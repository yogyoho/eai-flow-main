# EAI-CUSTOM: 煤矿环评报告样例库 二期（BS3 ③提取流水线 MVP）——source 定位/章节大纲/实体候选。
# 章节双通道正则沿用在 KF 抽取管道（knowledge_factory.pipeline/doc_parser）中验证过的模式族；
# 实体候选移植 skills/public/coal-eia-report/references/sample_entities/（gen_sample_entities_t4.py）
# 的生成思路：后缀词匹配 + 泛词(GENERIC)过滤，仅做候选枚举（非 per-sample 注册表精标）。
"""Extraction pipeline for the coal EIA sample bank (phase 2).

Pipeline: locate source (.txt direct read / .docx via stdlib zip+ElementTree,
.doc or encrypted -> guidance error) -> chapter outline (dual-channel regex +
CR normalization + TOC-region skip) -> entity candidates (suffix-word match)
-> outline_json dict (caller persists into ``kf_samples.outline_json``).
"""

import json
import logging
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

# 大文件超时防护：超过此体积的源文件直接拒绝（环评报告书 docx 实测量级 <50MB）
MAX_SOURCE_BYTES = 150 * 1024 * 1024

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class ExtractSourceError(Exception):
    """source 定位/读取失败（.doc 未转换、加密、超大、格式不支持、文件缺失）——路由层转 400+guidance"""


# ── CR 归一化 ──


def normalize_cr(text: str) -> str:
    r"""CRLF / 孤 CR 归一为 \n（txt 转换产物常见混合行尾，先归一再匹配行首正则）。"""
    return re.sub(r"\r\n?", "\n", text)


# ── 中文数字 → int（第X章 连续性体检用） ──

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn_to_int(s: str) -> int | None:
    """一二三…十/百 + 半角数字混合解析（'十'=10、'十三'=13、'一百零三'=103、'13'=13）。"""
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    total, digit = 0, 0  # digit = 挂起个位（十/百/千 落位即入 total）
    for ch in s:
        if ch in _CN_DIGITS:
            digit = _CN_DIGITS[ch]
        elif ch == "十":
            total += (digit or 1) * 10
            digit = 0
        elif ch == "百":
            total += (digit or 1) * 100
            digit = 0
        elif ch == "千":
            total += (digit or 1) * 1000
            digit = 0
        else:
            return None
    return total + digit if (total or digit) else None


# ── 章节大纲提取（双通道 + 目录区启发跳过） ──

# 目录行：行尾页码（tab / 3+空格 / 点导引线 / 省略号导引线）
_TOC_LINE = re.compile(r".*(?:\t|\s{3,}|\.{4,}|…{2,})\s*\d+\s*$")
# 目录行补充：标题样式行（数字/中文章节开头）+ 单空格尾页码（"4 环境影响预测与评价 4"，
# 真标题不以页码数字结尾，凡此形态皆目录条目）
_HEAD_START = re.compile(r"^\d{1,2}(?:\.\d{1,2})?[\s\t]|^第[一二三四五六七八九十百千\d]+[章节]")
_TOC_PAGE_TAIL = re.compile(r"\s\d+$")


def _toc_like(line: str) -> bool:
    return bool(_TOC_LINE.match(line)) or (bool(_HEAD_START.match(line)) and bool(_TOC_PAGE_TAIL.search(line)))


# 通道一：阿拉伯章号 "1 总论" / "12\t附则"
_ARABIC_CH = re.compile(r"^(\d{1,2})[\s\t]+(\S.*)$")
# 通道一：中文章 "第一章 总论" / "第十三章附则"（章/节均按章级登记，family 由质检侧区分）
_CN_CH = re.compile(r"^(第[一二三四五六七八九十百千\d]+[章节])[\.、\s]?\s*(.*)$")
# 通道二：二级节 "1.1 井田境界"
_ARABIC_SEC = re.compile(r"^(\d{1,2})\.(\d{1,2})[\s\t]+(\S.*)$")
# 噪声守卫（同 doc_parser 验证过的判定线）：真标题不含子句/句末标点
_CLAUSE_PUNCT = set("，。；！？,;!?")
_TABLE_CAPTION = re.compile(r"^表\s*\d+")
# 量词/单位开头不是章标题（"3 个月内" 类正文噪声）。集合刻意极小：EIA 章节标题
# 高频以 项目/环境/保护/人员/年度/计划 等词开头（项/人/年/月/日/条/层/座 等字
# 均出现在真标题里，实证 "2 项目概况"、"1.1 项目由来" 被误杀），只留真量词字。
_UNIT_LEAD = "个台套名次吨米亩户批"
MAX_HEAD_LINE = 80


def _is_heading_noise(line: str) -> bool:
    if len(line) > MAX_HEAD_LINE or any(c in _CLAUSE_PUNCT for c in line):
        return True
    if _TABLE_CAPTION.match(line):
        return True
    return False


