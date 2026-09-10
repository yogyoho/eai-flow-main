"""bank_compile——投标样例入库编译器(v4 WP-2/G1, 离线一键产全部衍生物)。

流程: 装载(标书 md/docx) → 全文脱敏(--map 显式对照 + 自动模式; 先脱敏后切片——T2 评审接线,
章 title 取自 redacted 文本, 标题里的机构名不绕过 --map) → 章切片 → 深度统计(M-1 段长分布,
P25=absolute_floor / median=global_median) → 四产物确定性落盘(slug 目录 full.md+chapters/、
bank_index.json、depth_targets.json(库级聚合——floor=各册 min、median=各册中位, 与编译顺序无关)、
registration.json——全 sort_keys 无时间戳, 重跑字节一致)
→ registration.json 供 backend/scripts/bid_seed_samples.py 入 BidSample 台账(file_hash 恰 64 字符)
→ 可选 RAGFlow bid_samples 域推送(失败=warnings 不阻塞, Task 5 接入)。

残留闸门: compile_bank 返回 residual 证据; 非空 → 全量证据行上 stderr 且 rc=1 零落盘
(bank_index/depth_targets/registration/切片全不写, 不静默出库——Task 4 闸门已落)。

stdlib 自包含(技能=自包含分发单元)。离线维护者工具, 不进 SKILL.md 速查表。
用法:
  python bank_compile.py --input 标书.md --title "江西师范大学课堂观测系统" \
    --industry 信息技术 --category IT软件平台 --bank-dir references/samples_bank \
    [--map map.json] [--ragflow-push]   (--map 已接入; --ragflow-push 于 Task 5 接入)
退出码: 0 干净 / 1 用法错误或残留命中(零落盘)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics
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
    (封面/篇首段), 其下内容不立章——全文仍进 slug 目录 full.md, 章切片只收 H2 节,
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
    mapping 键=原文, 值=脱敏占位。调用方(compile_bank)必须先对全文 redact 再 split_chapters
    (T2 评审接线)——章 title 来自 redacted 标题行, 机构名才不绕过 --map。"""
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


def slugify(title: str) -> str:
    """sha1(title)[:12] 小写 hex——ASCII 确定性目录名(CJK 题名不进文件系统, 可读名进 bank_index)。"""
    return hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]


