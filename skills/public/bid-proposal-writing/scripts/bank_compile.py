"""bank_compile——投标样例入库编译器(v4 WP-2/G1, 离线一键产全部衍生物)。

流程: 装载(标书 md/docx) → 章切片 → 自动脱敏(+--map 显式对照) → 残留扫描(rc=1 不出库)
→ 深度统计(P25 floor/全库 median) → 四产物(samples_bank 切片+指纹池+bank_index+depth_targets)
→ registration.json(供 backend/scripts/bid_seed_samples.py 入 BidSample 台账)
→ 可选 RAGFlow bid_samples 域推送(失败=warnings 不阻塞)。

stdlib 自包含(技能=自包含分发单元)。离线维护者工具, 不进 SKILL.md 速查表。
用法:
  python bank_compile.py --input 标书.md --title "江西师范大学课堂观测系统" \
    --industry 信息技术 --category IT软件平台 --bank-dir references/samples_bank \
    [--map map.json] [--ragflow-push]
退出码: 0 干净 / 1 用法或残留扫描命中。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1

HEAD1_RE = re.compile(r"^# (?!#)(.+)$")
HEAD2_RE = re.compile(r"^## (?!#)(.+)$")


def load_text(path: Path) -> str:
    """md 直读; docx 走内置极简文本抽取(段落带样式层级→md 标题)。"""
    if path.suffix.lower() == ".md":
        return path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".docx":
        return _docx_to_markdown(path)
    raise ValueError(f"不支持的输入类型: {path.suffix}(支持 .md/.docx)")


def _docx_to_markdown(path: Path) -> str:
    """docx → md(标题样式→# 层级, 段落照抄, 表格→管道表)。极简: 只服务切片。"""
    import zipfile
    from xml.etree import ElementTree as ET

    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines: list[str] = []
    with zipfile.ZipFile(str(path)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    for child in root.find(f"{W}body") or []:
        if child.tag == f"{W}p":
            text = "".join(t.text or "" for t in child.iter(f"{W}t")).strip()
            if not text:
                continue
            style = child.find(f"{W}pPr/{W}pStyle")
            sid = style.get(f"{W}val", "") if style is not None else ""
            m = re.match(r"^[Hh]eading(\d)$", sid) or re.match(r"^(\d)$", sid or "")
            lines.append(("#" * int(m.group(1)) + " " + text) if m else text)
        elif child.tag == f"{W}tbl":
            rows = child.findall(f"{W}tr")
            grid: list[list[str]] = []
            for tr in rows:
                grid.append(["".join(t.text or "" for t in tc.iter(f"{W}t")) for tc in tr.findall(f"{W}tc")])
            if grid:
                # 整表作为一个块(行间单 \n)——外层 "\n\n" join 时管道表行须连续, 空行会碎表
                tbl = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * len(grid[0])]
                tbl.extend("| " + " | ".join(r) + " |" for r in grid[1:])
                lines.append("\n".join(tbl))
    return "\n\n".join(lines)


def split_chapters(text: str) -> list[dict]:
    """章切片: H1/H2 标题为界连续分段(不重排——1:1 纪律)。返回 [{title, level, text}]。"""
    lines = text.split("\n")
    chapters: list[dict] = []
    cur: dict | None = None
    buf: list[str] = []

    def _flush():
        nonlocal cur, buf
        if cur is not None:
            cur["text"] = "\n".join(buf).strip()
            chapters.append(cur)
        buf = []

    for line in lines:
        m1 = HEAD1_RE.match(line)
        m2 = HEAD2_RE.match(line)
        if m1 or m2:
            _flush()
            cur = {"title": (m1 or m2).group(1).strip(), "level": 1 if m1 else 2, "text": ""}
            buf = [line]
        else:
            buf.append(line)
    _flush()
    return chapters


def paragraph_lengths(text: str) -> list[int]:
    """非空段落长度列表(深度统计输入)。"""
    return [len(p.strip()) for p in text.split("\n") if p.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bank_compile.py", description="投标样例入库编译器(离线)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--industry", default="信息技术")
    ap.add_argument("--category", default="IT软件平台")
    ap.add_argument("--bank-dir", required=True)
    args = ap.parse_args(argv)
    text = load_text(Path(args.input))
    chapters = split_chapters(text)  # Task 3 起接入完整流水线
    print(json.dumps({"command": "bank_compile", "chapters": len(chapters)}, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