def _clean_title(title: str) -> str:
    return title.strip().strip("　 ").rstrip("—-_")


def extract_outline(text: str) -> list[dict]:
    """双通道章节大纲：[{no: '1'|'第一章', no_int: 1|None, title, sections: [{no,title}]}]。

    目录区启发：连续 >=3 条带页码目录行进入目录区，区内行（含无页码残行）全部跳过，
    直到空行或连续 2 条非目录行把区域打断——防目录树与正文双份入树。
    阿拉伯章号要求严格递增（容差 +3 以保留源文档真跳号，供质检编号体检上报）。
    """
    chapters: list[dict] = []
    seen: set[tuple[str, str]] = set()
    consec_toc = 0
    in_toc_region = False
    non_toc_after_region = 0
    last_no = 0

    def _push(no: str, no_int: int | None, title: str) -> None:
        nonlocal last_no
        if no_int is not None:
            if no_int <= last_no or no_int > last_no + 3:
                return  # 非递增（页眉/引用重复）或跳得太远（正文噪声）——弃
            last_no = no_int
        key = (no, title)
        if key in seen:
            return
        seen.add(key)
        chapters.append({"no": no, "no_int": no_int, "title": title, "sections": []})

    for raw in normalize_cr(text).split("\n"):
        line = raw.strip()
        if not line:
            in_toc_region = False
            consec_toc = 0
            non_toc_after_region = 0
            continue
        if _toc_like(line):
            consec_toc += 1
            if consec_toc >= 3:
                in_toc_region = True
            continue
        if in_toc_region:
            # 目录区内无页码残行同样跳过；连续 2 条非目录行视为目录区结束（当前行仍弃）
            non_toc_after_region += 1
            if non_toc_after_region >= 2:
                in_toc_region = False
            continue
        if _is_heading_noise(line):
            continue

        if m := _CN_CH.match(line):
            token, rest = m.group(1), _clean_title(m.group(2))
            no_int = cn_to_int(token[1:-1])
            _push(token, no_int, rest or token)
            continue
        if m := _ARABIC_SEC.match(line):
            if chapters:
                no = f"{m.group(1)}.{m.group(2)}"
                title = _clean_title(m.group(3))
                if not _is_heading_noise(title) and title and title[0] not in _UNIT_LEAD:
                    if (no, title) not in seen:
                        seen.add((no, title))
                        chapters[-1]["sections"].append({"no": no, "title": title})
            continue
        if m := _ARABIC_CH.match(line):
            title = _clean_title(m.group(2))
            if not title or title[0] in _UNIT_LEAD:
                continue  # "3 个月内" 类量词开头的正文行
            _push(m.group(1), int(m.group(1)), title)
    return chapters


# ── 实体候选（后缀词匹配，移植 gen_sample_entities_t4.py 思路） ──

# 桶 → 后缀词（长词优先，防 "保护区" 吃掉 "自然保护区" 前半）
_SUFFIX_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("mines", ("煤矿", "矿井", "露天矿", "选煤厂", "矿区", "矿")),
    ("sensitive", ("自然保护区", "饮用水水源保护区", "水源保护区", "水源地", "湿地公园", "风景名胜区", "森林公园", "生态保护红线", "保护区")),
    ("waters", ("水库", "河流")),
]
_NAME_CHARS = r"[一-龥A-Za-z0-9]"
_SUFFIX_RES = [(bucket, re.compile("(" + _NAME_CHARS + "{2,12}?(?:" + "|".join(sfx) + "))")) for bucket, sfx in _SUFFIX_RULES]
# 泛词（gen 脚本 GENERIC 思路）：裸泛词不进候选，带专名前缀的保留
_GENERIC = {
    "煤矿",
    "矿井",
    "生产矿井",
    "基建矿井",
    "技改矿井",
    "小煤矿",
    "乡镇煤矿",
    "露天矿",
    "选煤厂",
    "矿区",
    "井田",
    "本矿",
    "该矿",
    "自然保护区",
    "水源地",
    "饮用水水源地",
    "饮用水水源保护区",
    "水源保护区",
    "湿地公园",
    "风景名胜区",
    "森林公园",
    "生态保护红线",
    "保护区",
    "河流",
    "水库",
}
_LEAD_STOP = "该本各等及其与和或之该周边附近邻近现有在建拟建新建改扩建"
_MAX_PER_BUCKET = 50