def percentile(sorted_vals: list[int], pct: int) -> int:
    """索引取整取值: idx=len*pct//100 截断钳位到 [0, n-1]; 空表返 0。入参须已升序排序。"""
    if not sorted_vals:
        return 0
    return sorted_vals[min(len(sorted_vals) * pct // 100, len(sorted_vals) - 1)]


def compile_bank(text: str, *, title: str, industry: str, category: str, mapping: dict[str, str]) -> dict:
    """纯函数编译(无 IO): 先对全文 redact 再切章(T2 评审接线——章 title 来自 redacted 标题行,
    机构名不绕过 --map) → M-1 段长分布(剔 #/| 结构行) → depth_targets(P25=absolute_floor/
    median=global_median, calibrated_from=内容指纹) → registration_item(bid_samples 台账契约,
    file_hash=sha256(redacted) 恰 64 字符) → residual 证据(main 残留闸门消费: 非空 → rc=1 零落盘)。"""
    redacted = redact(text, mapping)
    chapters = split_chapters(redacted)
    lengths = sorted(paragraph_lengths(redacted))
    file_hash = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
    slug = slugify(title)
    return {
        "slug": slug,
        "title": title,
        "redacted": redacted,
        "chapters": chapters,
        "file_hash": file_hash,
        "depth_targets": {
            "absolute_floor": percentile(lengths, 25),
            "global_median": percentile(lengths, 50),
            "paragraph_count": len(lengths),
            "calibrated_from": file_hash,
        },
        "registration_item": {
            "slug": slug,  # 非台账契约字段(pydantic 未知键忽略), 供 main 幂等去重
            "title": title,
            "source_path": f"{slug}/full.md",  # bank 根相对路径(可移植, 不落绝对路径)
            "file_hash": file_hash,
            "industry": industry,
            "project_category": category,
            "scenario": "bid_sample",
            "status": "indexed",
            "notes": f"chapters={len(chapters)}; paragraphs={len(lengths)}",
        },
        "residual": residual_scan(redacted),
    }


def _chapter_filename(idx: int, title: str) -> str:
    """chNN__{短名}.md——序号定序, 短名=题名清洗(路径敌对字符/空白折叠为 _, 截 24 字)确定性派生。"""
    short = re.sub(r'[\\/:*?"<>|\s]+', "_", title).strip("._")[:24] or "untitled"
    return f"ch{idx:02d}__{short}.md"


def _write_text(path: Path, text: str) -> None:
    """newline="\n" 强制 LF——Windows/Linux 落盘字节一致(跨机确定性, 不吃 os.linesep 翻译)。"""
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _write_json(path: Path, obj: dict | list) -> None:
    """sort_keys+indent2+LF 结尾——确定性 JSON 落盘(重跑字节一致)。"""
    _write_text(path, json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _load_bank_json(path: Path, default: dict, *, require_items_list: bool = False) -> dict:
    """M-3: 既有 JSON 产物损坏/形态异常 → stderr 提示后按 default 重置(不裸 traceback,
    对齐 load_text 可操作报错风格)——产物可由输入全量重建, 重置优于中断。"""
    if not path.is_file():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("顶层非对象")
        if require_items_list and not isinstance(data.get("items", []), list):
            raise ValueError("items 非列表")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        print(f"警告: {path.name} 损坏或形态异常({exc}), 已重置重建——如需保留请先备份", file=sys.stderr)
        return dict(default)
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bank_compile.py", description="投标样例入库编译器(离线)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--industry", default="信息技术")
    ap.add_argument("--category", default="IT软件平台")
    ap.add_argument("--bank-dir", required=True)
    ap.add_argument("--map", default=None, help="显式脱敏对照 JSON 文件(键=原文, 值=脱敏占位)")
    args = ap.parse_args(argv)

    mapping: dict[str, str] = {}
    if args.map:  # M-7: 坏 JSON 包成可操作报错(对齐 load_text 风格), 不裸 traceback
        try:
            mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))
            if not isinstance(mapping, dict):
                raise ValueError("顶层非对象")
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"map 文件 JSON 解析失败: {args.map}({exc}; 须为对象, 键=原文, 值=脱敏占位)") from exc

    text = load_text(Path(args.input))
    result = compile_bank(text, title=args.title, industry=args.industry, category=args.category, mapping=mapping)

    if not result["chapters"]:  # M-6: 零章=极端形态(如自定义样式 docx 全量丢弃), 提示而非静默
        print("警告: 切片 0 章——输入无 H2 章标题(自定义样式 docx 可能全量丢弃), 请核对标题样式", file=sys.stderr)
    # 残留闸门(Task 4): 脱敏后仍有残留 → 全量证据行上 stderr 后 rc=1, 位于一切落盘之前
    # (bank_index/depth_targets/registration/切片全不写)——不静默出库, 处置=补 --map 对照或修订源文后重跑。
    if result["residual"]:
        print(f"残留扫描 {len(result['residual'])} 处命中——拒绝出库(rc=1, 零落盘), 请补 --map 对照或修订源文后重试:", file=sys.stderr)
        for ln in result["residual"]:
            print(f"  · {ln}", file=sys.stderr)
        return EXIT_ERROR

    bank_dir = Path(args.bank_dir)
    slug = result["slug"]
    slug_dir = bank_dir / slug
    chapters_dir = slug_dir / "chapters"
    if chapters_dir.is_file():  # M-6: 路径被文件占位(异常残留) → unlink 兜底再建目录
        chapters_dir.unlink()
    if chapters_dir.is_dir():  # 旧切片清场再重写——源文件修订后重编译不留陈旧 chNN
        shutil.rmtree(chapters_dir)
    chapters_dir.mkdir(parents=True, exist_ok=True)
    _write_text(slug_dir / "full.md", result["redacted"] + "\n")
    chapter_entries = []
    for i, ch in enumerate(result["chapters"], 1):
        fname = _chapter_filename(i, ch["title"])
        _write_text(chapters_dir / fname, ch["text"] + "\n")
        chapter_entries.append({"file": f"chapters/{fname}", "title": ch["title"]})

    index_path = bank_dir / "bank_index.json"
    index = _load_bank_json(index_path, {})
    prior = index.get(slug)
    if isinstance(prior, dict) and prior.get("file_hash") and prior["file_hash"] != result["file_hash"]:  # M-2: 同题重编内容漂移可见
        print(f"警告: slug={slug} 重编译内容漂移: file_hash {str(prior['file_hash'])[:12]}… → {result['file_hash'][:12]}…(旧产物将被覆盖)", file=sys.stderr)
    index[slug] = {
        "title": args.title,
        "industry": args.industry,
        "category": args.category,
        "file_hash": result["file_hash"],
        "depth": result["depth_targets"],
        "chapters": chapter_entries,
    }
    _write_json(index_path, index)

    # depth_targets.json=库级深度门基准(I-1 评审修订: 对 bank_index 全册聚合——floor 取 min、
    # median 取中位, 根除先编 A 再编 B 时的 last-writer-wins; geo calibrate.py 先例即对全样例库取
    # median)。键名 absolute_floor/global_median 为 build_output 消费契约保持稳定; calibrated_from
    # 指向触发本次重校准的内容指纹; per-sample 深度仍在 bank_index[slug].depth。
    depths = [e["depth"] for e in index.values() if isinstance(e, dict) and isinstance(e.get("depth"), dict)]
    floors = [d["absolute_floor"] for d in depths if isinstance(d.get("absolute_floor"), int)]
    medians = [d["global_median"] for d in depths if isinstance(d.get("global_median"), int)]
    bank_targets = {
        "absolute_floor": min(floors) if floors else result["depth_targets"]["absolute_floor"],
        "global_median": statistics.median(medians) if medians else result["depth_targets"]["global_median"],
        "paragraph_count": sum(int(d.get("paragraph_count", 0)) for d in depths),
        "calibrated_from": result["file_hash"],
    }
    _write_json(bank_dir / "depth_targets.json", bank_targets)

    reg_path = bank_dir / "registration.json"
    reg = _load_bank_json(reg_path, {"items": []}, require_items_list=True)
    items = [it for it in reg.get("items", []) if isinstance(it, dict) and it.get("slug") != slug]  # M-4: 旧行缺 slug 不丢
    items.append(result["registration_item"])
    items.sort(key=lambda it: str(it.get("slug", "")))  # M-4: 缺 slug 空串排首, 不崩
    _write_json(reg_path, {"items": items})

    print(
        json.dumps(
            {
                "command": "bank_compile",
                "slug": slug,
                "chapters": len(result["chapters"]),
                "paragraphs": result["depth_targets"]["paragraph_count"],
                "absolute_floor": bank_targets["absolute_floor"],
                "global_median": bank_targets["global_median"],
                "residual": len(result["residual"]),
            },
            ensure_ascii=False,
        )
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
