"""投标方案编写技能·进度快照(project_snapshot.json 确定性落盘, 无 LLM)。

回放实证(2026-08-18): 多轮承接靠 agent 会话末手写 project_snapshot.json, 实际从未
落地——后续 run 反复找 snapshot/merge_ledger/decisions 等文件, 或漂移回"重新生成"。
本脚本把快照变成确定性产物: 每个阶段动作后跑一次, run 开始读它续作。

用法:
    python snapshot.py --workspace /mnt/user-data/workspace/bid \
        --project "内蒙古财经大学软件采购" --code ZB=招标文件 --code BY=补遗01

--project/--code 可省(续作时保留快照既有值); 阶段由状态文件存在性推断。stdout 输出
单行 JSON 快照摘要(管线脚本统一口径), 同时原子写 <workspace>/project_snapshot.json。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SNAPSHOT_NAME = "project_snapshot.json"
_VERSION_RE = re.compile(r"^version_(\d+)\.md$")


def _atomic_write_json(path: Path, data: dict) -> None:
    """原子写盘: 临时文件 + os.replace(与管线脚本同纪律)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _load_json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _count_state(state_dir: Path) -> dict:
    sections = _load_json(state_dir / "sections.json") or {}
    clauses = _load_json(state_dir / "clauses.json") or []
    structure = _load_json(state_dir / "structure.json") or []
    rubric = _load_json(state_dir / "rubric.json") or {}
    return {
        "sections_chunks": len(sections.get("chunks", [])) if isinstance(sections, dict) else 0,
        "sections_tables": len(sections.get("tables", [])) if isinstance(sections, dict) else 0,
        "clauses": len(clauses) if isinstance(clauses, list) else 0,
        "structure_nodes": len(structure) if isinstance(structure, list) else 0,
        "rubric_items": len(rubric.get("items", [])) if isinstance(rubric, dict) else 0,
        "rubric_total_score": rubric.get("total_score") if isinstance(rubric, dict) else None,
        "entities_locked": (state_dir / "entities_whitelist.json").is_file(),
    }


def _infer_phase(workspace: Path, state_dir: Path, counts: dict) -> tuple[str, str]:
    """按状态文件存在性推断阶段与下一步(推断链与 SKILL.md 六阶段对应)。"""
    if not (state_dir / "sections.json").is_file():
        return ("0-受理", "请用户上传基础文件并分配代号, 运行 ingest.py(命令见 SKILL.md 速查表)")
    if counts["clauses"] == 0:
        return ("2-提取中", "继续阶段2 提取循环: 逐 chunk/table 产候选落 candidates/, 然后 extract.py validate + merge")
    if not counts["entities_locked"]:
        return ("确认门1-待锁定", "向用户呈现计数+异常项, 逐条改分类, 实体白名单确认后写 entities_whitelist.json")
    if not (workspace / "output" / "商务卷.md").is_file():
        return ("3/4-合并与构建", "补遗到达走阶段3(ingest --addendum→提取→merge_addenda); 无补遗直接 build_output.py 六件套")
    versions = [int(m.group(1)) for p in (state_dir / "评分报告").glob("version_*.md") if (m := _VERSION_RE.match(p.name))]
    if versions:
        return (f"5-评分已完成(v{max(versions)})", "按报告改进建议修订, 或团队新版回传后重跑阶段5(报告 version++)")
    return ("4-已构建", "走确认门2(补遗 diff+终稿复核), 分发双卷; 团队回传后进阶段5")


def _parse_code(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"--code 应为 代号=说明 形态(如 ZB=招标文件), 实际 {text!r}")
    code, _, label = text.partition("=")
    if not code.strip() or not label.strip():
        raise argparse.ArgumentTypeError(f"--code 代号与说明均不可为空: {text!r}")
    return code.strip(), label.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="snapshot.py",
        description="投标方案编写·进度快照: 扫描 workspace 推断阶段, 确定性写 project_snapshot.json(无 LLM; 每阶段动作后跑一次, run 开始读它续作)",
        epilog="示例: python snapshot.py --workspace /mnt/user-data/workspace/bid --project 内蒙古财经大学软件采购 --code ZB=招标文件",
    )
    parser.add_argument("--workspace", required=True, help="技能工作区目录(其下 state/ candidates/ output/; 快照写 <workspace>/project_snapshot.json)")
    parser.add_argument("--project", default=None, help="项目名(省略则保留快照既有值; 新工作区首跑建议必填, 防跨项目路径混淆)")
    parser.add_argument("--code", action="append", default=None, type=_parse_code, metavar="CODE=LABEL", help="文件代号映射, 可多次(如 --code ZB=招标文件 --code BY=补遗01; 省略则保留既有)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if not exc.code:
            return 0
        print(f"[snapshot] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}; 用 --help 查看用法)", file=sys.stderr)
        return 1

    workspace = Path(args.workspace)
    state_dir = workspace / "state"
    previous = _load_json(workspace / SNAPSHOT_NAME) or {}

    codes: dict[str, str] = dict(previous.get("codes") or {})
    if args.code:
        codes.update(dict(args.code))
    project = args.project if args.project is not None else previous.get("project")

    counts = _count_state(state_dir)
    phase, next_step = _infer_phase(workspace, state_dir, counts)
    candidates_dir = workspace / "candidates"
    output_dir = workspace / "output"
    snapshot = {
        "project": project,
        "codes": codes,
        "phase": phase,
        "next_step": next_step,
        "state": counts,
        "candidates_files": len(list(candidates_dir.glob("*.json"))) if candidates_dir.is_dir() else 0,
        "output_files": sorted(p.name for p in output_dir.glob("*.md")) if output_dir.is_dir() else [],
    }
    _atomic_write_json(workspace / SNAPSHOT_NAME, snapshot)
    print(json.dumps(snapshot, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