def _trim_entity(name: str) -> str:
    """去掉候选前后的黏连虚词，返回规范化实体名；无效返回空串。

    后缀词匹配的固有缺陷是左黏连（"项目为月儿湾矿井"、"刘家沟水库为饮用水水源地"）：
    先按功能词（为/的/及/…）切尾——尾段有效取尾段；尾段无效（泛词/过短）则弃候选
    （首段通常会被它自己的桶规则干净命中，弃掉防跨桶重复）。
    """
    name = name.strip("（）()、，。;；:：“”\"' \t　")
    for sep in ("为", "的", "等", "及", "和", "与", "或", "在", "由", "从", "含", "是", "位于", "属于"):
        if sep in name:
            tail = name.rpartition(sep)[2].strip("（）()、，。;；: \t　")
            while tail and tail[0] in _LEAD_STOP:
                tail = tail[1:]
            if len(tail) >= 2 and tail not in _GENERIC and not any(s in tail for s in ("厂新建", "工程")):
                return tail
            return ""  # 尾段无效——首段留给各自的桶规则，防跨桶重复
    while name and name[0] in _LEAD_STOP:
        name = name[1:]
    return name.strip()


def extract_entities(text: str) -> dict[str, list[str]]:
    """实体候选：{bucket: [name, ...]}——后缀词匹配 + 泛词过滤，每桶去重截断 50。"""
    out: dict[str, list[str]] = {}
    for bucket, rx in _SUFFIX_RES:
        names: list[str] = []
        for m in rx.finditer(normalize_cr(text)):
            name = _trim_entity(m.group(1))
            if len(name) < 2 or name in _GENERIC or name in names:
                continue
            names.append(name)
            if len(names) >= _MAX_PER_BUCKET:
                break
        out[bucket] = names
    return out


# ── source 定位与读取 ──


def read_source_text(source_path: str) -> tuple[str, str]:
    """按扩展名读取源文本，返回 (text, source_kind)。失败抛 ExtractSourceError（路由转 400）。

    .txt 直接读（utf-8 失败回退 gb18030）；.docx 用 stdlib zip+ElementTree 读
    word/document.xml 提取段落文本；.doc（OLE 复合文档）不可直接解析——400 提示走
    doc_convert；其余扩展名同 .doc 处理。
    """
    path = Path(source_path)
    if not path.is_file():
        raise ExtractSourceError(f"源文件不存在: {source_path}（请核对台账 source_path，或先走入库向导上传）")
    size = path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ExtractSourceError(f"源文件过大（{size // (1024 * 1024)}MB > 上限 {MAX_SOURCE_BYTES // (1024 * 1024)}MB），拒绝同步提取以防超时")
    ext = path.suffix.lower().lstrip(".")
    if ext == "txt":
        return _read_txt(path), "txt"
    if ext == "docx":
        return _read_docx(path), "docx"
    if ext == "doc":
        raise ExtractSourceError("旧版 .doc（OLE 复合文档）无法直接解析：请先走 doc_convert 转换为 .docx 或 .txt，更新台账 source_path 后重试")
    raise ExtractSourceError(f"不支持的源格式 .{ext}：仅支持 .txt/.docx；.doc 请先走 doc_convert 转换")


def _read_txt(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            if "word/document.xml" not in zf.namelist():
                raise ExtractSourceError("无法读取：不是有效的 .docx 包（缺 word/document.xml）——若是加密文档请先解密，若是 .doc 请走 doc_convert")
            xml_bytes = zf.read("word/document.xml")
    except zipfile.BadZipFile as e:
        raise ExtractSourceError(f"无法读取：文件损坏或加密（{e}）——加密文档请先解密，.doc 请走 doc_convert 转换") from e
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as e:
        raise ExtractSourceError(f"word/document.xml 解析失败：{e}") from e
    p_tag, t_tag = f"{{{_W_NS}}}p", f"{{{_W_NS}}}t"
    paragraphs: list[str] = []
    for p in root.iter(p_tag):
        line = "".join(t.text or "" for t in p.iter(t_tag)).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


# ── 流水线编排 ──

OUTLINE_SCHEMA = "eia-sample-outline/v1"


def run_extract(source_path: str, source_kind: str = "auto") -> dict:
    """完整提取：返回 {source_kind, source_chars, chapters, candidates, extracted_at}。

    source_kind: txt|docx|auto（auto 按扩展名）。sync 函数——异步路由须经 asyncio.to_thread 调用。
    """
    if source_kind not in ("auto", "txt", "docx"):
        raise ExtractSourceError(f"未知 source_kind: {source_kind}（可选 txt/docx/auto）")
    text, resolved_kind = read_source_text(source_path)
    text = normalize_cr(text)
    return {
        "schema": OUTLINE_SCHEMA,
        "source_kind": resolved_kind,
        "extracted_at": datetime.now(UTC).isoformat(),
        "source_chars": len(text),
        "chapters": extract_outline(text),
        "candidates": extract_entities(text),
    }


def outline_text_for_scan(outline: dict) -> str:
    """outline_json 的可扫描文本化（质检隐私扫描用：只扫标题与候选名，不存正文）。"""
    try:
        return json.dumps(outline, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""
