"""bank_compile——投标样例入库编译器(v4 WP-2/G1, 离线一键产全部衍生物)。

流程: 装载(标书 md/docx) → 章切片 → 自动脱敏(+--map 显式对照) → 残留扫描(rc=1 不出库)
→ 深度统计(P25 floor/全库 median) → 四产物(samples_bank 切片+指纹池+bank_index+depth_targets)
→ registration.json(供 backend/scripts/bid_seed_samples.py 入 BidSample 台账)
→ 可选 RAGFlow bid_samples 域推送(失败=warnings 不阻塞)。

stdlib 自包含(技能=自包含分发单元)。离线维护者工具, 不进 SKILL.md 速查表。
用法:
  python bank_compile.py --input 标书.md --title "江西师范大学课堂观测系统" \
    --industry 信息技术 --category IT软件平台 --bank-dir references/samples_bank \
    [--map map.json] [--ragflow-push]   (--map/--ragflow-push 于 Task 3/5 接入)
退出码: 0 干净 / 1 用法或残留扫描命中。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1
MASK = "****"  # 对齐 geo_samples/redactor.py:9

HEAD1_RE = re.compile(r"^# (?!#)(.+)$")
HEAD2_RE = re.compile(r"^## (?!#)(.+)$")
CLOSING_HASHES_RE = re.compile(r"\s+#+\s*$")  # M-4: ATX 闭合 # 序列

DOCX_HEADING_STYLE_RE = re.compile(r"^[Hh]eading(\d)$")  # M-8: docx 样式→层级, 预编译
DOCX_NUM_STYLE_RE = re.compile(r"^(\d)$")
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 脱敏引擎。边界口径沿用 bug-3061 教训(geo_samples/redactor.py): 中文语境禁 \b——Unicode 模式下
# CJK 属 \w, \b 在「电话13800138000」这类紧邻汉字处永不成立; 信用代码加「至少含一字母」环视,
# 防 18 位纯数字(身份证)被信用代码规则误吞。
AMOUNT_RE = re.compile(r"[￥¥]?\s*\d{1,3}(?:[,，]\d{3})*(?:\.\d+)?\s*(?:万?元)")
CREDIT_CODE_RE = re.compile(r"(?<![0-9A-Za-z])(?=[0-9A-HJ-NPQRTUWXY]*[A-HJ-NPQRTUWXY])[0-9A-HJ-NPQRTUWXY]{18}(?![0-9A-Za-z])")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?![0-9Xx])")
# M-1: 残留门=组合式——直接引用各规则 pattern 拼接(同源而非同文), 规则修订不再让安全门静默过期。
# 另含脱敏不覆盖的 fail-closed 分支(只进残留门不进掩码, 命中即 rc=1 交维护者 --map 或人工裁决):
#   · ￥/¥+数字(无元后缀)——货币符号形态 AMOUNT_RE 摸不到的残余;
#   · 裸「万元」(M-3: 声明接受误伤面——脱敏后正文不应再有万元字样, 「按万元计」类误报宁多勿漏);
#   · 两位小数千分位金额(M-2, bug-3236: 表格单价 3,500.00 类无元后缀高频漏网形态)。
RESIDUAL_RE = re.compile(
    "|".join(
        [
            AMOUNT_RE.pattern,
            r"[￥¥]\s*\d",
            "万元",
            CREDIT_CODE_RE.pattern,
            PHONE_RE.pattern,
            ID_CARD_RE.pattern,
            r"\d{1,3}(?:[,，]\d{3})*\.\d{2}(?!\d)",
        ]
    )
)


def load_text(path: Path) -> str:
    """md 直读(UTF-8 优先, 失败退 gb18030, 双败给可操作报错); docx 走内置极简文本抽取。"""
    if path.suffix.lower() == ".md":
        raw = path.read_bytes()
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError(f"{path.name} 无法按 UTF-8/gb18030 解码——请先转存为 UTF-8 md 再入库") from exc
            print(f"提示: {path.name} 非 UTF-8, 已按 gb18030 解码", file=sys.stderr)
            return text
    if path.suffix.lower() == ".docx":
        return _docx_to_markdown(path)
    raise ValueError(f"不支持的输入类型: {path.suffix}(支持 .md/.docx)")


def _docx_cell_text(tc) -> str:
    """M-2: 单元格文本——| 转义防碎表, 内嵌换行折叠空格。"""
    return "".join(t.text or "" for t in tc.iter(f"{W_NS}t")).replace("|", "\\|").replace("\n", " ")


def _docx_to_markdown(path: Path) -> str:
    """docx → md(标题样式→# 层级, 段落照抄, 表格→管道表)。极简: 只服务切片。"""
    import zipfile
    from xml.etree import ElementTree as ET

    lines: list[str] = []
    with zipfile.ZipFile(str(path)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(f"{W_NS}body")
    if body is None:  # M-3: 显式 None 判定——Element 真值测试自 3.12 起 DeprecationWarning
        return ""
    for child in body:
        if child.tag == f"{W_NS}p":
            text = "".join(t.text or "" for t in child.iter(f"{W_NS}t")).strip()
            if not text:
                continue
            style = child.find(f"{W_NS}pPr/{W_NS}pStyle")
            sid = style.get(f"{W_NS}val", "") if style is not None else ""
            m = DOCX_HEADING_STYLE_RE.match(sid) or DOCX_NUM_STYLE_RE.match(sid)
            lines.append(("#" * int(m.group(1)) + " " + text) if m else text)
        elif child.tag == f"{W_NS}tbl":
            rows = child.findall(f"{W_NS}tr")
            grid: list[list[str]] = []
            for tr in rows:
                grid.append([_docx_cell_text(tc) for tc in tr.findall(f"{W_NS}tc")])
            if grid:
                # 整表作为一个块(行间单 \n)——外层 "\n\n" join 时管道表行须连续, 空行会碎表
                width = len(grid[0])
                tbl = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * width]
                for r in grid[1:]:
                    padded = r[:width] + [""] * (width - len(r))  # M-2: 短行补空单元格闭合管道表
                    tbl.append("| " + " | ".join(padded) + " |")
                lines.append("\n".join(tbl))
    return "\n\n".join(lines)


def split_chapters(text: str) -> list[dict]:
    """章切片: H2 为唯一章界连续分段(不重排——1:1 纪律); H3+ 不切。H1 视作文档/篇标题
    (封面/篇首段), 其下内容不立章——全文仍进 full.md(Task 3), 章切片只收 H2 节,
    仿标书「一、二、三」节结构。返回 [{title, level, text}], level 恒 2。"""
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
        m2 = HEAD2_RE.match(line)
        if m2:
            _flush()
            title = CLOSING_HASHES_RE.sub("", m2.group(1).strip())  # M-4: 剥 ATX 闭合 #
            cur = {"title": title, "level": 2, "text": ""}
            buf = [line]
        elif HEAD1_RE.match(line):  # H1=文档/篇标题: 起新非章段, 其下内容不立章
            _flush()
            cur = None
        else:
            buf.append(line)
    _flush()
    return chapters


def paragraph_lengths(text: str) -> list[int]:
    """非空正文段落长度列表(深度统计输入)。M-1: 剔 # 标题行与 | 表格行/分隔行——
    短结构行会系统性拉低 Task 3 的 P25 absolute_floor。"""
    return [len(p.strip()) for p in text.split("\n") if p.strip() and not p.lstrip().startswith(("#", "|"))]


def redact(text: str, mapping: dict[str, str]) -> str:
    """脱敏: --map 显式对照优先(逐字替换, 全行含标题), 再跑自动模式(金额/信用代码/手机号/身份证)。
    标题行(# 开头)只吃 --map、跳过自动正则——# 前缀与标题完整性不动(章结构保真); 机构/人名在标题
    出现时 --map 是唯一清洗通道, 标题里的裸金额类残留交残留门 fail-closed 兜底(I-2, 不静默泄漏)。
    mapping 键=原文, 值=脱敏占位。切片(split_chapters)在脱敏之前完成, 标题替换不伤章界。"""
    out_lines = []
    for line in text.split("\n"):
        for src, dst in mapping.items():
            if src:  # 空键防御: "".replace 语义陷阱, 直接跳过
                line = line.replace(src, dst)
        if line.lstrip().startswith("#"):
            out_lines.append(line)  # I-2: 标题行只吃 --map, 自动正则跳过
            continue
        line = AMOUNT_RE.sub(MASK, line)
        line = CREDIT_CODE_RE.sub(MASK, line)
        line = PHONE_RE.sub(MASK, line)
        line = ID_CARD_RE.sub(MASK, line)
        out_lines.append(line)
    return "\n".join(out_lines)


def residual_scan(text: str) -> list[str]:
    """残留扫描(脱敏后质检): 命中即返回证据行(调用方 rc=1 不出库)。"""
    return [ln.strip()[:120] for ln in text.split("\n") if RESIDUAL_RE.search(ln)]


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
    if not chapters:  # M-6: 零章=极端形态(如自定义样式 docx 全量丢弃), 提示而非静默
        print("警告: 切片 0 章——输入无 H2 章标题(自定义样式 docx 可能全量丢弃), 请核对标题样式", file=sys.stderr)
    print(json.dumps({"command": "bank_compile", "chapters": len(chapters)}, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
