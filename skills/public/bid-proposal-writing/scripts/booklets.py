#!/usr/bin/env python3
"""册规划与索引卷渲染(v4 WP-1): 页数估算/贪心切册/册命名/索引卷——纯函数无 IO。

契约(docs/designs/bid-proposal-writing-v4-volume-architecture.md 分册契约表):
- 页数估算: ceil(字符/800 + 表格×0.5 + 图片×0.5 + max(0,行数-20)×0.05/行)——
  系数经三份真实中标标书校验(江西师大估 217p vs 实际 ~220p, 误差 1-2%); 图片项
  来自同批实证(资质扫描章 ~100 页纯图, 每份 118-156 图)。估算属性=守门告警,
  非精确排版(契约表"页数公式备注")。
- 软上限 50 页(eng-review 2A): 沿镜像章序贪心装箱, 达上限在章边界切;
  单章自身超限 → 整章成册 + 超限告警(80 页册≈2100 块, 远离 300 页 BlockNote
  红线, 不在章内硬切); 尾册 <8 页并入前册(合并告警)。
- 册命名: {文档}-{册序02d}-{首章短名}.md; 索引卷固定 0-总目录索引.md。
- booklet 归属(外部声音 7A): build_output 构建时产物——渲染时按生成后字数现算,
  写 delivery_manifest + 索引卷, 不进 structure.json/state(schema 落盘在生成前,
  切册判据依赖生成后字数, 落 state 即循环依赖)。
- 本模块纯 stdlib 自包含(技能=自包含分发单元, 兄弟技能不互 import), 被同目录
  build_output.py import(兄弟脚本间 import 沿 extract/ingest 先例)。
"""
from __future__ import annotations

import math
import re

# 页数估算系数(契约表定案, 常量化入测试)
CHARS_PER_PAGE = 800
TABLE_PAGES = 0.5
IMAGE_PAGES = 0.5
BIG_TABLE_FREE_ROWS = 20
BIG_TABLE_EXTRA_PER_ROW = 0.05
# 切册阈值(契约表定案)
SOFT_CAP_PAGES = 50.0
MERGE_BELOW_PAGES = 8.0
INDEX_FILENAME = "0-总目录索引.md"

_TITLE_PREFIX_RE = None  # short_name 改三段式子正则, 保留占位说明历史(不再使用)
_SHORT_NAME_LIMIT = 12


def estimate_pages(chars: int = 0, tables: int = 0, table_rows: int = 0, images: int = 0) -> float:
    """页数估算(F2 公式, 契约表): 字符 + 表格 + 图片 + 大表行数补偿。返回 1 位小数。"""
    big_extra = max(0, table_rows - BIG_TABLE_FREE_ROWS) * BIG_TABLE_EXTRA_PER_ROW
    raw = (
        chars / CHARS_PER_PAGE
        + tables * TABLE_PAGES
        + images * IMAGE_PAGES
        + big_extra
    )
    return round(raw, 1)


def chapter_of(path: str) -> str:
    """章键 = 标题链首段(structure.json path "投标函/签署页" → "投标函")。"""
    return path.split("/")[0].strip()


def short_name(title: str, limit: int = _SHORT_NAME_LIMIT) -> str:
    """首章短名(册文件名用): 去编号前缀("第十章 总体技术方案"→"总体技术方案"),
    截断到 limit 字——文件名可读性优先, 索引卷承载全名。

    三段式剥离: 第X章 → （一）/（1）括号形态 → 裸编号"1."/"一、"; 保守匹配
    (编号后必须跟分隔符或闭括号), "一表通平台"这类词头不误剥。
    """
    stripped = re.sub(r"^第[一二三四五六七八九十百零〇\d]{1,4}[章节部分篇]\s*", "", title)
    stripped = re.sub(r"^[（(][一二三四五六七八九十\d]{1,6}[）)][\s、.．:：]*", "", stripped)
    stripped = re.sub(r"^[\d一二三四五六七八九十]{1,4}[、.．:：]\s*", "", stripped)
    stripped = stripped.strip()
    return (stripped or title.strip())[:limit]


def booklet_filename(doc: str, idx: int, first_title: str) -> str:
    """册文件名(契约表): {文档}-{册序02d}-{首章短名}.md"""
    return f"{doc}-{idx:02d}-{short_name(first_title)}.md"


