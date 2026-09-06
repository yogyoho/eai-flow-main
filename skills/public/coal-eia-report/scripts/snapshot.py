#!/usr/bin/env python3
"""coal-eia-report v2 — snapshot.py：project_snapshot.json 读写器（跨轮承接 + 版本历史）。

geo v2 改造（差异有意非漂移，见 docs/designs/coal-eia-report-v2.md 两层模型改造点清单）：
  1. **mapping 枚举**（两层状态模型）：state/mapping.json（state 节 ↔ 项目章节 UUID 绑定，
     门 1 前章树绑定步骤产出）位于 state/ —— file_hashes 的 state/** rglob 天然全枚举；
     另增 --mapping 显式记录 mapping_path 进快照（续跑不重绑，D6），并对「文件在盘而
     枚举缺失」做护栏补记（rglob 永远覆盖——此护栏只为手改/旁路 save 兜底）。
  2. **版本指纹**（OV#8）：save 时对本技能 scripts/*.py 逐个算 SHA-256 前 16 位存入快照
     script_fingerprints；show --verify 时与当前脚本副本逐一比对，漂移 → SNAPSHOT_SCRIPT_DRIFT
     警告行（rc 不变）——副本债从「人肉约定」升级为「工具可见」（geo 三副本同步教训）。
     _ 前缀脚本（_smoke_t1.py 等临时件）不入指纹。
  3. save 保留 **hash 清单**（geo 原语义）：对 data/ + state/ 逐文件 SHA-256——
     show --verify 时逐一复算，mismatch → exit 3（篡改/半更新检测，步骤0 完整性门）。
  4. show --input 必填（无默认路径——沙箱布局不定，默认路径是隐性耦合）。
  5. 正典文件名守卫（bug-2198）：只允许写 project_snapshot.json。

用法：
  python snapshot.py save \
    --task "把矿区总规模从 6.0 改成 9.20 Mt/a 重算" \
    --stage references/stages/planning_eia.json \
    --data-dir /mnt/user-data/workspace/eia-report/data \
    --state-dir /mnt/user-data/workspace/eia-report/state \
    --mapping /mnt/user-data/workspace/eia-report/state/mapping.json \
    --manifest /mnt/user-data/workspace/eia-report/state/chapter_manifest.json \
    --report /mnt/user-data/outputs/环评报告.md \
    --output /mnt/user-data/workspace/project_snapshot.json
  → SNAPSHOT_READY: version=2 last_task=...
  python snapshot.py show --input .../project_snapshot.json [--verify]

退出码：0 干净（含 SCRIPT_DRIFT 警告——指纹漂移不改变 rc）/ 1 用法错误 / 3 篡改。
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

EXIT_OK, EXIT_ERROR, EXIT_TAMPERED = 0, 1, 3

# 技能脚本目录（版本指纹的比对对象=本副本 scripts/*.py；自包含，不指向 geo）
SCRIPTS_DIR = Path(__file__).resolve().parent
FP_LEN = 16  # OV#8：hash 前 16 位
MAPPING_RELPATH = "state/mapping.json"  # file_hashes 中的键形


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


def script_fingerprints() -> dict[str, str]:
    """本技能 scripts/*.py → {文件名: sha256 前 16 位}（OV#8）。_ 前缀临时件（_smoke 等）不入指纹。"""
    return {p.name: sha256_file(p)[:FP_LEN] for p in sorted(SCRIPTS_DIR.glob("*.py")) if p.is_file() and not p.name.startswith("_")}


def hash_manifest(data_dir: Path | None, state_dir: Path | None) -> dict[str, str]:
    """data/ + state/ 逐文件 SHA-256（相对路径 → hash）。state/** 天然涵盖
    sections/、chapters/、mapping.json、progress.json、formula_state.json 全部两层状态工件。"""
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

    state_dir = _maybe_path(args.state_dir) or prev.get("state_dir")
    file_hashes = hash_manifest(_maybe_path(args.data_dir), state_dir)
    # mapping.json 枚举护栏（改造点①）：文件在盘而 rglob 枚举缺失（手改/旁路 save 的形状）→ 补记
    mapping_enumerated = False
    if state_dir and (Path(state_dir) / "mapping.json").exists():
        if MAPPING_RELPATH not in file_hashes:
            file_hashes[MAPPING_RELPATH] = sha256_file(Path(state_dir) / "mapping.json")
            print(f"SNAPSHOT_GUARD: {MAPPING_RELPATH} 不在 rglob 枚举中（旁路 save 特征）——已护栏补记", file=sys.stderr)
        mapping_enumerated = True

    snap = {
        "version": new_version,
        "last_task": args.task,  # ⬅ 防漂移锚点：下一轮启动读此字段决定「当前任务」
        "created_at": prev.get("created_at") or entry["timestamp"],
        "updated_at": entry["timestamp"],
        "stage": args.stage or prev.get("stage"),
        "data_dir": _maybe_path(args.data_dir) or prev.get("data_dir"),
        "state_dir": state_dir,
        "mapping_path": _maybe_path(args.mapping) or prev.get("mapping_path"),  # 续跑不重绑（D6）
        "state_manifest_path": _maybe_path(args.state_manifest) or prev.get("state_manifest_path"),
        "formula_state_path": _maybe_path(args.formula_state) or prev.get("formula_state_path"),
        "chapter_manifest_path": _maybe_path(args.manifest) or prev.get("chapter_manifest_path"),
        "report_path": _maybe_path(args.report) or prev.get("report_path"),
        "changelog": changelog,
        "change_log": changelog,  # 兼容旧字段名
        "file_hashes": file_hashes,
        # OV#8 版本指纹：本快照由哪个版本的脚本副本产出
        "script_fingerprints": script_fingerprints(),
    }
    if file_hashes:
        entry["file_count"] = len(file_hashes)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SNAPSHOT_READY: version={new_version} last_task={args.task} path={out}")
    print(f"SNAPSHOT_FILE: {out}")
    print(f"SNAPSHOT_HASHES: {len(file_hashes)} files")
    print(f"SNAPSHOT_MAPPING: {'enumerated（续跑不重绑）' if mapping_enumerated else 'absent（门1 章树绑定后入库）'}")
    print(f"SNAPSHOT_SCRIPT_FINGERPRINTS: {len(snap['script_fingerprints'])} scripts")
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
    # OV#8 版本指纹比对：快照产出脚本 vs 当前副本——漂移只警告，rc 不变
    #（副本债工具可见；快照数据本身未被旁改，hash 门语义不受影响）。
    fps = snap.get("script_fingerprints") or {}
    if fps:
        drift: list[str] = []
        for name, fp in sorted(fps.items()):
            cur = SCRIPTS_DIR / name
            if not cur.exists():
                drift.append(f"{name}: 脚本副本缺失（快照产出后该副本被移除？）")
            elif sha256_file(cur)[:FP_LEN] != fp:
                drift.append(f"{name}: {fp} → {sha256_file(cur)[:FP_LEN]}")
        if drift:
            print(f"SNAPSHOT_SCRIPT_DRIFT: {len(drift)}/{len(fps)} 脚本副本指纹漂移（OV#8——快照由旧版脚本产出，副本同步约定可能被绕过；rc 不变）")
            for d in drift:
                print(f"  DRIFT: {d}")
        else:
            print(f"SNAPSHOT_SCRIPTS_VERIFIED: {len(fps)} script fingerprints intact")
    else:
        print("SNAPSHOT_SCRIPT_FINGERPRINTS: 无（旧版本快照）——跳过")
    return EXIT_OK


def main() -> int:
    p = argparse.ArgumentParser(description="coal-eia-report v2 — project_snapshot.json 读写（含 OV#8 脚本版本指纹）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("save", help="读旧快照→version++→追加 changelog→写回（hash 清单+脚本指纹+mapping 枚举）")
    s.add_argument("--task", required=True, help="本轮用户指令一句话摘要（写入 last_task）")
    s.add_argument("--stage", default=None, help="stage JSON 路径（如 references/stages/planning_eia.json）")
    s.add_argument("--data-dir", default=None, help="data/ 目录（hash 清单范围）")
    s.add_argument("--state-dir", default=None, help="state/ 目录（hash 清单范围——含 sections/chapters/mapping.json）")
    s.add_argument("--mapping", default=None, help="state/mapping.json 路径（节↔项目章节 UUID 绑定，续跑不重绑）")
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

    sh = sub.add_parser("show", help="打印锚点摘要；--verify 逐文件 hash 复算 + 脚本版本指纹漂移检查（漂移只警告，rc 不变）")
    sh.add_argument("--input", required=True, help="project_snapshot.json 路径（必填，无默认）")
    sh.add_argument("--verify", action="store_true", help="复算 file_hashes（mismatch → exit 3）+ 指纹比对（DRIFT 行）")
    sh.set_defaults(func=cmd_show)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
