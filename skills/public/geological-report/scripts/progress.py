#!/usr/bin/env python3
"""geological-report v2 — progress.py：章节进度状态机（步骤4 控制器）。

spec 2026-08-28 控制器化改造：主 agent 薄上下文只协调——每轮读 `next`（输出恰好一个
下一步动作 + 精确命令 + 期望 rc），派发/跑门/记账，不亲自写章。progress.json 是唯一
事实源（本脚本唯一写者，防手改同 formula_state 惯例）；断点续跑靠磁盘不靠对话记忆
（FORCED STOP / 上下文摘要压缩 / 新会话均无损恢复，spec §6 流4）。

状态机：
  PENDING  --派发--> DRAFTED --门PASS--> VERIFIED --修改回路--> DRAFTED
  DRAFTED  --重派--> DRAFTED（dispatches 递增；每章重派 ≤1 次由 SKILL.md 协议约束）
  DRAFTED  --门FAIL且重派耗尽--> BLOCKED --补数据/批准降档--> DRAFTED
  PENDING  --额度耗尽--> BLOCKED
VERIFIED 只能来自 `gate` 真跑单章门 rc=0 的自动回写（手动 mark VERIFIED 已禁用，bug-3049）——只信产物，不信子代理摘要。

相位推导（derive_phase，单一事实）：
  wave1 有 PENDING/DRAFTED → WAVE1（单章 BLOCKED 不拖停全书）
  存在未批准 BLOCKED → NEGOTIATE（先协商再定要点包范围）
  要点包未确认 → KEY_POINTS；ch10 未收口 → WAVE2；否则 FINAL。

退出码：0 成功 / 1 用法错误、非法状态转移、重复 init、未知章节、批量门有 FAIL。

平台预算规避（bug-3040/3048，2026-08-31）：gate 批量单章门（一次 bash 跑完全部 DRAFTED 章，
PASS 自动转 VERIFIED——唯一写者仍是本脚本）；run-stage freeze/finalize 把固定脚本序列
（冻结二连/组装→校验→快照三连）合并为一次 bash 调用，stdout 原样透传（BUILD_READY 等
交付铁律粘贴行不丢失）。主循环 bash 记账从 ~60 次/全书压到 ~25 次以内，停车点规约见 SKILL.md。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1

# finalize 的 consistency --standards 默认 = 技能规范索引（CC3 规范编号枚举门的真源；
# 缺文件时省略该旗标 → CC1/CC3 降为 manual，rc=2 由调用方按门拦语义处理）。
STANDARDS_INDEX = Path(__file__).resolve().parent.parent / "references" / "standards_index.json"

# 派发额度 = config.yaml subagents.max_total_per_run（本计划 Task 5 提额到 16；clamp [1,50]）。
# progress.py 不读 harness 配置（技能脚本自包含），按 16 做预算展示与耗尽判定。
# 注意：脚本内预算只做展示与 WAVE1 路由提示；硬执行在 harness SubagentLimitMiddleware（WAVE2 ch10 重派不检额度属预期）。
DISPATCH_BUDGET = 16

TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"DRAFTED", "VERIFIED", "BLOCKED"},  # PENDING→BLOCKED = 派发额度耗尽；PENDING→VERIFIED = gate 真跑门 PASS 自动补记（手动 mark VERIFIED 已禁用，bug-3049）
    "DRAFTED": {"DRAFTED", "VERIFIED", "BLOCKED"},  # DRAFTED→DRAFTED = 重派
    "VERIFIED": {"DRAFTED"},  # 修改回路重写
    "BLOCKED": {"DRAFTED"},  # 补数据/批准降档后复活
}


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


def load(state_dir: Path) -> dict:
    p = state_dir / "progress.json"
    if not p.exists():
        print(f"[progress] {p} 不存在——新任务先 init；续跑检查 --state-dir 路径", file=sys.stderr)
        raise SystemExit(EXIT_ERROR)
    return json.loads(p.read_text(encoding="utf-8"))


def save(state_dir: Path, doc: dict) -> None:
    """原子写（tmp + os.replace，build_output 同款）。不用 sort_keys：chapters 插入序=数值序。"""
    p = state_dir / "progress.json"
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, p)


def approved_set(doc: dict) -> set[str]:
    out: set[str] = set()
    for a in doc.get("downgrade_approvals", []):
        out.update(a.get("chapters", []))
    return out


def derive_phase(doc: dict) -> str:
    chs = doc["chapters"]
    order = chapter_order(chs)
    wave1 = order[:-1]
    wave2 = [order[-1]] if order else []
    unapproved = {c for c, s in chs.items() if s["status"] == "BLOCKED"} - approved_set(doc)
    if any(chs[c]["status"] in ("PENDING", "DRAFTED") for c in wave1):
        return "WAVE1"
    if unapproved:
        return "NEGOTIATE"
    if not doc.get("key_points_confirmed"):
        return "KEY_POINTS"
    if any(chs[c]["status"] in ("PENDING", "DRAFTED") for c in wave2):
        return "WAVE2"
    return "FINAL"


def _self_cmd(*extra: str) -> str:
    return "python -X utf8 " + str(Path(__file__).resolve()) + " " + " ".join(extra)


def next_action(doc: dict, state_dir: Path) -> str:
    phase = derive_phase(doc)
    chs = doc["chapters"]
    order = chapter_order(chs)
    wave1 = order[:-1]
    last = order[-1] if order else None
    sd = str(state_dir)
    lines = [f"PHASE: {phase}"]

    if phase == "WAVE1":
        drafted = [c for c in wave1 if chs[c]["status"] == "DRAFTED"]  # 先收口已起草的（批量一次跑完）
        if drafted:
            lines += [
                f"[NEXT] 批量跑门: {', '.join(drafted)}（DRAFTED——只信产物，不信子代理摘要；一次 bash 全部跑完，PASS 章自动转 VERIFIED）",
                f"命令: {_self_cmd('gate', '--state-dir', sd)}",
                "期望 rc: 0（GATE_BATCH_DONE passed=N failed=0，PASS 章已由 gate 真跑单章门自动转 VERIFIED）",
                '        1 → failed 章按 stderr 原文重派（原 prompt + stderr，每章 ≤1 次）；重派仍 FAIL → mark BLOCKED --gate FAIL --detail "<一句话差距>"',
            ]
            return "\n".join(lines)
        pending = [c for c in wave1 if chs[c]["status"] == "PENDING"]
        if doc.get("total_dispatches", 0) >= DISPATCH_BUDGET:
            lines += [
                f"[NEXT] 额度耗尽: 总派发 {doc.get('total_dispatches', 0)}/{DISPATCH_BUDGET}，剩余 PENDING {pending}",
                f'动作: 逐章 progress.py mark <chN> BLOCKED --state-dir {sd} --detail "派发额度耗尽" → 进协商（或请用户新会话续跑，progress 无损）',
            ]
            return "\n".join(lines)
        c = pending[0]
        lines += [
            f"[NEXT] 派发: {c}（PENDING，wave1 独立章）",
            f'动作: 按 SKILL.md 步骤4 派发契约组装 prompt，task(subagent_type="general-purpose") 派子代理直写 state/chapters/{c}.md',
            "约束: 每轮 ≤3 个并发 task()（超发被运行时静默丢弃）；子代理只回 ≤10 行摘要（含本章要点 3-5 条）",
            f"派发后记账: progress.py mark {c} DRAFTED --state-dir {sd}（收章后跑单章门，见 DRAFTED 分支）",
        ]
        return "\n".join(lines)

    if phase == "NEGOTIATE":
        un = sorted({c for c, s in chs.items() if s["status"] == "BLOCKED"} - approved_set(doc))
        lines += [
            f"[NEXT] 协商: 未批准 BLOCKED: {', '.join(un)}",
            "动作: 组差距表（章/实际 eff/目标/缺口——取各章 gate_detail 与单章门 stderr）单表单 ask_clarification 三选项:",
            "  ① 补数据（回 ingest → formula_runner → 相关章 mark DRAFTED 重派）",
            f'  ② 批准降档（progress.py approve-downgrade --state-dir {sd} --chapters {",".join(un)} --note "<用户批准依据>"）',
            "  ③ [待确认] 收尾（缺数信号放宽覆盖缩放，重写即可能达标）",
            "期望: 用户答复后才推进（单回合至多一次 ask_clarification；挂起即停，不推进）",
        ]
        return "\n".join(lines)

    if phase == "KEY_POINTS":
        lines += [
            "[NEXT] 要点包: wave1 已收口，蒸馏 state/key_points.json",
            "动作: 聚合各子代理摘要的「本章要点 3-5 条」+ formula_state 关键值（L9 总量/分类量、L10 对比、E 链经济指标）",
            '      写 state/key_points.json: {"chapters":{"ch1":[...],...},"highlights":{...},"issues":[...]}',
            f"      单表单 ask_clarification 呈现用户确认 → progress.py confirm-key-points --state-dir {sd}",
            "要点包 = ch10 唯一事实来源（不重读 9 章全文）",
        ]
        return "\n".join(lines)

    if phase == "WAVE2":
        if chs[last]["status"] == "DRAFTED":
            lines += [
                f"[NEXT] 跑门: {last}（DRAFTED，wave2 结论章——同款批量 gate 命令）",
                f"命令: {_self_cmd('gate', '--state-dir', sd)}",
                "期望 rc: 同 WAVE1 批量跑门分支（PASS→VERIFIED / FAIL→重派 ≤1 次→BLOCKED）",
            ]
            return "\n".join(lines)
        lines += [
            f"[NEXT] 派发: {last}（PENDING，wave2 结论章）",
            "动作: 派发契约同 wave1，输入追加 state/key_points.json——只依据要点包写投影式结论，不引入 wave1 之外的新数字",
        ]
        return "\n".join(lines)

    # FINAL
    blocked = sorted(c for c, s in chs.items() if s["status"] == "BLOCKED")
    gate_cmd = _self_cmd("run-stage", "finalize", "--state-dir", sd, "--outputs-dir", '"<OUTPUTS>"', "--task", '"<本轮用户指令一句话>"')
    if blocked:
        lines += [
            f"[NEXT] 终验（分级交付）: 已批准降档 {blocked}",
            f"命令: {gate_cmd}",
            "说明: 已批准降档自动加 --allow-partial（stdout PARTIAL_DELIVERY 行明示 N 章降档；manifest.partial 逐章留痕）——交付时向用户汇报降档章节与差距",
            "期望 rc: 0 → stdout 含 BUILD_READY/MANIFEST_READY（整行+退出码原样粘贴进回复）→ present_files",
            "        consistency rc=3（WARN/MANUAL 透传）→ 逐条汇报用户后交付；rc=1/2 → stderr 原样呈现，修章重跑",
        ]
        return "\n".join(lines)
    lines += [
        "[NEXT] 终验: 全部章节 VERIFIED",
        f"命令: {gate_cmd}",
        "说明: run-stage finalize 一次 bash 完成 build_output → consistency.py → snapshot.py save（交付名由脚本从 data/ 拼，stdout 原样透传）",
        "期望 rc: 0 → stdout 含 BUILD_READY/MANIFEST_READY（整行+退出码原样粘贴进回复）→ present_files",
        "        consistency rc=3（WARN/MANUAL 透传）→ 逐条汇报用户后交付；rc=1/2 → stderr 原样呈现，修章重跑",
    ]
    return "\n".join(lines)


def cmd_init(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    p = state_dir / "progress.json"
    if p.exists():
        print(f"[progress] {p} 已存在——续跑请用 next/status，勿重复 init 抹掉进度", file=sys.stderr)
        return EXIT_ERROR
    stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
    doc = {
        "stage_path": str(Path(args.stage).resolve()),
        "data_dir": str(Path(args.data_dir).resolve()) if args.data_dir else None,
        "phase": "WAVE1",
        "total_dispatches": 0,
        "chapters": {c: {"status": "PENDING", "dispatches": 0, "last_gate": None, "gate_detail": "", "blocked_reason": None} for c in chapter_order(stage.get("chapters", {}))},
        "key_points_confirmed": False,
        "downgrade_approvals": [],
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    save(state_dir, doc)
    n = len(doc["chapters"])
    print(f"PROGRESS_INIT: {n} 章全部 PENDING（{', '.join(doc['chapters'])}）→ 下一步 progress.py next")
    return EXIT_OK


def cmd_next(args: argparse.Namespace) -> int:
    doc = load(Path(args.state_dir))
    print(next_action(doc, Path(args.state_dir)))
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    doc = load(Path(args.state_dir))
    print(f"phase={derive_phase(doc)} 总派发={doc.get('total_dispatches', 0)}/{DISPATCH_BUDGET} 要点包确认={doc.get('key_points_confirmed', False)}")
    for c in chapter_order(doc["chapters"]):
        s = doc["chapters"][c]
        extra = f" reason={s['blocked_reason']}" if s.get("blocked_reason") else ""
        print(f"  {c}: {s['status']} 派发{s.get('dispatches', 0)} 门={s.get('last_gate')}{extra}")
    return EXIT_OK


def cmd_mark(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    ch_id, status = args.chapter, args.status
    if ch_id not in doc["chapters"]:
        print(f"[progress] 未知章节 {ch_id}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    if status not in ("DRAFTED", "VERIFIED", "BLOCKED"):
        print(f"[progress] mark 只接受 DRAFTED/VERIFIED/BLOCKED（收到 {status}）", file=sys.stderr)
        return EXIT_ERROR
    cur = doc["chapters"][ch_id]["status"]
    if status not in TRANSITIONS[cur]:
        print(f"[progress] 非法转移 {ch_id}: {cur} → {status}（合法: {cur} → {sorted(TRANSITIONS[cur])}）", file=sys.stderr)
        return EXIT_ERROR
    # bug-3049 定案：--gate PASS 是调用方自证（自申报），非官方凭据——VERIFIED 一律拒绝手动 mark。
    # 唯一合法通道 = progress.py gate（内部真跑 build_output.run_chapter_gate，PASS 章自动回写）。
    if status == "VERIFIED":
        print(f"[progress] {ch_id} 手动 mark VERIFIED 已禁用（--gate PASS 是自证，bug-3049）——用 `progress.py gate`（真跑官方单章门，PASS 自动转 VERIFIED）或 `gate --chapters {ch_id}`", file=sys.stderr)
        return EXIT_ERROR
    ent = doc["chapters"][ch_id]
    ent["status"] = status
    if status == "DRAFTED":
        ent["dispatches"] = ent.get("dispatches", 0) + 1
        doc["total_dispatches"] = doc.get("total_dispatches", 0) + 1
        ent["last_gate"] = None
        ent["gate_detail"] = ""
        ent["blocked_reason"] = None
    else:  # BLOCKED
        ent["last_gate"] = args.gate or "FAIL"
        ent["gate_detail"] = args.detail or ""
        ent["blocked_reason"] = args.detail or ("门 FAIL 且重派耗尽" if args.gate != "PASS" else "派发额度耗尽")
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"MARKED: {ch_id} {cur} → {status}（phase={doc['phase']}）")
    return EXIT_OK


def cmd_gate(args: argparse.Namespace) -> int:
    """批量单章门（平台预算规避，bug-3040/3048）：一次 bash 跑完全部指定章的门禁，
    PASS 章当场自动转 VERIFIED（last_gate=PASS；VERIFIED 只能来自单章门 rc=0 的不变式不破——
    推进凭据就是 run_chapter_gate 无异常返回，progress.py 仍是 progress.json 唯一写者）。
    任一章 FAIL → stderr 打该章完整差距，不推进该章，rc=1。"""
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    if not doc.get("stage_path") or not doc.get("data_dir"):
        print("[progress] progress.json 缺 stage_path/data_dir（init 须带 --stage 与 --data-dir 才能批量跑门）", file=sys.stderr)
        return EXIT_ERROR
    if args.chapters:
        wanted = [c.strip() for c in args.chapters.split(",") if c.strip()]
        unknown = [c for c in wanted if c not in doc["chapters"]]
        if unknown:
            print(f"[progress] 未知章节 {unknown}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
            return EXIT_ERROR
    else:
        wanted = [c for c in chapter_order(doc["chapters"]) if doc["chapters"][c]["status"] == "DRAFTED"]
    if not wanted:
        print("[progress] 没有 DRAFTED 章（显式列表除外）——先按 next 指引派发", file=sys.stderr)
        return EXIT_ERROR
    stage = json.loads(Path(doc["stage_path"]).read_text(encoding="utf-8"))
    import build_output  # 同目录脚本；targets 语义与 build_output CLI 一致（--targets 仅调试）

    targets, _src = build_output.resolve_targets(args.targets, Path(doc["stage_path"]), data_dir=Path(doc["data_dir"]))  # EAI-CUSTOM (geo-sample-bank Phase 2 T4)
    passed: list[str] = []
    failed: list[str] = []
    for ch in wanted:
        try:
            build_output.run_chapter_gate(stage, Path(doc["data_dir"]), state_dir, ch, targets)
            passed.append(ch)
        except ValueError as e:
            failed.append(ch)
            print(f"CHAPTER_GATE_FAIL: {ch}\n{e}", file=sys.stderr)
    skipped: list[str] = []
    for ch in passed:
        ent = doc["chapters"][ch]
        if "VERIFIED" not in TRANSITIONS[ent["status"]]:
            skipped.append(f"{ch}({ent['status']})")  # BLOCKED→VERIFIED 非法：先 mark DRAFTED 复活再跑门
            continue
        ent["status"] = "VERIFIED"
        ent["last_gate"] = "PASS"
        ent["gate_detail"] = ""
        ent["blocked_reason"] = None
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"GATE_BATCH_DONE: passed={len(passed) - len(skipped)} failed={len(failed)}（failed: {', '.join(failed) or '无'}；skipped: {', '.join(skipped) or '无'}——stderr 逐条差距，原 prompt 重派 ≤1 次）")
    if skipped:
        print(f"[progress] 门过但未推进（状态机不允许直接 {skipped}；先 mark DRAFTED 复活）: {skipped}", file=sys.stderr)
    return EXIT_ERROR if failed else EXIT_OK


def _run_py(script: str, *cmd_args: str) -> int:
    """子进程跑同目录脚本，stdout/stderr 原样透传（BUILD_READY/CHAPTER_GATE_PASS 等交付粘贴行不丢失）。"""
    return subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).resolve().parent / script), *cmd_args]).returncode


def cmd_run_stage(args: argparse.Namespace) -> int:
    """固定脚本序列合并为一次 bash（平台预算规避）：freeze = 冻结二连（manifest+execute），
    finalize = 组装→校验→快照三连。退出码逐步透传：build/manifest 1 即停；consistency 0/3
    继续（3=WARN/MANUAL，交付时汇报用户）、1/2 即停；snapshot 透传。"""
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    if not doc.get("stage_path") or not doc.get("data_dir"):
        print("[progress] progress.json 缺 stage_path/data_dir（init 须带 --stage 与 --data-dir）", file=sys.stderr)
        return EXIT_ERROR
    stage, data = doc["stage_path"], doc["data_dir"]
    if args.stage_name == "finalize" and not args.outputs_dir:
        print("[progress] run-stage finalize 需要 --outputs-dir（交付目录）", file=sys.stderr)
        return EXIT_ERROR
    if args.stage_name == "freeze":
        rc = _run_py("chapter_planner.py", "manifest", "--stage", stage, "--output", str(state_dir / "chapter_manifest.json"))
        if rc:
            return rc
        print("[run-stage] manifest OK → formula_runner execute（rc=3=有 anomalies，必须发卡逐条呈现用户确认）", file=sys.stderr)
        return _run_py("formula_runner.py", "execute", "--stage", stage, "--data-dir", data, "--state-dir", str(state_dir))
    # finalize：交付名唯一来源 = data/ 表单（expected_deliverable_name，与 build_output 交付名门同源）
    import build_output

    stage_doc = json.loads(Path(stage).read_text(encoding="utf-8"))
    report = Path(args.outputs_dir) / build_output.expected_deliverable_name(stage_doc, Path(data))
    blocked_approved = {c for c, s in doc["chapters"].items() if s["status"] == "BLOCKED"} & approved_set(doc)
    build_args = ["--stage", stage, "--data-dir", data, "--state-dir", str(state_dir), "--output", str(report)]
    if blocked_approved or args.allow_partial:
        build_args.append("--allow-partial")
        print(f"[run-stage] 分级交付模式（已批准降档 {sorted(blocked_approved)}——交付时如实汇报降档章节与差距）", file=sys.stderr)
    rc = _run_py("build_output.py", *build_args)
    if rc:
        return rc
    # 复核修复（bug-3058）：build_output 内联门已按去附录正文（body scope）跑过 consistency 并写
    # consistency_check.json；此处再以完整报告重跑会以不同 scope 覆盖同一 JSON（附录文本/全文字数
    # 差异 → 汇总漂移、rc 语义漂移）。统一 scope：优先复用 body 文件（build 成功时必在），CLI rc 语义不变。
    _body = state_dir / "consistency_body.md"
    cons_args = ["--report", str(_body if _body.exists() else report), "--data-dir", data, "--stage", stage, "--state", str(state_dir / "formula_state.json"), "--output", str(state_dir / "consistency_check.json")]
    if STANDARDS_INDEX.exists():
        cons_args += ["--standards", str(STANDARDS_INDEX)]
    rc = _run_py("consistency.py", *cons_args)
    if rc in (1, 2):
        return rc
    if rc == 3:
        print("[run-stage] CONSISTENCY_RC3: 校验完成带 WARN/MANUAL——逐条汇报用户后再交付（state/consistency_check.json）", file=sys.stderr)
    return _run_py(
        "snapshot.py",
        "save",
        "--task",
        args.task,
        "--stage",
        stage,
        "--data-dir",
        data,
        "--state-dir",
        str(state_dir),
        "--manifest",
        str(state_dir / "chapter_manifest.json"),
        "--formula-state",
        str(state_dir / "formula_state.json"),
        "--report",
        str(report),
        "--output",
        str(Path(args.outputs_dir) / "project_snapshot.json"),
    )


def cmd_confirm(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    doc["key_points_confirmed"] = True
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"KEY_POINTS_CONFIRMED（phase={doc['phase']}）")
    return EXIT_OK


def cmd_approve(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    chs = [c.strip() for c in args.chapters.split(",") if c.strip()]
    unknown = [c for c in chs if c not in doc["chapters"]]
    if unknown:
        print(f"[progress] 未知章节 {unknown}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    doc.setdefault("downgrade_approvals", []).append({"chapters": chs, "note": args.note or "", "approved_at": datetime.now().astimezone().isoformat(timespec="seconds")})
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"APPROVED: 降档批准 {chs}（累计批准集 {sorted(approved_set(doc))}，phase={doc['phase']}）")
    return EXIT_OK


def main() -> int:
    p = argparse.ArgumentParser(description="geological-report v2 — 章节进度状态机（步骤4 控制器）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("init", help="按 stage 章节清单初始化 progress.json（全 PENDING；已存在=续跑拒重置）")
    sp.add_argument("--stage", required=True)
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--data-dir", help="记录数据目录（next 渲染精确命令用；缺省输出 <DATA> 占位）")
    sp.set_defaults(fn=cmd_init)
    sp = sub.add_parser("next", help="控制器每轮先读：恰好一个下一步动作 + 精确命令 + 期望 rc")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_next)
    sp = sub.add_parser("status", help="全章状态表 + 派发计数 + 额度余量")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser("mark", help="状态转移（DRAFTED/VERIFIED/BLOCKED）")
    sp.add_argument("chapter")
    sp.add_argument("status")
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--gate", choices=["PASS", "FAIL"])
    sp.add_argument("--detail", default="")
    sp.set_defaults(fn=cmd_mark)
    sp = sub.add_parser("gate", help="批量单章门：一次跑完全部（缺省）或指定章的门禁，PASS 章自动转 VERIFIED（bug-3049 后 VERIFIED 唯一通道）")
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--chapters", help="逗号分隔，如 ch2,ch3；缺省=全部 DRAFTED 章")
    sp.add_argument("--targets", help="depth_targets.json 路径；仅调试，正式跑门绝不传（同 build_output 语义）")
    sp.set_defaults(fn=cmd_gate)
    sp = sub.add_parser("run-stage", help="固定脚本序列合并一次 bash：freeze=manifest+execute；finalize=build→consistency→snapshot")
    sp.add_argument("stage_name", choices=["freeze", "finalize"])
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--outputs-dir", help="finalize 必填：交付目录（报告+project_snapshot.json 落这里）")
    sp.add_argument("--task", default="地质勘查报告终验", help="snapshot last_task 一句话摘要")
    sp.add_argument("--allow-partial", action="store_true", help="强制分级交付（已批准降档时自动启用，无需显式传）")
    sp.set_defaults(fn=cmd_run_stage)
    sp = sub.add_parser("confirm-key-points", help="要点包已经用户单表单确认（解锁 ch10）")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_confirm)
    sp = sub.add_parser("approve-downgrade", help="记录用户批准的降档（--allow-partial 放行凭据）")
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--chapters", required=True, help="逗号分隔，如 ch3,ch8")
    sp.add_argument("--note", default="")
    sp.set_defaults(fn=cmd_approve)
    args = p.parse_args()
    try:
        return args.fn(args)
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
        print(f"[progress] progress.json/stage 文件损坏或不可读（手改特征或路径错误）: {e!r}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
