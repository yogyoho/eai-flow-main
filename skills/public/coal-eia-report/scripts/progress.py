#!/usr/bin/env python3
"""coal-eia-report v2 — progress.py：两层状态机（章级门禁 × 节级派发，步骤4 控制器）。

spec docs/designs/coal-eia-report-v2.md「两层状态模型」：报告 ~700 页 ≈ 77+ 节，派发/记账
是节级（chNN_SNN），门禁是章级（节无独立门）。progress.json 是唯一事实源（本脚本唯一写者，
防手改同 formula_state 惯例）；断点续跑靠磁盘不靠对话记忆。章条目带 sections 子表：

  {"ch6": {"status": "IN_PROGRESS",
    "sections": [
      {"id": "ch6_S01", "title": "矿区开采地表沉陷预测", "status": "VERIFIED",
       "dispatches": 1, "delivered": false},
      {"id": "ch6_S02", "title": "生态环境影响评价", "status": "DRAFTED", "dispatches": 1}]}}

状态机（章与节同构）：
  PENDING  --派发--> DRAFTED --门PASS--> VERIFIED --修改回路--> DRAFTED
  DRAFTED  --重派--> DRAFTED（dispatches 递增）
  DRAFTED  --门FAIL且重派耗尽--> BLOCKED --补数据/批准降档--> DRAFTED
  PENDING  --额度耗尽--> BLOCKED
  任意态   --stage 条件开关--> ABSENT --开关回翻--> PENDING（门/组装/记账跳过，D 决策）
VERIFIED 只能来自真门 rc=0 的自动回写：
  章 VERIFIED = `gate` 批量跑章门 PASS 自动回写（geo bug-3049 手动 mark 禁用）；
  节 VERIFIED = 所属章门 PASS 时随章自动回写（两层模型改造点①——节无独立门，唯一通道同源），
  手动 mark --sections VERIFIED 一律拒绝（bug-3049 同构）。

批量记账原语（两层模型改造点④；bug-3048：单 run bash ≤25 次，节粒度下逐节单发必烧穿）：
  mark --sections ch6_S01,ch6_S02 DRAFTED   按波批量记账节集（原子——任一未知/非法全批拒绝）
  delivered --sections … --wave N           交付子代理按波回执（delivered 布尔 + 交付波次，D6）

退出码：0 成功 / 1 用法错误、非法状态转移、重复 init、未知章节或节、批量门有 FAIL。

平台预算规避（bug-3040/3048 移植）：gate 批量单章门（一次 bash 跑完全部 DRAFTED 章）；
run-stage freeze/finalize 把固定脚本序列合并为一次 bash 调用。700 页规模下停车点规约见 SKILL.md。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1

# finalize 的 consistency --standards 默认 = 技能规范索引（CC3 规范编号枚举门的真源；
# 缺文件时省略该旗标 → CC1/CC3 降为 manual，rc=2 由调用方按门拦语义处理）。
# coal-eia T1：references/standards_index.json 尚未落地（一期任务4），在册即自动启用。
STANDARDS_INDEX = Path(__file__).resolve().parent.parent / "references" / "standards_index.json"

# finalize 的 consistency --contracts 默认 = 技能合约注册表（T1b 改造点①条件激活门的真源；
# T4 并行会话维护，本脚本只读——在册即自动启用，缺文件时省略旗标，注册表门整体跳过）。
CONTRACTS_INDEX = Path(__file__).resolve().parent.parent / "references" / "consistency_contracts.json"

# 派发额度：700 页 ≈ 77+ 节派发（D10 规模约束），batch_task 分波是默认生存方式。
# 本脚本内预算只做展示与 WAVE1 路由提示；硬执行在 harness SubagentLimitMiddleware。
DISPATCH_BUDGET = 120

# 节 id 契约（stage JSON sections[].id 同形）：chNN_SNN——章前缀必须与所属章一致
SECTION_ID_RE = re.compile(r"^ch\d+_S\d+$")

TRANSITIONS: dict[str, set[str]] = {
    # PENDING→VERIFIED = gate 真跑门 PASS 自动补记（手动 mark VERIFIED 已禁用，bug-3049）
    "PENDING": {"DRAFTED", "VERIFIED", "BLOCKED", "ABSENT"},
    "DRAFTED": {"DRAFTED", "VERIFIED", "BLOCKED", "ABSENT"},  # DRAFTED→DRAFTED = 重派
    "VERIFIED": {"DRAFTED", "ABSENT"},  # 修改回路重写；条件开关翻出
    "BLOCKED": {"DRAFTED", "ABSENT"},  # 补数据/批准降档后复活
    # ABSENT：stage 条件开关驱动（双模式互换/可选章缺席），门/组装/记账跳过；开关回翻 → PENDING
    "ABSENT": {"PENDING"},
}


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


def section_sort_key(s: dict):
    m = re.match(r"^ch\d+_S(\d+)$", s.get("id", ""))
    return int(m.group(1)) if m else 99


def active_order(doc: dict) -> list[str]:
    """参与波次推导的章（ABSENT 章不占波、不派发、不跑门）。"""
    return [c for c in chapter_order(doc["chapters"]) if doc["chapters"][c]["status"] != "ABSENT"]


def iter_sections(doc: dict):
    """(章id, 节条目) 全量遍历。"""
    for c in chapter_order(doc["chapters"]):
        for s in doc["chapters"][c].get("sections", []):
            yield c, s


def find_section(doc: dict, sid: str) -> tuple[str, dict] | None:
    for c, s in iter_sections(doc):
        if s.get("id") == sid:
            return c, s
    return None


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
    act = active_order(doc)
    wave1 = act[:-1]
    wave2 = [act[-1]] if act else []
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


def _sections_line(ent: dict) -> str:
    """章内节状态摘要行（status 输出用）。"""
    secs = ent.get("sections", [])
    if not secs:
        return ""
    by: dict[str, int] = {}
    for s in secs:
        by[s.get("status", "?")] = by.get(s.get("status", "?"), 0) + 1
    delivered = sum(1 for s in secs if s.get("delivered"))
    tally = " ".join(f"{k} {v}" for k, v in sorted(by.items()))
    return f" 节[{len(secs)}] {tally} 已交付 {delivered}"


def _self_cmd(*extra: str) -> str:
    return "python -X utf8 " + str(Path(__file__).resolve()) + " " + " ".join(extra)


def next_action(doc: dict, state_dir: Path) -> str:
    phase = derive_phase(doc)
    chs = doc["chapters"]
    act = active_order(doc)
    wave1 = act[:-1]
    last = act[-1] if act else None
    sd = str(state_dir)
    lines = [f"PHASE: {phase}"]

    def pending_sections(ch_id: str) -> list[str]:
        return [s["id"] for s in chs[ch_id].get("sections", []) if s.get("status") in ("PENDING", "DRAFTED")]

    if phase == "WAVE1":
        drafted = [c for c in wave1 if chs[c]["status"] == "DRAFTED"]  # 先收口已起草的（批量一次跑完）
        if drafted:
            lines += [
                f"[NEXT] 批量跑门: {', '.join(drafted)}（DRAFTED——只信产物，不信子代理摘要；一次 bash 全部跑完，PASS 章自动转 VERIFIED）",
                f"命令: {_self_cmd('gate', '--state-dir', sd)}",
                "期望 rc: 0（GATE_BATCH_DONE passed=N failed=0，PASS 章及其全部节由 gate 自动转 VERIFIED）",
                '        1 → failed 章按 stderr 原文重派（原 prompt + stderr，每章 ≤1 次）；重派仍 FAIL → mark <chN> BLOCKED --gate FAIL --detail "<一句话差距>"',
            ]
            return "\n".join(lines)
        pending = [c for c in wave1 if chs[c]["status"] == "PENDING"]
        if doc.get("total_dispatches", 0) >= DISPATCH_BUDGET:
            lines += [
                f"[NEXT] 额度耗尽: 总派发 {doc.get('total_dispatches', 0)}/{DISPATCH_BUDGET}，剩余 PENDING 章 {pending}",
                f'动作: 逐章 progress.py mark <chN> BLOCKED --state-dir {sd} --detail "派发额度耗尽" → 进协商（或请用户新会话续跑，progress 无损）',
            ]
            return "\n".join(lines)
        c = pending[0]
        ps = pending_sections(c)
        lines += [
            f"[NEXT] 按波派发: {c}（PENDING，wave1 独立章；节级派发，D9 粒度分层）",
            f"动作: 按 SKILL.md 步骤4 派发契约组装 prompt（stage sections 要素链+范文索引+节级深度目标），batch_task 分波派子代理直写 state/sections/<节id>.md（每波 5–10 节）",
            f"约束: 每轮 ≤3 个并发 task()（超发被运行时静默丢弃）；子代理只回 ≤10 行摘要（含本节要点）",
            f"记账（批量原语，节粒度禁逐节单发——bug-3048）: progress.py mark --sections {','.join(ps[:5])}{'…' if len(ps) > 5 else ''} DRAFTED --state-dir {sd}",
            f"收口: 波内节稿拼章稿 state/chapters/{c}.md → mark {c} DRAFTED → gate（PASS 章与其全部节自动转 VERIFIED）",
        ]
        return "\n".join(lines)

    if phase == "NEGOTIATE":
        un = sorted({c for c, s in chs.items() if s["status"] == "BLOCKED"} - approved_set(doc))
        lines += [
            f"[NEXT] 协商: 未批准 BLOCKED: {', '.join(un)}",
            "动作: 组差距表（章/实际 eff/目标/缺口——取各章 gate_detail 与单章门 stderr）单表单 ask_clarification 三选项:",
            "  ① 补数据（回 ingest → formula_runner → 相关节 mark --sections … DRAFTED 重派）",
            f'  ② 批准降档（progress.py approve-downgrade --state-dir {sd} --chapters {",".join(un)} --note "<用户批准依据>"）',
            "  ③ [待确认] 收尾（缺数信号放宽覆盖缩放，重写即可能达标）",
            "期望: 用户答复后才推进（单回合至多一次 ask_clarification；挂起即停，不推进）",
        ]
        return "\n".join(lines)

    if phase == "KEY_POINTS":
        lines += [
            "[NEXT] 要点包: wave1 已收口，蒸馏 state/key_points.json",
            "动作: 聚合各子代理摘要的「本节要点」+ formula_state 关键值（产能/沉陷预测/容量/水量平衡等冻结值）",
            '      写 state/key_points.json: {"chapters":{"ch1":[...],...},"highlights":{...},"issues":[...]}',
            f"      单表单 ask_clarification 呈现用户确认 → progress.py confirm-key-points --state-dir {sd}",
            "要点包 = ch13 结论章唯一事实来源（不重读 wave1 全文）",
        ]
        return "\n".join(lines)

    if phase == "WAVE2":
        if chs[last]["status"] == "DRAFTED":
            lines += [
                f"[NEXT] 跑门: {last}（DRAFTED，wave2 结论章——同款批量 gate 命令）",
                f"命令: {_self_cmd('gate', '--state-dir', sd)}",
                "期望 rc: 同 WAVE1 批量跑门分支（PASS→章与节 VERIFIED / FAIL→重派 ≤1 次→BLOCKED）",
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
            "期望 rc: 0 → stdout 含 BUILD_READY/MANIFEST_READY（整行+退出码原样粘贴进回复）→ 交付（项目路径=交付子代理分波逐节 write_chapter；独立路径=present_files）",
            "        consistency rc=3（WARN/MANUAL 透传）→ 逐条汇报用户后交付；rc=1/2 → stderr 原样呈现，修章重跑",
        ]
        return "\n".join(lines)
    lines += [
        "[NEXT] 终验: 全部章节 VERIFIED",
        f"命令: {gate_cmd}",
        "说明: run-stage finalize 一次 bash 完成 build_output → consistency.py → snapshot.py save（交付名由脚本从 data/ 拼，stdout 原样透传）",
        "期望 rc: 0 → stdout 含 BUILD_READY/MANIFEST_READY（整行+退出码原样粘贴进回复）→ 交付（项目路径=交付子代理分波逐节 write_chapter；独立路径=present_files）",
        "        consistency rc=3（WARN/MANUAL 透传）→ 逐条汇报用户后交付；rc=1/2 → stderr 原样呈现，修章重跑",
    ]
    return "\n".join(lines)


def _blank_section(s: dict) -> dict:
    return {"id": s["id"], "title": s.get("title", ""), "status": "PENDING", "dispatches": 0, "delivered": False}


def cmd_init(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    p = state_dir / "progress.json"
    if p.exists():
        print(f"[progress] {p} 已存在——续跑请用 next/status，勿重复 init 抹掉进度", file=sys.stderr)
        return EXIT_ERROR
    stage = json.loads(Path(args.stage).read_text(encoding="utf-8"))
    # 节 id 契约校验（stage sections 与 progress 解析的接口契约，T1 骨架即生效）：
    # id 形状 chNN_SNN、章前缀与所属章一致、章内唯一。
    chapters: dict = {}
    n_sections = 0
    for c in chapter_order(stage.get("chapters", {})):
        ch = stage["chapters"][c]
        seen: set[str] = set()
        sections: list[dict] = []
        for s in ch.get("sections", []):
            sid = s.get("id", "")
            if not SECTION_ID_RE.match(sid):
                print(f"[progress] {c} 节 id 非法: {sid!r}（契约形 chNN_SNN，与章 {c} 同前缀）", file=sys.stderr)
                return EXIT_ERROR
            if not sid.startswith(c + "_S"):
                print(f"[progress] 节 {sid} 前缀与所属章 {c} 不一致（stage JSON 结构错误）", file=sys.stderr)
                return EXIT_ERROR
            if sid in seen:
                print(f"[progress] 节 {sid} 在 {c} 内重复（stage JSON 结构错误）", file=sys.stderr)
                return EXIT_ERROR
            seen.add(sid)
            sections.append(_blank_section(s))
        sections.sort(key=section_sort_key)
        n_sections += len(sections)
        chapters[c] = {
            "status": "PENDING",
            "dispatches": 0,
            "last_gate": None,
            "gate_detail": "",
            "blocked_reason": None,
            "sections": sections,
        }
    doc = {
        "stage_path": str(Path(args.stage).resolve()),
        "data_dir": str(Path(args.data_dir).resolve()) if args.data_dir else None,
        "phase": "WAVE1",
        "total_dispatches": 0,
        "chapters": chapters,
        "key_points_confirmed": False,
        "downgrade_approvals": [],
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    save(state_dir, doc)
    n = len(doc["chapters"])
    print(f"PROGRESS_INIT: {n} 章 {n_sections} 节全部 PENDING（{', '.join(doc['chapters'])}）→ 下一步 progress.py next")
    return EXIT_OK


def cmd_next(args: argparse.Namespace) -> int:
    doc = load(Path(args.state_dir))
    print(next_action(doc, Path(args.state_dir)))
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    doc = load(Path(args.state_dir))
    total_sections = sum(len(e.get("sections", [])) for e in doc["chapters"].values())
    verified_sections = sum(1 for _, s in iter_sections(doc) if s.get("status") == "VERIFIED")
    delivered_sections = sum(1 for _, s in iter_sections(doc) if s.get("delivered"))
    print(
        f"phase={derive_phase(doc)} 总派发={doc.get('total_dispatches', 0)}/{DISPATCH_BUDGET} 要点包确认={doc.get('key_points_confirmed', False)} "
        f"节 VERIFIED {verified_sections}/{total_sections} 已交付 {delivered_sections}"
    )
    for c in chapter_order(doc["chapters"]):
        s = doc["chapters"][c]
        extra = f" reason={s['blocked_reason']}" if s.get("blocked_reason") else ""
        print(f"  {c}: {s['status']} 派发{s.get('dispatches', 0)} 门={s.get('last_gate')}{_sections_line(s)}{extra}")
    return EXIT_OK


def cmd_mark(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    status = args.status
    if bool(args.sections) == bool(args.chapter):
        print("[progress] 用法: mark <chN> <status>（章）或 mark --sections <csv> <status>（节批量）——二选一", file=sys.stderr)
        return EXIT_ERROR
    if status == "VERIFIED":
        # bug-3049 定案（节级同构，两层模型改造点②）：--gate PASS 是调用方自证（自申报），
        # 非官方凭据——VERIFIED 一律拒绝手动 mark。唯一合法通道 = progress.py gate
        # （内部真跑 build_output.run_chapter_gate，PASS 章自动回写 VERIFIED 并随章回写全部节）。
        who = f"--sections {args.sections}" if args.sections else args.chapter
        print(f"[progress] {who} 手动 mark VERIFIED 已禁用（--gate PASS 是自证，bug-3049）——节 VERIFIED 唯一通道 = 所属章 `progress.py gate` 真跑章门 rc=0 自动回写", file=sys.stderr)
        return EXIT_ERROR
    if status not in TRANSITIONS:
        print(f"[progress] mark 只接受 {'/'.join(TRANSITIONS)}（收到 {status}）", file=sys.stderr)
        return EXIT_ERROR

    # ── 节批量记账（两层模型改造点④：原子批量——任一未知/非法全批拒绝，bug-3048）──
    if args.sections:
        wanted = list(dict.fromkeys(x.strip() for x in args.sections.split(",") if x.strip()))  # 去重保序——重复 id 不重复记账
        if not wanted:
            print("[progress] --sections 为空", file=sys.stderr)
            return EXIT_ERROR
        resolved: list[tuple[str, dict]] = []
        unknown: list[str] = []
        for sid in wanted:
            hit = find_section(doc, sid)
            if hit is None:
                unknown.append(sid)
                continue
            resolved.append(hit)
        if unknown:
            inbook = [s.get("id") for _, s in iter_sections(doc)]
            print(f"[progress] 未知节 {unknown}（在册 {len(inbook)} 节，如 {inbook[:8]}…）", file=sys.stderr)
            return EXIT_ERROR
        illegal: list[str] = []
        for sid, (ch, ent) in zip(wanted, resolved):
            if status not in TRANSITIONS[ent["status"]]:
                illegal.append(f"{sid}: {ent['status']} → {status}")
        if illegal:
            print(f"[progress] 非法转移（批量原子拒绝，全批未动）: {'; '.join(illegal)}", file=sys.stderr)
            return EXIT_ERROR
        for sid, (ch, ent) in zip(wanted, resolved):
            ent["status"] = status
            if status == "DRAFTED":
                ent["dispatches"] = ent.get("dispatches", 0) + 1
                doc["total_dispatches"] = doc.get("total_dispatches", 0) + 1
            elif status == "BLOCKED":
                ent["note"] = args.detail or "节 BLOCKED"
            elif status == "ABSENT":
                ent["note"] = args.detail or "stage 条件开关驱动缺席"
            elif status == "PENDING":
                ent.pop("note", None)  # 开关回翻复位
        doc["phase"] = derive_phase(doc)
        save(state_dir, doc)
        print(f"MARKED_SECTIONS: {len(wanted)} 节 → {status}（{', '.join(wanted)}；phase={doc['phase']}）")
        return EXIT_OK

    # ── 章记账（geo 语义 + ABSENT）──
    ch_id = args.chapter
    if ch_id not in doc["chapters"]:
        print(f"[progress] 未知章节 {ch_id}（在册: {chapter_order(doc['chapters'])}）", file=sys.stderr)
        return EXIT_ERROR
    cur = doc["chapters"][ch_id]["status"]
    if status not in TRANSITIONS[cur]:
        print(f"[progress] 非法转移 {ch_id}: {cur} → {status}（合法: {cur} → {sorted(TRANSITIONS[cur])}）", file=sys.stderr)
        return EXIT_ERROR
    ent = doc["chapters"][ch_id]
    ent["status"] = status
    if status == "DRAFTED":
        ent["dispatches"] = ent.get("dispatches", 0) + 1
        doc["total_dispatches"] = doc.get("total_dispatches", 0) + 1
        ent["last_gate"] = None
        ent["gate_detail"] = ""
        ent["blocked_reason"] = None
    elif status == "BLOCKED":
        ent["last_gate"] = args.gate or "FAIL"
        ent["gate_detail"] = args.detail or ""
        ent["blocked_reason"] = args.detail or ("门 FAIL 且重派耗尽" if args.gate != "PASS" else "派发额度耗尽")
    elif status == "ABSENT":
        # stage 条件开关驱动（双模式互换/可选章缺席）：章 ABSENT 级联其全部节 ABSENT
        #（门/组装/记账跳过同语义，两层状态模型）；开关回翻逐节 PENDING 复位（章内节状态按节回翻）。
        cascaded = 0
        for s in ent.get("sections", []):
            if s.get("status") != "ABSENT":
                s["status"] = "ABSENT"
                s["note"] = args.detail or f"章 {ch_id} 条件开关缺席级联"
                cascaded += 1
        ent["blocked_reason"] = args.detail or "stage 条件开关驱动缺席"
        doc["phase"] = derive_phase(doc)
        save(state_dir, doc)
        extra = f"，级联节 ABSENT {cascaded}" if cascaded else ""
        print(f"MARKED: {ch_id} {cur} → ABSENT（phase={doc['phase']}{extra}）")
        return EXIT_OK
    else:  # PENDING（ABSENT 开关回翻——章回 PENDING，节按节回翻）
        ent["last_gate"] = None
        ent["gate_detail"] = ""
        ent["blocked_reason"] = None
        flipped = 0
        for s in ent.get("sections", []):
            if s.get("status") == "ABSENT":
                s["status"] = "PENDING"
                s.pop("note", None)
                flipped += 1
        doc["phase"] = derive_phase(doc)
        save(state_dir, doc)
        extra = f"，级联节回 PENDING {flipped}" if flipped else ""
        print(f"MARKED: {ch_id} {cur} → PENDING（phase={doc['phase']}{extra}）")
        return EXIT_OK
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"MARKED: {ch_id} {cur} → {status}（phase={doc['phase']}）")
    return EXIT_OK


def _writeback_sections(doc: dict, ch_id: str) -> list[str]:
    """章门 PASS 自动回写节 VERIFIED（两层模型改造点②）：章作为门对象整体过门，
    其全部节随章转 VERIFIED（PENDING/DRAFTED→VERIFIED）；ABSENT 保持缺席；
    BLOCKED 节属罕见中间态，留原状由调用方 stderr 提示。返回未推进节 id。"""
    skipped: list[str] = []
    for s in doc["chapters"][ch_id].get("sections", []):
        if s.get("status") in ("PENDING", "DRAFTED"):
            s["status"] = "VERIFIED"
        elif s.get("status") == "BLOCKED":
            skipped.append(s.get("id", "?"))
    return skipped


def cmd_gate(args: argparse.Namespace) -> int:
    """批量单章门（平台预算规避，bug-3040/3048）：一次 bash 跑完全部指定章的门禁，
    PASS 章当场自动转 VERIFIED，并随章回写其全部节 VERIFIED（两层模型改造点②——
    节 VERIFIED 唯一通道，不变式不破：推进凭据就是 run_chapter_gate 无异常返回，
    progress.py 仍是 progress.json 唯一写者）。任一章 FAIL → stderr 打该章完整差距，
    不推进该章，rc=1。"""
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
        except OSError as e:
            # coal-eia T1：冻结层缺失（formula_state.json 不存在）等文件级错误按该章门 FAIL 处理，
            # 不让 OSError 逃出批量门砸掉整批（geo 同路径会裸崩——两层模型下步骤2 先于步骤4 不再是隐含前提）。
            failed.append(ch)
            print(f"CHAPTER_GATE_FAIL: {ch}\n文件级错误（冻结层/章稿缺失？先跑 run-stage freeze 或补齐产物）: {e}", file=sys.stderr)
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
        # 章门 PASS → 随章回写节 VERIFIED（唯一通道，改造点②）
        sec_skipped = _writeback_sections(doc, ch)
        if sec_skipped:
            print(f"[progress] {ch} 门过但节未推进（BLOCKED 节须先 mark --sections … DRAFTED 复活）: {sec_skipped}", file=sys.stderr)
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"GATE_BATCH_DONE: passed={len(passed) - len(skipped)} failed={len(failed)}（failed: {', '.join(failed) or '无'}；skipped: {', '.join(skipped) or '无'}——stderr 逐条差距，原 prompt 重派 ≤1 次）")
    if skipped:
        print(f"[progress] 门过但未推进（状态机不允许直接 {skipped}；先 mark DRAFTED 复活）: {skipped}", file=sys.stderr)
    return EXIT_ERROR if failed else EXIT_OK


def cmd_delivered(args: argparse.Namespace) -> int:
    """交付回执（D6）：交付子代理每波（≤5–10 节）write_chapter 后一次批量回执——
    节粒度禁逐节单发（bug-3048）。只接受 VERIFIED 节（交付起点=一致性 PASS 后，
    VERIFIED 是章门产物）；重复回执幂等（delivered 已真则 no-op）。"""
    state_dir = Path(args.state_dir)
    doc = load(state_dir)
    wanted = [x.strip() for x in args.sections.split(",") if x.strip()]
    if not wanted:
        print("[progress] --sections 为空", file=sys.stderr)
        return EXIT_ERROR
    resolved: list[tuple[str, dict]] = []
    unknown: list[str] = []
    for sid in wanted:
        hit = find_section(doc, sid)
        if hit is None:
            unknown.append(sid)
            continue
        resolved.append(hit)
    if unknown:
        print(f"[progress] 未知节 {unknown}", file=sys.stderr)
        return EXIT_ERROR
    not_verified = [f"{sid}({ent['status']})" for sid, (ch, ent) in zip(wanted, resolved) if ent["status"] != "VERIFIED"]
    if not_verified:
        print(f"[progress] 交付回执拒绝（仅 VERIFIED 节可交付，原子全批拒绝）: {'; '.join(not_verified)}", file=sys.stderr)
        return EXIT_ERROR
    fresh = 0
    for sid, (ch, ent) in zip(wanted, resolved):
        if not ent.get("delivered"):
            ent["delivered"] = True
            ent["delivery_wave"] = args.wave
            fresh += 1
    doc["phase"] = derive_phase(doc)
    save(state_dir, doc)
    print(f"DELIVERED_BATCH: wave={args.wave} fresh={fresh} idempotent={len(wanted) - fresh}（{', '.join(wanted)}）")
    return EXIT_OK


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
    if CONTRACTS_INDEX.exists():
        cons_args += ["--contracts", str(CONTRACTS_INDEX)]
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
        "--mapping",
        str(state_dir / "mapping.json"),
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
    p = argparse.ArgumentParser(description="coal-eia-report v2 — 两层状态机（章级门禁 × 节级派发，步骤4 控制器）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("init", help="按 stage 章节清单初始化 progress.json（章+节子表全 PENDING；已存在=续跑拒重置）")
    sp.add_argument("--stage", required=True)
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--data-dir", help="记录数据目录（next 渲染精确命令用；缺省输出 <DATA> 占位）")
    sp.set_defaults(fn=cmd_init)
    sp = sub.add_parser("next", help="控制器每轮先读：恰好一个下一步动作 + 精确命令 + 期望 rc")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_next)
    sp = sub.add_parser("status", help="全章状态表（含节子表计数）+ 派发计数 + 额度余量")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser("mark", help="状态转移（DRAFTED/BLOCKED/ABSENT/PENDING）；VERIFIED 禁手动（唯一通道=gate）。章: mark <chN> <status>；节批量: mark --sections <csv> <status>（bug-3048 批量原语）")
    sp.add_argument("chapter", nargs="?", help="章 id（与 --sections 二选一）")
    sp.add_argument("status")
    sp.add_argument("--sections", help="节 id 逗号清单批量记账（原子——任一未知/非法全批拒绝），如 ch6_S01,ch6_S02")
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--gate", choices=["PASS", "FAIL"])
    sp.add_argument("--detail", default="")
    sp.set_defaults(fn=cmd_mark)
    sp = sub.add_parser("gate", help="批量单章门：一次跑完全部（缺省）或指定章的门禁，PASS 章自动转 VERIFIED 并随章回写节 VERIFIED（两层模型改造点②——VERIFIED 唯一通道）")
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--chapters", help="逗号分隔，如 ch2,ch3；缺省=全部 DRAFTED 章")
    sp.add_argument("--targets", help="depth_targets.json 路径；仅调试，正式跑门绝不传（同 build_output 语义）")
    sp.set_defaults(fn=cmd_gate)
    sp = sub.add_parser("delivered", help="交付回执：交付子代理按波批量回执节 delivered 布尔+交付波次（仅 VERIFIED 节；幂等；bug-3048 批量原语）")
    sp.add_argument("--sections", required=True, help="节 id 逗号清单，如 ch1_S01,ch1_S02")
    sp.add_argument("--wave", type=int, required=True, help="交付波次（D6 分波回执）")
    sp.add_argument("--state-dir", required=True)
    sp.set_defaults(fn=cmd_delivered)
    sp = sub.add_parser("run-stage", help="固定脚本序列合并一次 bash：freeze=manifest+execute；finalize=build→consistency→snapshot")
    sp.add_argument("stage_name", choices=["freeze", "finalize"])
    sp.add_argument("--state-dir", required=True)
    sp.add_argument("--outputs-dir", help="finalize 必填：交付目录（报告+project_snapshot.json 落这里）")
    sp.add_argument("--task", default="环评报告终验", help="snapshot last_task 一句话摘要")
    sp.add_argument("--allow-partial", action="store_true", help="强制分级交付（已批准降档时自动启用，无需显式传）")
    sp.set_defaults(fn=cmd_run_stage)
    sp = sub.add_parser("confirm-key-points", help="要点包已经用户单表单确认（解锁 ch13 结论章）")
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
