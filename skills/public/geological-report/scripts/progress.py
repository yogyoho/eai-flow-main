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
VERIFIED 只能来自单章门 rc=0（--gate PASS 强制）——只信产物，不信子代理摘要。

相位推导（derive_phase，单一事实）：
  wave1 有 PENDING/DRAFTED → WAVE1（单章 BLOCKED 不拖停全书）
  存在未批准 BLOCKED → NEGOTIATE（先协商再定要点包范围）
  要点包未确认 → KEY_POINTS；ch10 未收口 → WAVE2；否则 FINAL。

退出码：0 成功 / 1 用法错误、非法状态转移、重复 init、未知章节。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1

# 派发额度 = config.yaml subagents.max_total_per_run（本计划 Task 5 提额到 16；clamp [1,50]）。
# progress.py 不读 harness 配置（技能脚本自包含），按 16 做预算展示与耗尽判定。
DISPATCH_BUDGET = 16

TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"DRAFTED", "VERIFIED", "BLOCKED"},  # PENDING→BLOCKED = 派发额度耗尽；PENDING→VERIFIED = 记账滞后凭门 PASS 补记（仍强制 --gate PASS）
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


def _build_cmd(stage: str, data: str, sd: str, *extra: str) -> str:
    return "python -X utf8 " + str(Path(__file__).resolve().parent / "build_output.py") + f" --stage {stage} --data-dir {data} --state-dir {sd} " + " ".join(extra)


def next_action(doc: dict, state_dir: Path) -> str:
    phase = derive_phase(doc)
    chs = doc["chapters"]
    order = chapter_order(chs)
    wave1 = order[:-1]
    last = order[-1] if order else None
    stage = doc.get("stage_path") or "<STAGE>"
    data = doc.get("data_dir") or "<DATA>"
    sd = str(state_dir)
    lines = [f"PHASE: {phase}"]

    if phase == "WAVE1":
        drafted = next((c for c in wave1 if chs[c]["status"] == "DRAFTED"), None)  # 先收口已起草的
        if drafted:
            lines += [
                f"[NEXT] 跑门: {drafted}（DRAFTED——只信产物，不信子代理摘要）",
                f"命令: {_build_cmd(stage, data, sd, '--chapter', drafted)}",
                f"期望 rc: 0 → python -X utf8 progress.py mark {drafted} VERIFIED --state-dir {sd} --gate PASS",
                f'        1 → 原 prompt + stderr 原文重派（每章 ≤1 次）；重派仍 FAIL → progress.py mark {drafted} BLOCKED --state-dir {sd} --gate FAIL --detail "<一句话差距>"',
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
                f"[NEXT] 跑门: {last}（DRAFTED，wave2 结论章）",
                f"命令: {_build_cmd(stage, data, sd, '--chapter', last)}",
                "期望 rc: 同 WAVE1 跑门分支（PASS→VERIFIED / FAIL→重派 ≤1 次→BLOCKED）",
            ]
            return "\n".join(lines)
        lines += [
            f"[NEXT] 派发: {last}（PENDING，wave2 结论章）",
            "动作: 派发契约同 wave1，输入追加 state/key_points.json——只依据要点包写投影式结论，不引入 wave1 之外的新数字",
        ]
        return "\n".join(lines)

    # FINAL
    blocked = sorted(c for c, s in chs.items() if s["status"] == "BLOCKED")
    if blocked:
        lines += [
            f"[NEXT] 终验（分级交付）: 已批准降档 {blocked}",
            f"命令: {_build_cmd(stage, data, sd, '--allow-partial', '--output', '<OUTPUTS>/<项目名>-<阶段>-地质勘查报告.md')}",
            "期望 rc: 0 BUILD_READY（stdout PARTIAL_DELIVERY 行明示 N 章降档；manifest.partial 逐章留痕）→ consistency.py → snapshot.py save → present_files（向用户汇报降档章节与差距）",
        ]
        return "\n".join(lines)
    lines += [
        "[NEXT] 终验: 全部章节 VERIFIED",
        f"命令: {_build_cmd(stage, data, sd, '--output', '<OUTPUTS>/<项目名>-<阶段>-地质勘查报告.md')}",
        "期望 rc: 0 BUILD_READY → consistency.py → snapshot.py save → present_files",
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
    if status == "VERIFIED" and args.gate != "PASS":
        print(f"[progress] {ch_id} VERIFIED 必须带 --gate PASS——VERIFIED 只能来自单章门 rc=0（只信产物，不信子代理摘要）", file=sys.stderr)
        return EXIT_ERROR
    ent = doc["chapters"][ch_id]
    ent["status"] = status
    if status == "DRAFTED":
        ent["dispatches"] = ent.get("dispatches", 0) + 1
        doc["total_dispatches"] = doc.get("total_dispatches", 0) + 1
        ent["last_gate"] = None
        ent["gate_detail"] = ""
        ent["blocked_reason"] = None
    elif status == "VERIFIED":
        ent["last_gate"] = "PASS"
        ent["gate_detail"] = args.detail or ""
    else:  # BLOCKED
        ent["last_gate"] = args.gate or "FAIL"
        ent["gate_detail"] = args.detail or ""
        ent["blocked_reason"] = args.detail or ("门 FAIL 且重派耗尽" if args.gate != "PASS" else "派发额度耗尽")
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"MARKED: {ch_id} {cur} → {status}（phase={doc['phase']}）")
    return EXIT_OK


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
    except json.JSONDecodeError as e:
        print(f"[progress] JSON 损坏: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
