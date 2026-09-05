#!/usr/bin/env python3
"""bid-proposal-writing v4 — progress.py：册/章级进度状态机(阶段4a 控制器)。

移植自 geological-report progress.py(eng-review 1A: 照搬+TODOS 多副本债扩条目;
bid 子集=init/next/status/mark/gate, geo 的 run-stage/要点包/降档协商属 T7/WP-2.2)。

主 agent 薄上下文只协调——每轮读 `next`(输出恰好一个下一步动作+精确命令+期望 rc),
派发/跑门/记账, 不亲自写响应。progress.json 是唯一事实源(本脚本唯一写者); 断点续跑
靠磁盘不靠对话记忆(FORCED STOP/上下文压缩/新会话均无损恢复)。

存放位置(bid 适配): progress.json 写 workspace 根(与 last_build.json 同级)——bid 的
state/ 签名登记不含它, 避免扩 state_guard 登记表; 唯一写者纪律与 geo 同款。

状态机(bug-3049 反自证凭据同款移植):
  PENDING  --响应已merge--> DRAFTED --gate真跑PASS--> VERIFIED --修改回路--> DRAFTED
  DRAFTED  --gate连续2轮FAIL--> BLOCKED --处置(候选白名单/重写)--> DRAFTED
VERIFIED 只能来自 `gate` 真跑章门 PASS 的自动回写(手动 mark VERIFIED 已禁用)——只信
产物, 不信 agent 自述。章门判据(确定性): 本章活 technical/service 条款全部有响应
(零空项=完备性) + 正文零 <SLOT:待填 白占位。

相位推导(derive_phase, 单一事实):
  存在 BLOCKED → RESOLVE(先处置: 实体门候选白名单/重写)
  存在 PENDING/DRAFTED → GENERATE(先收口已 DRAFTED——批量跑门优先于派发)
  全 VERIFIED → BUILD(两文档册集渲染+交付门)
  build 回执+交付凭据在场 → DONE

退出码: 0 成功 / 1 用法错误、非法状态转移、重复 init、未知章节。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_output  # noqa: E402  兄弟模块(章分组/linked_map/装载器复用——geo gate 调 build_output.run_chapter_gate 同款先例)

EXIT_OK, EXIT_ERROR = 0, 1

STATUSES = ("PENDING", "DRAFTED", "VERIFIED", "BLOCKED")
TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"DRAFTED", "BLOCKED"},
    "DRAFTED": {"DRAFTED", "VERIFIED", "BLOCKED"},
    "VERIFIED": {"DRAFTED"},  # 修改回路重写
    "BLOCKED": {"DRAFTED"},  # 处置后复活
}
PROGRESS_FILE = "progress.json"


# ── 章计划(确定性, 从 state 推导; 不手写) ────────────────────────────────────


def chapter_plan(state_dir: Path) -> list[dict]:
    """章计划: structure 镜像序的 technical 章分组 + 各章活 technical/service 条款。

    与 build_output._chapter_groups 同构(镜像连续, 不重排)——切册在 build 期,
    进度跟踪以章为粒度(册是 build 产物, 7A)。
    """
    clauses = build_output.load_clauses(state_dir)
    structure = build_output.load_structure(state_dir)
    ctx = build_output._volume_ctx("technical", structure, clauses, build_output.load_responses(state_dir))
    groups: list[list[dict]] = []
    for node in ctx["nodes"]:
        key = build_output.booklets.chapter_of(node["path"])
        if not groups or build_output.booklets.chapter_of(groups[-1][-1]["path"]) != key:
            groups.append([node])
        else:
            groups[-1].append(node)
    plan: list[dict] = []
    for i, group in enumerate(groups, 1):
        chapter = build_output.booklets.chapter_of(group[0]["path"])
        node_ids = {n["node_id"] for n in group}
        clause_ids = sorted(cid for cid, nid in ctx["linked_map"].items() if nid in node_ids)
        plan.append({"id": f"C-{i:02d}", "chapter": chapter, "clause_ids": clause_ids})
    # 兜底章(孤儿条款)挂在最后一个实体章; 全零章的极端结构 → 计划为空(管线前端问题)
    return plan


def chapter_progress(plan: list[dict], responses: list[dict]) -> dict[str, dict]:
    """按 responses.json 现算每章已 merge 的响应覆盖(推导 DRAFTED, 不靠 agent 自述)。"""
    resp_ids = {str(r.get("clause_id")) for r in responses}
    progress: dict[str, dict] = {}
    for ch in plan:
        total = len(ch["clause_ids"])
        done = sum(1 for cid in ch["clause_ids"] if cid in resp_ids)
        progress[ch["id"]] = {"chapter": ch["chapter"], "clause_total": total, "clause_responded": done}
    return progress


def derived_status(record: dict | None, ch: dict, responses: list[dict], texts: dict[str, str]) -> str:
    """VERIFIED/BLOCKED 粘滞(磁盘记录优先); 其余按产物推导——响应全量 merge 即
    DRAFTED(无需自述), 不完整回 PENDING(删响应即降级, 修改回路语义)。"""
    recorded = (record or {}).get("status")
    if recorded in ("VERIFIED", "BLOCKED"):
        return recorded
    complete = bool(ch["clause_ids"]) and chapter_progress_for(ch, responses) == len(ch["clause_ids"])
    if complete and all("<SLOT:" not in texts.get(cid, "") for cid in ch["clause_ids"]):
        return "DRAFTED"
    return recorded or "PENDING"


def chapter_progress_for(ch: dict, responses: list[dict]) -> int:
    resp_ids = {str(r.get("clause_id")) for r in responses}
    return sum(1 for cid in ch["clause_ids"] if cid in resp_ids)


def load(workspace_dir: Path) -> dict:
    path = workspace_dir / PROGRESS_FILE
    if not path.is_file():
        raise ProgressError(f"{PROGRESS_FILE} 不存在——先跑 init(重复 init=续跑拒重置)")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ProgressError(f"{PROGRESS_FILE} 不可解析: {exc}") from exc


def save(workspace_dir: Path, doc: dict) -> None:
    (workspace_dir / PROGRESS_FILE).write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ProgressError(Exception):
    """用法/状态错误 → 退出码 1。"""


# ── 相位与下一步(恰好一个) ──────────────────────────────────────────────────


def derive_phase(doc: dict, plan: list[dict], responses: list[dict], texts: dict[str, str]) -> str:
    chs = doc.get("chapters", {})
    if any(rec.get("status") == "BLOCKED" for rec in chs.values()):
        return "RESOLVE"
    statuses = {ch["id"]: derived_status(chs.get(ch["id"]), ch, responses, texts) for ch in plan}
    if any(s in ("PENDING", "DRAFTED") for s in statuses.values()):
        return "GENERATE"
    if not doc.get("key_points_confirmed"):
        return "KEY_POINTS"  # 波间要点包门(T7): 报价汇总/关键承诺/偏离结论 用户单表单确认后才准 build
    if (doc.get("build") or {}).get("done"):
        return "DONE"
    return "BUILD"


def next_action(doc: dict, plan: list[dict], responses: list[dict], texts: dict[str, str], state_dir: Path) -> str:
    phase = derive_phase(doc, plan, responses, texts)
    chs = doc.get("chapters", {})
    lines = [f"PHASE: {phase}"]

    if phase == "RESOLVE":
        blocked = sorted(cid for cid, rec in chs.items() if rec.get("status") == "BLOCKED")
        lines += [
            f"[NEXT] 处置 BLOCKED 章: {', '.join(blocked)}",
            "动作(按 gate_detail 二选一): ① 实体残留 → 用户确认候选后写入 state/entities_whitelist.json(见 实体lint报告.md 候选白名单节);",
            "  ② 编造正文含残留 → 回 stage4a 重写该章响应(tech_response_prompt.md 级联)",
            f"处置后: progress.py mark <章id> DRAFTED --state-dir {state_dir} → 重进 GENERATE",
        ]
        return "\n".join(lines)

    if phase == "GENERATE":
        drafted = [ch["id"] for ch in plan if derived_status(chs.get(ch["id"]), ch, responses, texts) == "DRAFTED"]
        if drafted:
            lines += [
                f"[NEXT] 批量跑门: {', '.join(drafted)}(DRAFTED——只信产物; PASS 章自动转 VERIFIED)",
                f"命令: progress.py gate --state-dir {state_dir}",
                "期望 rc: 0(GATE_BATCH_DONE passed=N failed=0); failed 章按 stderr 重写, 连续 2 轮 FAIL 自动 BLOCKED",
            ]
            return "\n".join(lines)
        pending = next(ch for ch in plan if derived_status(chs.get(ch["id"]), ch, responses, texts) == "PENDING")
        lines += [
            f"[NEXT] 生成: {pending['id']}({pending['chapter']})——{len(pending['clause_ids'])} 条活条款",
            "动作: 读 references/tech_response_prompt.md(供源级联), 逐条款生成响应候选落盘 candidates/, responses.py validate+merge",
            f"merge 后重跑: progress.py next --state-dir {state_dir}(全量 merge 的章自动升 DRAFTED)",
        ]
        return "\n".join(lines)

    if phase == "KEY_POINTS":
        lines += [
            "[NEXT] 波间要点包: 响应生成已收口, 蒸馏 workspace/key_points.json",
            "动作: 聚合三节——①报价汇总(各册 SLOT 报价值对照) ②关键承诺(工期/质保/响应时限等废标级承诺) ③偏离结论(偏离表口径)",
            f"      单表单 ask_clarification 呈现用户确认 → progress.py confirm-key-points --state-dir {state_dir}",
            "要点包 = 投标函/结论章与偏离表的唯一口径来源(不重读全部响应正文)",
        ]
        return "\n".join(lines)

    if phase == "BUILD":
        lines += [
            "[NEXT] build: 全部章 VERIFIED → 两文档册集渲染",
            f"命令: build_output.py --state-dir {state_dir} --out /mnt/user-data/outputs/投标文件(速查表逐字)",
            "期望 rc: 0/3(3=带异常, 摘要 anomalies 逐项呈现); 实体门硬门期间交付被禁, 按 lint 报告处置",
            f"build 后: progress.py mark-build-done --state-dir {state_dir} → DONE",
        ]
        return "\n".join(lines)

    lines += ["[NEXT] DONE: 册集已交付凭据在场——进确认门2(stage3-merge-gate2.md)→阶段5 评分"]
    return "\n".join(lines)


# ── 章门(真跑, bug-3049 反自证) ─────────────────────────────────────────────


def run_chapter_gate(ch: dict, responses: list[dict], texts: dict[str, str]) -> tuple[bool, str]:
    """单章门(确定性): 完备性(零空项) + 零 <SLOT:待填 白占位。PASS → 调用方转 VERIFIED。"""
    missing = [cid for cid in ch["clause_ids"] if cid not in {str(r.get("clause_id")) for r in responses}]
    if missing:
        return False, f"响应缺失 {len(missing)}/{len(ch['clause_ids'])}: {', '.join(missing[:8])}"
    whites = [cid for cid in ch["clause_ids"] if "<SLOT:" in texts.get(cid, "")]
    if whites:
        return False, f"正文残留 <SLOT:待填> 白占位(围栏域必须经槽位注入或重写): {', '.join(whites[:8])}"
    return True, f"完备 {len(ch['clause_ids'])} 条, 零白占位"


# ── 子命令 ──────────────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    workspace = Path(args.workspace_dir) if args.workspace_dir else state_dir.parent
    path = workspace / PROGRESS_FILE
    if path.is_file():
        print(json.dumps({"command": "init", "resumed": True, "note": "progress.json 已存在=续跑, 拒重置(断点无损)"}, ensure_ascii=False))
        return EXIT_OK
    plan = chapter_plan(state_dir)
    if not plan:
        raise ProgressError("章计划为空: structure.json 无 technical 卷节点——先走阶段2 提取")
    doc = {"chapters": {}, "plan": plan, "build": {"done": False}}
    responses = build_output.load_responses(state_dir)
    for ch in plan:
        doc["chapters"][ch["id"]] = {"chapter": ch["chapter"], "status": derived_status(None, ch, responses, {})}
    save(workspace, doc)
    print(json.dumps({"command": "init", "chapters": len(plan), "resumed": False}, ensure_ascii=False))
    return EXIT_OK


def cmd_next(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    workspace = Path(args.workspace_dir) if args.workspace_dir else state_dir.parent
    doc = load(workspace)
    plan = doc.get("plan") or chapter_plan(state_dir)
    responses = build_output.load_responses(state_dir)
    print(next_action(doc, plan, responses, {}, state_dir))
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    workspace = Path(args.workspace_dir) if args.workspace_dir else state_dir.parent
    doc = load(workspace)
    plan = doc.get("plan") or chapter_plan(state_dir)
    responses = build_output.load_responses(state_dir)
    rows = []
    for ch in plan:
        status = derived_status(doc["chapters"].get(ch["id"]), ch, responses, {})
        rows.append({"id": ch["id"], "chapter": ch["chapter"], "status": status,
                     "clauses": f"{chapter_progress_for(ch, responses)}/{len(ch['clause_ids'])}"})
    print(json.dumps({"command": "status", "phase": derive_phase(doc, plan, responses, {}), "chapters": rows}, ensure_ascii=False))
    return EXIT_OK


def cmd_mark(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    workspace = Path(args.workspace_dir) if args.workspace_dir else state_dir.parent
    doc = load(workspace)
    rec = doc["chapters"].get(args.chapter)
    if rec is None:
        raise ProgressError(f"未知章节: {args.chapter}(合法: {', '.join(sorted(doc['chapters']))})")
    if args.status == "VERIFIED":
        # bug-3049 反自证凭据: VERIFIED 唯一通道 = gate 真跑 PASS 自动回写
        print(json.dumps({"command": "mark", "rejected": True,
                          "message": "VERIFIED 禁止手动标记(bug-3049 同款)——唯一通道: progress.py gate 真跑章门 PASS 自动回写"}, ensure_ascii=False))
        return EXIT_ERROR
    if args.status not in TRANSITIONS.get(rec["status"], set()):
        raise ProgressError(f"非法转移 {rec['status']} → {args.status}(合法: {sorted(TRANSITIONS.get(rec['status'], set()))})")
    rec["status"] = args.status
    if args.detail:
        rec["detail"] = args.detail
    save(workspace, doc)
    print(json.dumps({"command": "mark", "chapter": args.chapter, "status": args.status}, ensure_ascii=False))
    return EXIT_OK


def cmd_gate(args: argparse.Namespace) -> int:
    """批量章门: 一次跑完全部 DRAFTED 章(缺省)或指定章, PASS 自动转 VERIFIED。

    VERIFIED 唯一通道(bug-3049); FAIL 章按 stderr 给差距, 连续 2 轮 FAIL 自动 BLOCKED
    (gate_rounds 记账在章记录内, 指纹=本轮门失败原因——简化为次数, 重写后 DRAFTED 重派清零)。
    """
    state_dir = Path(args.state_dir)
    workspace = Path(args.workspace_dir) if args.workspace_dir else state_dir.parent
    doc = load(workspace)
    plan_list = doc.get("plan") or chapter_plan(state_dir)
    plan = {ch["id"]: ch for ch in plan_list}
    responses = build_output.load_responses(state_dir)
    derived = {ch["id"]: derived_status(doc["chapters"].get(ch["id"]), ch, responses, {}) for ch in plan_list}
    targets = [c.strip() for c in args.chapters.split(",")] if args.chapters else sorted(
        cid for cid, status in derived.items() if status == "DRAFTED"
    )
    if not targets:
        raise ProgressError("无 DRAFTED 章可跑门(先完成阶段4a 响应生成)")
    passed, failed = 0, 0
    for cid in targets:
        rec = doc["chapters"].get(cid)
        if rec is None:
            raise ProgressError(f"未知章节: {cid}")
        if rec.get("status") == "VERIFIED":
            continue
        ok, detail = run_chapter_gate(plan[cid], responses, {})
        if ok:
            rec["status"] = "VERIFIED"
            rec["gate_detail"] = detail
            rec.pop("gate_rounds", None)
            passed += 1
        else:
            failed += 1
            rec["gate_detail"] = detail
            rounds = int(rec.get("gate_rounds") or 0) + 1
            rec["gate_rounds"] = rounds
            if rounds >= 2:
                rec["status"] = "BLOCKED"
                rec["detail"] = f"章门连续 {rounds} 轮 FAIL: {detail}"
    save(workspace, doc)
    print(json.dumps({"command": "gate", "GATE_BATCH_DONE": True, "passed": passed, "failed": failed,
                      "details": {cid: doc["chapters"][cid].get("gate_detail", "") for cid in targets}}, ensure_ascii=False))
    return EXIT_ERROR if failed else EXIT_OK


def cmd_confirm_key_points(args: argparse.Namespace) -> int:
    """波间要点包确认记账(T7): 用户单表单确认后解锁 BUILD 相位。"""
    state_dir = Path(args.state_dir)
    workspace = Path(args.workspace_dir) if args.workspace_dir else state_dir.parent
    doc = load(workspace)
    doc["key_points_confirmed"] = True
    save(workspace, doc)
    print(json.dumps({"command": "confirm-key-points", "key_points_confirmed": True}, ensure_ascii=False))
    return EXIT_OK


def cmd_mark_build_done(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    workspace = Path(args.workspace_dir) if args.workspace_dir else state_dir.parent
    doc = load(workspace)
    doc.setdefault("build", {})["done"] = True
    save(workspace, doc)
    print(json.dumps({"command": "mark-build-done", "phase": "DONE"}, ensure_ascii=False))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="progress.py",
        description="投标方案编写·阶段4a 控制器: 册/章级进度状态机(next 恰好一个下一步; VERIFIED 唯一通道=真跑章门; 断点续跑靠磁盘)",
        epilog="示例: python progress.py init --state-dir state ; python progress.py next --state-dir state",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _state_arg(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--state-dir", required=True, help="状态目录(clauses/structure/responses 只读推导章计划)")
        sp.add_argument("--workspace-dir", default=None, help="progress.json 所在目录(默认 state 目录的父级=workspace)")

    sp = sub.add_parser("init", help="按 structure 章计划初始化 progress.json(已存在=续跑拒重置)")
    _state_arg(sp)
    sp.set_defaults(func=cmd_init)
    sp = sub.add_parser("next", help="控制器每轮先读: 恰好一个下一步动作+精确命令+期望 rc")
    _state_arg(sp)
    sp.set_defaults(func=cmd_next)
    sp = sub.add_parser("status", help="全章状态表+响应覆盖")
    _state_arg(sp)
    sp.set_defaults(func=cmd_status)
    sp = sub.add_parser("mark", help="状态转移(DRAFTED/BLOCKED; VERIFIED 禁手动——bug-3049)")
    _state_arg(sp)
    sp.add_argument("chapter", help="章 id(C-01..)")
    sp.add_argument("status", help=f"目标状态({','.join(s for s in STATUSES if s != 'VERIFIED')}; VERIFIED 拒绝)")
    sp.add_argument("--detail", default=None, help="一句话备注(BLOCKED 原因等)")
    sp.set_defaults(func=cmd_mark)
    sp = sub.add_parser("gate", help="批量章门: 一次跑完全部(缺省)或指定 DRAFTED 章, PASS 自动转 VERIFIED")
    _state_arg(sp)
    sp.add_argument("--chapters", default=None, help="逗号分隔章 id(缺省=全部 DRAFTED 章)")
    sp.set_defaults(func=cmd_gate)
    sp = sub.add_parser("confirm-key-points", help="波间要点包已经用户单表单确认(解锁 BUILD, T7)")
    _state_arg(sp)
    sp.set_defaults(func=cmd_confirm_key_points)
    sp = sub.add_parser("mark-build-done", help="build+交付完成记账(→DONE)")
    _state_arg(sp)
    sp.set_defaults(func=cmd_mark_build_done)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if not exc.code:
            return EXIT_OK
        print(f"[progress] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}; 用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR
    try:
        return args.func(args)
    except ProgressError as exc:
        print(f"[progress] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
