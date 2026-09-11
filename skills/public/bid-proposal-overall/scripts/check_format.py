#!/usr/bin/env python3
"""check_format.py — 投标方案编写技能·格式 1:1 复刻确定性校验(无 LLM, 只读)。

回放实证(2026-08-16 江西师大线程 1a80a1d8): 阶段2 槽位定型是 LLM 循环,
"只镜像不自创"此前只靠提示词自律——实测三类静默失真全部漏过:
  ① 标题被归一化("1. 投标书(格式)"→"投标书", 编号/后缀被剥);
  ② 模板固定文字没逐字抄进 template_text(正文只剩元数据 bullet);
  ③ 格式章节骨架漏节点(封面/资格声明等整个节消失)。
本脚本把格式保真从提示词纪律升级为确定性校验: structure.json 的每段标题/每段
template_text/每个 fixed_rows 单元格, 以及源文件骨架覆盖, 全部对
  --sources <uploads 转出的 .md> + sections.json heading_path
逐字比对; 对不上 = 退出码 3 异常项逐条呈现, 绝不静默, 也绝不回写"修正"。

比较期归一化只做两件事(原文照抄纪律不变, 归一化仅用于比对侧):
  - 去全部空白(含全角空格/换行——markitdown 单行化与 docx 渲染差异);
  - 标题比对另折叠"连续同字重复"(PDF/markitdown char-dup 伪影,
    如"一一一一 总总总总 则则则则"≡"总则")——正文包含性比对不折叠(防合法叠字误配)。

用法:
    python check_format.py --state-dir <dir> --sources <md> [<md> ...]

调用点(SKILL.md 编排): extract merge 后+确认门1 前 / merge_addenda 后 / build 前自检。

退出码: 0=全部通过; 1=用法/文件错误(structure.json/sections.json 缺失=先跑前序脚本;
        签名校验失败同归 1, 按错误行恢复指令重建); 3=发现格式保真异常(读 stdout 单行
        JSON 摘要, anomalies 逐项呈现给用户——不是失败, 不静默吞掉)。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import state_guard

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ANOMALY = 3

_ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


class CheckFormatError(Exception):
    """用法/文件/签名错误(退出码 1)。"""


def norm_title(text: str) -> str:
    """标题比对形态: 去全部空白 + 连续同字折叠(char-dup 伪影) + casefold。

    折叠对两侧标题同时生效——真一致的标题折叠后仍一致; 代价是仅差叠字的两个
    不同标题会误判相等, 该容差留给确认门人核, 不做更强启发式。"""
    compact = "".join(text.split())
    folded: list[str] = []
    for ch in compact:
        if not folded or folded[-1] != ch:
            folded.append(ch)
    return "".join(folded).casefold()


def norm_text(text: str) -> str:
    """正文包含性比对形态: 去全部空白 + casefold; 不折叠同字(正文合法叠字常见)。"""
    return "".join(text.split()).casefold()


def md_heading_paths(text: str) -> list[tuple[str, ...]]:
    """解析 md 的 ATX 标题(#..######)为层级路径链; 无标题文件返回空(markitdown
    单行化产物现实存在——此时骨架覆盖只能依赖 sections.json, 不视为错误)。"""
    stack: list[tuple[int, str]] = []
    paths: list[tuple[str, ...]] = []
    for line in text.splitlines():
        matched = _ATX_HEADING_RE.match(line)
        if not matched:
            continue
        level, title = len(matched.group(1)), matched.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        paths.append(tuple(title for _, title in stack))
    return paths


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise CheckFormatError(f"无法读取 {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CheckFormatError(f"{path} 不是合法 JSON: {exc}") from exc


def _prefix_related(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """a 与 b 存在前缀链关系(任一方向)——镜像树里源标题链与结构标题链允许
    一方是另一方的前缀(源只有容器级标题/结构有更深叶子都合法)。"""
    shorter = min(len(a), len(b))
    return a[:shorter] == b[:shorter]


def check(state_dir: str, sources: list[str]) -> tuple[list[dict], dict]:
    """执行全部校验; 返回 (anomalies, 计数摘要)。只读, 不写任何文件。"""
    guard_problems = state_guard.verify_state_files(state_dir)
    if guard_problems:
        raise CheckFormatError("权威状态文件签名校验失败(疑似脚本外直写/误删):\n  - " + "\n  - ".join(guard_problems))

    structure_path = Path(state_dir) / "structure.json"
    sections_path = Path(state_dir) / "sections.json"
    if not structure_path.is_file() or not sections_path.is_file():
        raise CheckFormatError(f"structure.json/sections.json 缺失({state_dir})——先跑 ingest.py 与 extract.py merge 再校验格式保真")
    structure = _load_json(structure_path)
    sections = _load_json(sections_path)
    if not isinstance(structure, list) or not all(isinstance(n, dict) for n in structure):
        raise CheckFormatError(f"{structure_path} 形态异常: 顶层应为节点数组")

    anomalies: list[dict] = []
    # ---- 源侧素材: sections.json heading_path 链 + 各 --sources md 标题链/正文 ----
    source_paths: list[tuple[str, ...]] = []
    for chunk in sections.get("chunks", []) if isinstance(sections, dict) else []:
        heading_path = chunk.get("heading_path") if isinstance(chunk, dict) else None
        if isinstance(heading_path, list) and heading_path and all(isinstance(s, str) and s for s in heading_path):
            source_paths.append(tuple(str(s).strip() for s in heading_path))

    if not sources:
        anomalies.append({"kind": "source_md_missing", "detail": "未提供 --sources(uploads 转出的 .md): template_text/fixed_rows 逐字校验与 md 骨架覆盖跳过, 仅对 sections.json 标题校验——显式降级, 不静默"})
    body_norm = ""
    for source in sources:
        path = Path(source)
        if not path.is_file():
            raise CheckFormatError(f"--sources 文件不存在: {path}(用绝对路径, 见速查表)")
        text = path.read_text(encoding="utf-8-sig")
        body_norm += norm_text(text)
        source_paths.extend(md_heading_paths(text))

    # ---- 源标题素材的比对形态 ----
    source_paths_norm = [tuple(norm_title(seg) for seg in p) for p in source_paths]
    segments_norm: dict[str, str] = {}
    for original in source_paths:
        for seg in original:
            segments_norm.setdefault(norm_title(seg), seg)

    # ---- 结构侧比对形态 ----
    node_paths = []
    for node in structure:
        raw = str(node.get("path", "")).strip()
        node_paths.append(tuple(s.strip() for s in raw.split("/")) if raw else ())
    node_paths_norm = [tuple(norm_title(seg) for seg in p) for p in node_paths]
    roots_norm = {p[0] for p in node_paths_norm if p}

    titles_checked = template_checked = fixed_rows_checked = 0

    # ---- 校验 A/B/C: 逐节点 标题逐字 + template_text 包含 + fixed_rows 单元 ----
    for node, path_segs in zip(structure, node_paths):
        node_id = str(node.get("node_id", "?"))
        if node.get("origin") == "self_created":
            continue  # 阶段4a 技术响应自拟挂接位: 非镜像, 免逐字校验(确认门人核)
        for seg in path_segs:
            if not segments_norm:
                break  # 无源标题素材(未给 --sources 且 sections 无 heading_path): 标题校验降级跳过
            titles_checked += 1
            if norm_title(seg) not in segments_norm:
                anomalies.append({"kind": "title_mismatch", "node_id": node_id, "segment": seg, "detail": "标题段在源文件标题集中无逐字对应(编号/（格式）后缀/全半角被归一化或同义改写均不合格——1:1 复刻要求逐字)"})
        path_norm = tuple(norm_title(seg) for seg in path_segs)
        if path_norm and source_paths_norm and not any(_prefix_related(path_norm, sp) for sp in source_paths_norm if sp):
            anomalies.append({"kind": "path_unmatched", "node_id": node_id, "path": "/".join(path_segs), "detail": "标题链层级/顺序在源文件中无对应前缀链(疑似层级错挂或跨章节拼装)"})

        required_format = node.get("required_format") or {}
        if not isinstance(required_format, dict):
            continue
        template_text = required_format.get("template_text")
        if isinstance(template_text, str) and template_text:
            template_checked += 1
            if sources and norm_text(template_text) not in body_norm:
                anomalies.append({"kind": "template_text_not_found", "node_id": node_id, "detail": "template_text 非源文件逐字子串(照抄纪律: 不得改写/概括/拼接/换行重排)"})
        table_spec = required_format.get("table_spec") or {}
        if not isinstance(table_spec, dict):
            continue
        fixed_rows = table_spec.get("fixed_rows")
        if fixed_rows is None:
            continue
        fixed_rows_checked += 1
        rows_ok = isinstance(fixed_rows, list) and bool(fixed_rows) and all(isinstance(r, list) for r in fixed_rows)
        if not rows_ok:
            anomalies.append({"kind": "fixed_rows_shape", "node_id": node_id, "detail": "fixed_rows 形态异常: 应为非空二维数组(每行=字符串/数值单元格数组, 待填单元格空串)"})
            continue
        columns = table_spec.get("columns")
        n_cols = len(columns) if isinstance(columns, list) else 0
        for i, row in enumerate(fixed_rows, start=1):
            if n_cols and len(row) != n_cols:
                anomalies.append({"kind": "fixed_rows_shape", "node_id": node_id, "detail": f"fixed_rows 第{i}行列数 {len(row)} ≠ columns 列数 {n_cols}"})
            for j, cell in enumerate(row, start=1):
                cell_text = "" if cell is None else str(cell)
                if cell_text and sources and norm_text(cell_text) not in body_norm:
                    anomalies.append({"kind": "fixed_rows_cell_not_found", "node_id": node_id, "detail": f"固定行[{i},{j}] 非源文件逐字子串: {cell_text[:30]}"})

    # ---- 校验 D: 骨架覆盖——镜像根下的每个源标题链必须是某结构路径的前缀 ----
    # 方向性判定(与校验 A 的双向前缀不同): 源链 [根, X] 只被 [根] 容器节点覆盖 = X 无节点 = 丢项;
    # 结构路径更深(源只到容器级)不算丢项。即: 源链 sp 合格 ⟺ ∃节点链 np: len(np)≥len(sp) 且 sp 是 np 的前缀。
    for original, path_norm in zip(source_paths, source_paths_norm):
        if not path_norm or path_norm[0] not in roots_norm:
            continue
        if not any(len(np) >= len(path_norm) and np[: len(path_norm)] == path_norm for np in node_paths_norm):
            anomalies.append({"kind": "skeleton_gap", "detail": f"源标题未被镜像: {'/'.join(original)}(格式章节骨架禁止静默丢项——每个标题/每张表都应有节点)"})

    summary = {
        "nodes_checked": len(structure),
        "titles_checked": titles_checked,
        "template_texts_checked": template_checked,
        "fixed_rows_checked": fixed_rows_checked,
        "source_heading_paths": len(source_paths),
        "anomaly_count": len(anomalies),
    }
    return anomalies, summary


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回进程退出码(见模块 docstring 退出码约定)。"""
    parser = argparse.ArgumentParser(
        prog="check_format.py",
        description="投标方案编写·格式 1:1 复刻确定性校验: 标题逐字/template_text 逐字/fixed_rows 单元/骨架覆盖(无 LLM, 只读, 不回写)",
        epilog="示例: python check_format.py --state-dir /mnt/user-data/workspace/bid/state --sources /mnt/user-data/uploads/招标文件.md",
    )
    parser.add_argument("--state-dir", required=True, help="状态目录(含 structure.json/sections.json)")
    parser.add_argument("--sources", nargs="*", default=[], help="源文件 md(uploads 转出的同名 .md, 可多个); 缺省=显式降级 anomaly")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if not exc.code:
            return EXIT_OK
        print(f"[check_format] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}; 用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR

    try:
        anomalies, summary = check(args.state_dir, list(args.sources))
    except CheckFormatError as exc:
        print(f"[check_format] 错误: {exc}", file=sys.stderr)
        return EXIT_ERROR

    payload = {"tool": "check_format", **summary, "anomalies": anomalies}
    print(json.dumps(payload, ensure_ascii=False))
    return EXIT_ANOMALY if anomalies else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
