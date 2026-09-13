#!/usr/bin/env python3
"""geological-report v2 — snapshot.py：project_snapshot.json 读写器（跨轮承接 + 版本历史）。

water 版改造（差异有意非漂移，见 TODOS.md 三副本同步约定）：
  1. --state 语义改为 **state_manifest_path**（data/state_manifest.json——v2 的 data/
     唯一写者清单）；formula_state 由 --formula-state 单独存路径。
  2. save 增加 **hash 清单**：对 data/state_manifest.json + state/* 逐文件 SHA-256——
     show --verify 时逐一复算，mismatch → exit 3（篡改/半更新检测，步骤0 完整性门）。
  3. show --input 必填（无默认路径——沙箱布局不定，默认路径是隐性耦合）。
  4. 正典文件名守卫（bug-2198）：只允许写 project_snapshot.json。

用法：
  python snapshot.py save \
    --task "把小体重 D 从 2.85 改成 2.90 重算资源量" \
    --state-manifest /mnt/user-data/workspace/data/state_manifest.json \
    --formula-state /mnt/user-data/workspace/state/formula_state.json \
    --manifest /mnt/user-data/workspace/state/chapter_manifest.json \
    --report /mnt/user-data/outputs/勘探报告.md \
    --diff '{"13a:体重_t_m3":{"old":"2.85","new":"2.90"}}' \
    --affected '{"formulas":["L7","L9"],"chapters":["ch1","ch4","ch8","ch9","ch10","compliance_appendix"]}' \
    --output /mnt/user-data/workspace/project_snapshot.json
  → SNAPSHOT_READY: version=2 last_task=...
  python snapshot.py show --input .../project_snapshot.json [--verify]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

EXIT_OK, EXIT_ERROR, EXIT_TAMPERED = 0, 1, 3


def _now_iso() -> str:
    try:
        import datetime
        return datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        return "unknown"


def _load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # 损坏 → 降级全新（步骤0 try/except 不崩）
        return {}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_manifest(data_dir: Path | None, state_dir: Path | None) -> dict[str, str]:
    """data/state_manifest.json + state/** 逐文件 SHA-256（相对路径 → hash）。"""
    out: dict[str, str] = {}
    for base, prefix in ((data_dir, "data/"), (state_dir, "state/")) if data_dir or state_dir else ():
        base = Path(base) if base else None
        if not base or not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                out[prefix + p.relative_to(base).as_posix()] = sha256_file(p)
    return out


def _maybe_path(v: str | None) -> str | None:
    return str(Path(v).resolve()) if v else None


def cmd_save(args: argparse.Namespace) -> int:
    out = Path(args.output)
    # bug-2198 守卫：快照只有正典文件名，禁止旁路 project_snapshot_N5.json
    if out.name != "project_snapshot.json":
        print(f"SNAPSHOT_ERROR: 快照必须写入正典文件 project_snapshot.json，收到: {out.name}（bug-2198 守卫）")
        return EXIT_ERROR
    prev = _load_existing(out)
    try:
        prev_version = int(prev.get("version", 0) or 0)
    except (TypeError, ValueError):
        prev_version = 0
    new_version = prev_version + 1

    changelog = list(prev.get("changelog", []) or prev.get("change_log", []) or [])
    entry = {"version": new_version, "task": args.task, "timestamp": _now_iso()}
    for opt_key, cli_val in (("value_diffs", args.diff), ("affected", args.affected), ("note", args.note), ("standards_selected", args.standards)):
        if not cli_val:
            continue
        try:
            entry[opt_key] = json.loads(cli_val)
        except Exception:
            entry[f"{opt_key}_raw"] = cli_val
    changelog.append(entry)

    snap = {
        "version": new_version,
        "last_task": args.task,  # ⬅ 防漂移锚点：下一轮启动读此字段决定「当前任务」
        "created_at": prev.get("created_at") or entry["timestamp"],
        "updated_at": entry["timestamp"],
        "stage": args.stage or prev.get("stage"),
        "data_dir": _maybe_path(args.data_dir) or prev.get("data_dir"),
        "state_dir": _maybe_path(args.state_dir) or prev.get("state_dir"),
        "state_manifest_path": _maybe_path(args.state_manifest) or prev.get("state_manifest_path"),
        "formula_state_path": _maybe_path(args.formula_state) or prev.get("formula_state_path"),
        "chapter_manifest_path": _maybe_path(args.manifest) or prev.get("chapter_manifest_path"),
        "report_path": _maybe_path(args.report) or prev.get("report_path"),
        "changelog": changelog,
        "change_log": changelog,  # 兼容旧字段名
        "file_hashes": hash_manifest(_maybe_path(args.data_dir), _maybe_path(args.state_dir)),
    }
    if snap["file_hashes"]:
        entry["file_count"] = len(snap["file_hashes"])

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SNAPSHOT_READY: version={new_version} last_task={args.task} path={out}")
    print(f"SNAPSHOT_FILE: {out}")
    print(f"SNAPSHOT_HASHES: {len(snap['file_hashes'])} files")
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    snap = _load_existing(Path(args.input))
    if not snap:
        print("SNAPSHOT_NONE: 无快照，全新运行")
        return EXIT_OK
    print(f"SNAPSHOT_VERSION: {snap.get('version', '?')}")
    print(f"SNAPSHOT_STAGE: {snap.get('stage', '?')}")
    print(f"SNAPSHOT_LAST_TASK: {snap.get('last_task', '(无)')}")
    print(f"SNAPSHOT_REPORT: {snap.get('report_path', '(无)')}")
    cl = snap.get("changelog") or snap.get("change_log") or []
    if cl:
        last = cl[-1]
        print(f"SNAPSHOT_LAST_CHANGE: v{last.get('version')} {last.get('task', '')}")
    if not args.verify:
        return EXIT_OK
    # 完整性校验（步骤0）：逐文件复算 hash；mismatch/缺失 → exit 3
    hashes = snap.get("file_hashes") or {}
    if not hashes:
        print("SNAPSHOT_VERIFY: 无 hash 清单（旧版本快照）——跳过")
        return EXIT_OK
    bad = []
    for rel, want in sorted(hashes.items()):
        base = snap.get("data_dir") if rel.startswith("data/") else snap.get("state_dir")
        p = Path(base) / rel.split("/", 1)[1] if base else None
        if not p or not p.exists():
            bad.append(f"{rel}: 缺失")
        elif sha256_file(p) != want:
            bad.append(f"{rel}: hash-mismatch")
    if bad:
        print(f"SNAPSHOT_TAMPERED: {len(bad)}/{len(hashes)} 文件不符——数据在快照后被旁改（D10 唯一写者被绕过？）")
        for b in bad[:10]:
            print(f"  {b}")
        return EXIT_TAMPERED
    print(f"SNAPSHOT_VERIFIED: {len(hashes)} files intact")
    return EXIT_OK


def main() -> int:
    p = argparse.ArgumentParser(description="geological-report v2 — project_snapshot.json 读写")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("save", help="读旧快照→version++→追加 changelog→写回（带 hash 清单）")
    s.add_argument("--task", required=True, help="本轮用户指令一句话摘要（写入 last_task）")
    s.add_argument("--stage", default=None, help="勘探/详查/普查")
    s.add_argument("--data-dir", default=None, help="data/ 目录（hash 清单范围）")
    s.add_argument("--state-dir", default=None, help="state/ 目录（hash 清单范围）")
    s.add_argument("--state-manifest", default=None, help="data/state_manifest.json 路径")
    s.add_argument("--formula-state", default=None, help="state/formula_state.json 路径")
    s.add_argument("--manifest", default=None, help="state/chapter_manifest.json 路径")
    s.add_argument("--report", default=None, help="主报告输出路径")
    s.add_argument("--standards", default=None, help="选中规范 JSON 数组字符串")
    s.add_argument("--diff", default=None, help="改参值差 JSON")
    s.add_argument("--affected", default=None, help="受影响公式/章节 JSON")
    s.add_argument("--note", default=None)
    s.add_argument("--output", required=True)
    s.set_defaults(func=cmd_save)

    sh = sub.add_parser("show", help="打印锚点摘要；--verify 逐文件 hash 复算")
    sh.add_argument("--input", required=True, help="project_snapshot.json 路径（必填，无默认）")
    sh.add_argument("--verify", action="store_true", help="复算 file_hashes（mismatch → exit 3）")
    sh.set_defaults(func=cmd_show)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