def plan_booklets(
    chapters: list[dict],
    soft_cap: float = SOFT_CAP_PAGES,
    merge_below: float = MERGE_BELOW_PAGES,
) -> tuple[list[dict], list[str]]:
    """贪心切册(契约表 WP-1.0): 沿镜像章序装箱, 三规则——

    A(2A) 单章超软上限 → flush 当前册后整章独立成册, oversized=True + 告警;
    B 装不下(当前册+章 > soft_cap) → flush, 章开新册;
    C 尾册 < merge_below → 并入前册(前册不存在则独立保留), + 合并告警。

    chapters: [{"title": 章名, "chars": int, "tables": int, "table_rows": int,
                "images": int}]——顺序即镜像序, 本函数不排序不重排。
    返回 (booklets, warnings); booklet = {"chapters": [章名...], "pages_est": float,
    "oversized": bool}。空输入 → ([], [])。
    """
    warnings: list[str] = []
    booklets: list[dict] = []
    acc: list[dict] = []
    acc_pages = 0.0

    def _flush() -> None:
        nonlocal acc, acc_pages
        if acc:
            booklets.append({"chapters": [c["title"] for c in acc], "pages_est": round(acc_pages, 1), "oversized": False})
            acc, acc_pages = [], 0.0

    for ch in chapters:
        pages = estimate_pages(
            ch.get("chars", 0), ch.get("tables", 0), ch.get("table_rows", 0), ch.get("images", 0)
        )
        if pages > soft_cap:  # 规则 A: 单章超限整章成册(2A)
            _flush()
            booklets.append({"chapters": [ch["title"]], "pages_est": pages, "oversized": True})
            warnings.append(f"单章超软上限({pages:.1f}>{soft_cap:.0f}页), 整章成册: {ch['title']}")
        elif acc_pages + pages > soft_cap:  # 规则 B: 章边界切册
            _flush()
            acc, acc_pages = [ch], pages
        else:
            acc.append(ch)
            acc_pages += pages
    _flush()

    # 规则 C: 尾册过薄并入前册(仅一册时保留——薄总比空好)
    if len(booklets) >= 2 and booklets[-1]["pages_est"] < merge_below:
        tail = booklets.pop()
        booklets[-1]["chapters"].extend(tail["chapters"])
        booklets[-1]["pages_est"] = round(booklets[-1]["pages_est"] + tail["pages_est"], 1)
        warnings.append(
            f"尾册 {tail['pages_est']:.1f} 页 <{merge_below:.0f}, 并入前册: {'、'.join(tail['chapters'])}"
        )
    return booklets, warnings


def assign_filenames(doc: str, booklets: list[dict]) -> list[str]:
    """册序命名(契约表): 依切册顺序 01..NN, 首章短名取每册第一章。"""
    return [booklet_filename(doc, i, b["chapters"][0]) for i, b in enumerate(booklets, 1)]


def render_index(groups: list[dict], extra_notes: list[str] | None = None) -> str:
    """索引卷渲染(契约表: 册清单[文件名/文档属/章节范围/估算页数] + 附注区)。

    groups: [{"doc": "整体方案"|"技术卷", "files": [文件名...], "booklets": plan 输出}]
    索引卷是 build_output 对最终册集的确定性投影(非 LLM 内容, Revision 4), 分册
    导航与合并导出顺序以此为准。
    """
    lines = [
        "# 总目录索引",
        "",
        "> 本卷由 build_output 确定性投影生成(非 LLM 内容)。分册导航与合并导出顺序",
        "> 以本卷为准; Word 页码/目录在导出层生成, md 层不写页码(geo D11 同款约定)。",
        "",
    ]
    for group in groups:
        lines.append(f"## {group['doc']}册组({len(group['booklets'])} 册)")
        lines.append("")
        lines.append("| 册 | 文件 | 章节范围 | 估算页数 |")
        lines.append("| --- | --- | --- | --- |")
        for i, (filename, booklet) in enumerate(zip(group["files"], group["booklets"]), 1):
            span = " → ".join(booklet["chapters"]) if booklet["chapters"] else "(空)"
            if booklet.get("oversized"):
                span += "(单章超限整章成册)"
            lines.append(f"| {i:02d} | {filename} | {span} | {booklet['pages_est']} |")
        lines.append("")
    if extra_notes:
        lines.append("## 附注")
        lines.append("")
        lines.extend(f"- {note}" for note in extra_notes)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def total_pages(booklets: list[dict]) -> float:
    """册组页数合计(索引/摘要用)。"""
    return round(sum(b["pages_est"] for b in booklets), 1)


def ceil_pages(booklets: list[dict]) -> int:
    """册组页数上取整(整数页口径场景)。"""
    return math.ceil(total_pages(booklets))
