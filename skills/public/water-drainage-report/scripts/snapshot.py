#!/usr/bin/env python3
"""project_snapshot.json 读写器（反馈7 跨轮承接 + 版本历史）。

为什么需要这个脚本（2026-08-13 页面验证根因）：
SKILL.md 多处引用 project_snapshot.json（standards_selected / change_log /
报告顶部变更块），但**从未给出具体写盘命令**，agent 因此从不创建它 → 第 2 轮
改参时无"当前任务"锚点 → 被线程首条消息漂移回"重新生成整篇"（bug-1171）。
本脚本把"读旧快照 → version++ → 追加 changelog → 写回"做成 canonical CLI，
agent 只需一句 `snapshot.py save --task ...` 即可固化，避免内联 python 写坏。

stdlib only（json/argparse/pathlib/subprocess）——不 import backend/harness，
对容器挂载布局稳健（与 formula_runner.py 不同，无 _resolve_backend 依赖）。

用法：
  python snapshot.py save \
    --task "把 Q 从 20000 改成 25000 做方案比选" \
    --params /mnt/user-data/workspace/params.json \
    --state /mnt/user-data/workspace/formula_state.json \
    --manifest /mnt/user-data/workspace/chapter_manifest.json \
    --report /mnt/user-data/outputs/循环水装置给排水计算书.md \
    --standards '["GB/T 50746-2012","GB 50648-2011","GB/T 50050-2017"]' \
    --diff '{"Q":{"old":20000,"new":25000}}' \
    --output /mnt/user-data/workspace/project_snapshot.json

  → 读旧快照（若在）→ version = prev+1 → 追加 changelog → 写回
  → stdout: `SNAPSHOT_READY: version=2 last_task=把 Q...`
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _now_iso() -> str:
    """容器内 date -Iseconds；失败回落 'unknown'（不崩）。"""
    try:
        return subprocess.check_output(["date", "-Iseconds"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def _load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        # 损坏 → 降级全新（与 SKILL 步骤0 一致：try/except 不崩）
        return {}


def _maybe_load_json_file(p: str | None) -> object | None:
    if not p:
        return None
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def cmd_save(args: argparse.Namespace) -> int:
    out = Path(args.output)
    # bug-2198 守卫：快照只有正典文件名。禁止 save 到旁路文件（如 project_snapshot_N5.json）——
    # 旁路快照会让正典锚点停留在旧版本，下一轮 show 读到旧 last_task，bug-1171 漂移复活。
    if out.name != "project_snapshot.json":
        print(f"SNAPSHOT_ERROR: 快照必须写入正典文件 project_snapshot.json，收到: {out.name}（bug-2198 守卫）")
        return 1

    # R8 守卫（快照门禁）：agent 手写公式折叠块 + 跳过 inject（文本铁律压不住 flash 模型）。
    # save 是交付前必经步骤，在这里把「未注入」打回，agent 才会回头走占位符+inject 正道。
    # R9 升级：签名带块数（v2），比对「签名数之和 == <details> 总数」——抓"注入了但又在
    # 别处手写折叠块"的混合违约（R9 实测 ch6-8 手写 8 块，且 V_ratio 单位抄错成 0.202 h）。
    if args.report:
        rp = Path(args.report)
        if rp.exists():
            rtext = rp.read_text(encoding="utf-8")
            _MARKER = "<!-- CALC_BLOCKS -->"
            _SIG_RE = re.compile(r"CALC_BLOCKS_INJECTED:v2 count=(\d+)")  # 与 render_calc_blocks.py SIGNATURE_PREFIX 同步
            if _MARKER in rtext:
                print(f"SNAPSHOT_ERROR: 报告仍含未注入占位符 {_MARKER}——先运行 render_calc_blocks.py inject 再 save（R8 守卫）")
                return 1
            _injected = [int(m) for m in _SIG_RE.findall(rtext)]
            _details = rtext.count("<details>")
            if "<details>" in rtext and not _injected:
                print("SNAPSHOT_ERROR: 报告含手写 <details> 计算过程块但缺脚本注入签名 CALC_BLOCKS_INJECTED:v2——禁止手写公式块；删除手写块，改回占位符后运行 render_calc_blocks.py inject（R8 守卫）")
                return 1
            if _injected and sum(_injected) != _details:
                print(f"SNAPSHOT_ERROR: 报告 <details> 共 {_details} 块，但脚本注入签名合计 {sum(_injected)} 块——多出的手写折叠块/被删注入块必须清除：正文只保留注入块，其余计算叙述去 <details> 化（R9 守卫）")
                return 1
            # R11 守卫（正向）：R8/R9 只防「注入后又手写」，b2117e88 实测 agent 整份手写报告
            # （0 details + 0 占位符 + 0 签名）三项全过穿透交付。save 是交付必经点，在这里
            # 正向要求「必须有注入产物」：仍含 per-formula 占位符 = 忘 inject；连签名都没有 =
            # 整个 inject 被跳过。打回后 agent 只能走 占位符 + render_calc_blocks.py inject 正道。
            if "<!-- CALC:" in rtext:
                print("SNAPSHOT_ERROR: 报告仍含未注入占位符 <!-- CALC:公式id -->——先运行 render_calc_blocks.py inject 再 save（R11 守卫）")
                return 1
            if not _injected:
                print(
                    "SNAPSHOT_ERROR: 报告无脚本注入签名 CALC_BLOCKS_INJECTED:v2——计算折叠块整批缺失（手写报告/跳过 inject）。"
                    "打回：计算节每公式小节写 <!-- CALC:id --> 占位符（id 取自 traces.json，禁写 <details>/$$）后运行 render_calc_blocks.py inject，再 save（R11 守卫）"
                )
                return 1
    prev = _load_existing(out)
    prev_version = prev.get("version", 0) or 0
    try:
        prev_version = int(prev_version)
    except (TypeError, ValueError):
        prev_version = 0
    new_version = prev_version + 1

    # params：优先 --params 文件内容，其次保留旧值，最后 {}
    params = _maybe_load_json_file(args.params)
    if params is None:
        # bug-2203：--params 显式指定但文件缺失 → 大声警告（锚点参数回显降级）
        if args.params:
            print(f"SNAPSHOT_WARN: --params 文件不存在（{args.params}），快照 params 将回退旧值/为空——先补写 params.json 再 save", flush=True)
        params = prev.get("params", {})

    standards = json.loads(args.standards) if args.standards else prev.get("standards_selected", [])

    # changelog：保留旧条目 + 追加本轮
    changelog = list(prev.get("changelog", []) or prev.get("change_log", []) or [])
    entry = {
        "version": new_version,
        "task": args.task,
        "timestamp": _now_iso(),
    }
    if args.diff:
        try:
            entry["value_diffs"] = json.loads(args.diff)
        except Exception:
            entry["value_diffs_raw"] = args.diff
    if args.affected:
        entry["affected"] = args.affected
    if args.note:
        entry["note"] = args.note
    changelog.append(entry)

    snap = {
        "version": new_version,
        "last_task": args.task,  # ⬅ 反馈7 防漂移锚点：第 2 轮启动读此字段决定"当前任务"
        "created_at": prev.get("created_at") or entry["timestamp"],
        "updated_at": entry["timestamp"],
        "params": params,
        "formula_state_path": args.state or prev.get("formula_state_path") or prev.get("formula_state"),
        "chapter_manifest_path": args.manifest or prev.get("chapter_manifest_path") or prev.get("chapter_manifest"),
        "standards_selected": standards,
        "report_path": args.report or prev.get("report_path"),
        "changelog": changelog,
        # 兼容旧字段名（SKILL.md 历史 reference 用 change_log）
        "change_log": changelog,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SNAPSHOT_READY: version={new_version} last_task={args.task} path={out}")
    print(f"SNAPSHOT_FILE: {out}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """打印一行锚点摘要（供 agent 启动时快速读当前任务，不必解析整份 JSON）。"""
    snap = _load_existing(Path(args.input))
    if not snap:
        print("SNAPSHOT_NONE: 无快照，全新运行")
        return 0
    print(f"SNAPSHOT_VERSION: {snap.get('version', '?')}")
    print(f"SNAPSHOT_LAST_TASK: {snap.get('last_task', '(无)')}")
    print(f"SNAPSHOT_REPORT: {snap.get('report_path', '(无)')}")
    cl = snap.get("changelog") or snap.get("change_log") or []
    if cl:
        last = cl[-1]
        print(f"SNAPSHOT_LAST_CHANGE: v{last.get('version')} {last.get('task', '')}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="project_snapshot.json 读写（反馈7）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("save", help="读旧快照→version++→追加 changelog→写回")
    s.add_argument("--task", required=True, help="本轮用户指令的一句话摘要（写入 last_task）")
    s.add_argument("--params", default=None, help="params.json 路径（内容嵌入快照）")
    s.add_argument("--state", default=None, help="formula_state.json 路径（存路径不存内容）")
    s.add_argument("--manifest", default=None, help="chapter_manifest.json 路径")
    s.add_argument("--report", default=None, help="主报告输出路径")
    s.add_argument("--standards", default=None, help="选中规范 JSON 数组字符串")
    s.add_argument("--diff", default=None, help='改参值差 JSON，如 \'{"Q":{"old":20000,"new":25000}}\'')
    s.add_argument("--affected", default=None, help="受影响公式/章节描述（反馈6）")
    s.add_argument("--note", default=None, help="额外备注")
    s.add_argument("--output", default="/mnt/user-data/workspace/project_snapshot.json")
    s.set_defaults(func=cmd_save)

    sh = sub.add_parser("show", help="打印快照锚点摘要（version/last_task/last_change）")
    sh.add_argument("--input", default="/mnt/user-data/workspace/project_snapshot.json")
    sh.set_defaults(func=cmd_show)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
