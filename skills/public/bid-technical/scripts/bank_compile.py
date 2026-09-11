"""bank_compile——投标样例入库编译器(v4 WP-2/G1, 离线一键产全部衍生物)。

流程: 装载(标书 md/docx) → 全文脱敏(--map 显式对照 + 自动模式; 先脱敏后切片——T2 评审接线,
章 title 取自 redacted 文本, 标题里的机构名不绕过 --map) → 章切片 → 技术章筛选(select_tech_chapters,
Plan 4 Task 2 用户定案 2026-09-11「检索语料只收技术章」) → 深度统计(**口径=技术章拼接文**的
M-1 段长分布, P25=absolute_floor / median=global_median; 切片/登记保持全册 1:1 不变) →
四产物确定性落盘(slug 目录 full.md+chapters/、bank_index.json、
depth_targets.json(库级聚合——floor=各册 min、median=各册中位, 与编译顺序无关; scope=technical_chapters)、
registration.json——全 sort_keys 无时间戳, 重跑字节一致)
→ registration.json 供 backend/scripts/bid_seed_samples.py 入 BidSample 台账(file_hash 恰 64 字符)
→ 可选 RAGFlow bid_samples 域推送(--ragflow-push, Task 5 + Plan 4 Task 2): 只推技术章拼接文
  (文档名不变——同名先删再传幂等自动替换旧全册文档), 位于一切本地产物落盘之后——
  目标/凭证走 BID_RAGFLOW_* env, 同名词旧版先删再传(幂等, geo_samples
  push_reports_to_ragflow 同款)+解析触发; 未配置=跳过, 任何失败=warnings——本地衍生物已先行
  落盘可用, 推送是辅助通道绝不阻塞出库/改 rc; 技术集为空 → fail-closed 跳过绝不回退推全册
  (summary 增 ragflow_skip_reason=no_tech_chapter, stderr 列全章标题供修词表/--map)。

残留闸门: compile_bank 返回 residual 证据; 非空 → 全量证据行上 stderr 且 rc=1 零落盘
(bank_index/depth_targets/registration/切片全不写, 不静默出库——Task 4 闸门已落)。
元数据同门(I-1 评审): --title 等元数据字段不经正文 redact 管线——bank_index/registration
组装后在内存序列化预写扫描(RESIDUAL_RE + --map 键原文名), 命中即 rc=1 零落盘。

stdlib 自包含(技能=自包含分发单元)。离线维护者工具, 不进 SKILL.md 速查表。
用法:
  python bank_compile.py --input 标书.md --title "某大学【1】课堂观测系统" \
    --industry 信息技术 --category IT软件平台 --bank-dir references/samples_bank \
    [--map map.json] [--ragflow-push]   (--map/--ragflow-push 均已接入)
退出码: 0 干净 / 1 用法错误(argparse 用法错误已改道 1——2 保留给 ingest 的 OCR 分流,
  对齐 score_simulate/state_guard 家族惯例)或残留命中(零落盘)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import sys
import urllib.error
import urllib.request
import uuid
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


# 技术章筛选词表(Plan 4 Task 2, 用户定案 2026-09-11「检索语料只收技术章」): 样例库是技术响应
# 供源(Skill B stage-4a 检索/定长只取技术条款), 商务章(投标函/资质/报价/授权/开标一览表…)进
# RAGFlow 语料=检索噪声、进深度统计=污染 P25 基线。真实语料钉: 江西师大册技术章题为
# 「第二章 项目内容、技术指标」——「技术指标」与「技术标」无子串关系, 必须显式入表
# (缺项会让真实册技术集为空 → 推送 fail-closed 跳过, 见 test_tech_whitelist_matches_real_corpus_titles)。
TECH_TITLE_RE = re.compile("技术标|技术部分|技术方案|技术响应|技术要求|技术指标|实施方案|服务方案|技术服务|项目实施|技术文件|总体理解|偏离说明")
TECH_SCOPE_H1_RE = re.compile("技术标|技术部分|技术文件|技术方案")  # H1 命中→其下 H2 全部继承


def select_tech_chapters(chapters: list[dict]) -> tuple[list[str], list[str]]:
    """技术章筛选(用户定案 2026-09-11): 标题关键词白名单+H1 范围继承。
    返回 (技术章文本列表, 技术章标题列表); 空集=合法态(调用方 fail-closed 告警)。
    注: 当前 split_chapters 只切 H2、level 恒 2(H1=篇标题不立章), H1 继承分支是切片器
    未来扩展的潜伏守卫——现阶段实际选择=纯标题白名单(词表维护点=TECH_TITLE_RE)。"""
    tech: list[str] = []
    titles: list[str] = []
    inherited = False
    for c in chapters:
        if c["level"] == 1:
            inherited = bool(TECH_SCOPE_H1_RE.search(c["title"]))
        if inherited or TECH_TITLE_RE.search(c["title"]):
            tech.append(c["text"])
            titles.append(c["title"])
    return tech, titles


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


# 序列化元数据的哈希假阳性免疫: 元数据全文含 sha256 file_hash/calibrated_from 摘要与 12-hex
# slug——纯 hex 串可偶然拼出手机号形态(实证: 某样例摘要含 '18156555939' 数字体串, ~10%/册概率
# 致元数据闸门误拒 rc=1 零落盘)。形态扫描前剥除「整串引号包裹的 64-hex 摘要值 / 12-hex slug 值 /
# slug/full.md 路径」三类 token(真实残留 token 都嵌在含中文的长串里, 不会被整串匹配误伤);
# --map 键原文名检查仍跑原文(键=真名, 与摘要无关)。
_META_HEX_VALUE_RE = re.compile(r'"[0-9a-f]{64}"|"[0-9a-f]{12}/full\.md"|"[0-9a-f]{12}"')


def metadata_residual_scan(text: str, mapping: dict[str, str]) -> list[str]:
    """元数据残留扫描(I-1 评审: 元数据通道与正文同门, fail-closed)。

    --title 等元数据字段不经正文 redact 管线(脱敏引擎只处理标书正文), 真名机构写进
    title 会原样随技能分发包(bank_index/registration)入库。对**序列化后的元数据全文**:
      1) 剥除哈希/slug 类 hex token(_META_HEX_VALUE_RE, 防摘要偶发数人体串假阳性)后
         跑正文同款 RESIDUAL_RE(金额/证号/手机号等形态);
      2) 逐个检查 --map 键原文名(原文)——维护者显式认定的敏感原名, 出现在元数据即命中。
    证据行带命中 token 与上下文(序列化 JSON 是超长单行, 全行截断会看不见命中点)。
    """
    hits: list[str] = []
    form_text = _META_HEX_VALUE_RE.sub('""', text)
    for m in RESIDUAL_RE.finditer(form_text):
        hits.append(f"形态命中 {m.group(0)[:40]!r}: …{form_text[max(0, m.start() - 30): m.end() + 30]}…")
    for key in mapping:
        if key and key in text:
            i = text.index(key)
            hits.append(f"--map 键原文名泄入元数据 {key[:40]!r}: …{text[max(0, i - 30): i + len(key) + 30]}…")
    return hits


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
    机构名不绕过 --map) → 技术章筛选(select_tech_chapters, Plan 4 Task 2 用户定案) → M-1 段长
    分布(**口径=技术章拼接文**, 剔 #/| 结构行; 空技术集 → percentile 空表返 0 的 fallback, 不回退
    全册统计) → depth_targets(P25=absolute_floor/median=global_median, scope=technical_chapters,
    calibrated_from=内容指纹) → registration_item(bid_samples 台账契约, file_hash=sha256(redacted)
    恰 64 字符, notes 保持**全册**段数口径——切片/登记全册 1:1 纪律不变) → residual 证据(main
    残留闸门消费: 非空 → rc=1 零落盘)。tech_text/tech_titles 供 main 的 RAGFlow 推送范围(只推技术章)。"""
    redacted = redact(text, mapping)
    chapters = split_chapters(redacted)
    tech_texts, tech_titles = select_tech_chapters(chapters)
    tech_text = "\n\n".join(tech_texts)
    lengths = sorted(paragraph_lengths(tech_text))  # 深度统计口径=技术章(Plan 4 Task 2)
    book_paragraphs = len(paragraph_lengths(redacted))  # 全册段数: registration notes 专用(1:1 纪律)
    file_hash = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
    slug = slugify(title)
    return {
        "slug": slug,
        "title": title,
        "redacted": redacted,
        "chapters": chapters,
        "file_hash": file_hash,
        "tech_text": tech_text,
        "tech_titles": tech_titles,
        "depth_targets": {
            "absolute_floor": percentile(lengths, 25),
            "global_median": percentile(lengths, 50),
            "paragraph_count": len(lengths),
            "scope": "technical_chapters",
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
            "notes": f"chapters={len(chapters)}; paragraphs={book_paragraphs}",
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


# --- RAGFlow bid_samples 域推送(Task 5, 可选辅助通道: 失败=warnings 不阻塞) ------------------------
# stdlib urllib 自包含(技能=自包含分发单元, 不 import 平台 RAGFlowClient); 端点形态对齐
# backend/app/extensions/knowledge/client.py(API_PREFIX=/api/v1, Bearer 凭证, code=0 成功)。

RAGFLOW_DATASET_ENV = "BID_RAGFLOW_DATASET_ID"
RAGFLOW_API_BASE_ENV = "BID_RAGFLOW_API_BASE"
RAGFLOW_API_KEY_ENV = "BID_RAGFLOW_API_KEY"
RAGFLOW_API_BASE_DEFAULT = "http://ragflow:9380"


def _ragflow_post(base: str, api_key: str, path: str, *, data: bytes | None = None, content_type: str = "application/json", method: str = "POST") -> dict:
    """单次 urllib 请求(60s 超时; data=None 无 body, GET 列表复用); RAGFlow 约定 code=0 成功——
    非 0 视同失败上抛(调用方统一吞掉记 warning)。"""
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": content_type},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("code") not in (0, None):
        raise RuntimeError(str(payload.get("message") or payload)[:200])
    return payload


def _ragflow_list_doc_ids(base: str, api_key: str, dataset_id: str) -> dict[str, str]:
    """分页拉 dataset 文档 name→id 映射(GET /datasets/{id}/documents?page=N&size=100,
    上游 page_size 上限 100, 分页口径同 geo push_reports_to_ragflow 幂等前置)。"""
    mapping: dict[str, str] = {}
    page = 1
    while True:
        payload = _ragflow_post(base, api_key, f"/api/v1/datasets/{dataset_id}/documents?page={page}&size=100", method="GET")
        data = payload.get("data")
        docs = data.get("docs", []) if isinstance(data, dict) else []
        for d in docs if isinstance(docs, list) else []:
            if isinstance(d, dict) and d.get("name") and d.get("id"):
                mapping[str(d["name"])] = str(d["id"])
        total = data.get("total") if isinstance(data, dict) else None
        if not docs or not isinstance(total, int) or page * 100 >= total:
            break
        page += 1
    return mapping


def _ragflow_delete_docs(base: str, api_key: str, dataset_id: str, doc_ids: list[str]) -> None:
    """DELETE /datasets/{id}/documents body {"ids": [...]}(批量删除约定, 同 knowledge/client.delete_document 形态)。"""
    _ragflow_post(base, api_key, f"/api/v1/datasets/{dataset_id}/documents", data=json.dumps({"ids": doc_ids}).encode("utf-8"), method="DELETE")


def _ragflow_upload(base: str, api_key: str, dataset_id: str, name: str, content: bytes) -> str:
    """multipart 上传 redacted 全文(POST /api/v1/datasets/{id}/documents), 返回 document id。
    上游 data 为单元素数组(knowledge/client.upload_document 同款归一); 手拼 multipart body
    (urllib 无 httpx files 语义), boundary 用 uuid4——网络载荷非持久产物, 不受确定性纪律约束。"""
    boundary = f"----bank_compile_{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f"Content-Type: text/markdown\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    payload = _ragflow_post(base, api_key, f"/api/v1/datasets/{dataset_id}/documents", data=body, content_type=f"multipart/form-data; boundary={boundary}")
    docs = payload.get("data")
    if isinstance(docs, list) and docs:
        docs = docs[0]
    doc_id = docs.get("id") if isinstance(docs, dict) else None
    if not doc_id:
        raise RuntimeError("响应缺 document id")
    return str(doc_id)


def ragflow_push(md: str, meta: dict) -> bool:
    """redacted 技术章拼接文推送 RAGFlow bid_samples 域(命名 <slug>.md, Plan 4 Task 2: 只推
    技术章——文档名不变, 同名先删再传幂等语义自动替换旧全册文档), 幂等契约同 geo_samples
    push_reports_to_ragflow: 分页 list 建 name→id 映射, 同名词旧版先删再传(重推送不留旧版/
    不堆积副本, 只删同名词不误删他人), 上传后触发服务端解析(上传不 parse=样例永不可检索,
    不等待解析完成)。dataset id / API key 缺失 → False+warning(跳过不算失败, 不触网);
    HTTPError 连同响应体摘要(M-3)/其余任何异常一律吞掉记 warning 返回 False——绝不阻塞
    主流程, 不改 rc(spec: 失败=warnings, 本地衍生物已先行落盘可用)。meta 恰 {"title"}
    (文件名 slug 派生自它), 推送目标一律以 env 当前值为准。"""
    dataset_id = (os.environ.get(RAGFLOW_DATASET_ENV) or "").strip()
    if not dataset_id:
        print(f"警告: 未配置 {RAGFLOW_DATASET_ENV}——跳过 RAGFlow 推送(本地衍生物已可用)", file=sys.stderr)
        return False
    api_key = (os.environ.get(RAGFLOW_API_KEY_ENV) or "").strip()
    if not api_key:
        print(f"警告: 未配置 {RAGFLOW_API_KEY_ENV}——跳过 RAGFlow 推送(本地衍生物已可用)", file=sys.stderr)
        return False
    base = (os.environ.get(RAGFLOW_API_BASE_ENV) or RAGFLOW_API_BASE_DEFAULT).rstrip("/")
    name = f"{slugify(str(meta.get('title') or 'sample'))}.md"
    try:
        stale_id = _ragflow_list_doc_ids(base, api_key, dataset_id).get(name)
        if stale_id:  # I-1 幂等: 同名先删再传(geo 同款)——重编重推不滞留旧版
            _ragflow_delete_docs(base, api_key, dataset_id, [stale_id])
        doc_id = _ragflow_upload(base, api_key, dataset_id, name, md.encode("utf-8"))
        _ragflow_post(base, api_key, f"/api/v1/datasets/{dataset_id}/chunks", data=json.dumps({"document_ids": [doc_id]}).encode("utf-8"))
        return True
    except urllib.error.HTTPError as exc:  # M-3: HTTP 状态+响应体摘要进告警(上游报错可见可处置)
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200].strip()
        except Exception:
            pass
        print(f"警告: RAGFlow 推送失败(HTTP {exc.code}: {detail or exc.reason})——本地衍生物已可用, 不阻塞出库", file=sys.stderr)
        return False
    except Exception as exc:  # 推送链路统一降级——RAGFlow 不可达不回滚出库(辅助通道定位)
        print(f"警告: RAGFlow 推送失败({exc})——本地衍生物已可用, 不阻塞出库", file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bank_compile.py", description="投标样例入库编译器(离线)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--industry", default="信息技术")
    ap.add_argument("--category", default="IT软件平台")
    ap.add_argument("--bank-dir", required=True)
    ap.add_argument("--map", default=None, help="显式脱敏对照 JSON 文件(键=原文, 值=脱敏占位)")
    ap.add_argument("--ragflow-push", action="store_true", help="落盘后推送 redacted 技术章拼接文到 RAGFlow bid_samples 域(env BID_RAGFLOW_* 配置; 失败=warnings 不阻塞; 技术集为空=跳过 no_tech_chapter 绝不回退推全册)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        # argparse 用法错误默认 SystemExit(2)——与 docstring「1 用法错误」不符, 且 2 已保留给
        # ingest 的 OCR 分流(撞号会把 CLI 误用误路由), 统一改道 EXIT_ERROR(T4 评审 Minor-1,
        # 对齐 score_simulate/state_guard 家族惯例); --help 等正常退出(code 0)原样放行。
        if not exc.code:
            return EXIT_OK
        print(f"[bank_compile] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}); 用法错误归退出码 1, 2 已保留给 ingest 的 OCR 分流(用 --help 查看用法)", file=sys.stderr)
        return EXIT_ERROR

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
    # 元数据在内存中先行组装(T7 评审 I-1): --title 等元数据字段不经正文 redact 管线,
    # 组装后序列化预写扫描(与正文同门 fail-closed), 一切落盘动作都排在两道闸门之后。
    chapter_files = [(_chapter_filename(i, ch["title"]), ch) for i, ch in enumerate(result["chapters"], 1)]
    chapter_entries = [{"file": f"chapters/{fname}", "title": ch["title"]} for fname, ch in chapter_files]
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

    # depth_targets.json=库级深度门基准(I-1 评审修订: 对 bank_index 全册聚合——floor 取 min、
    # median 取中位, 根除先编 A 再编 B 时的 last-writer-wins; geo calibrate.py 先例即对全样例库取
    # median)。键名 absolute_floor/global_median 为 build_output 消费契约保持稳定; calibrated_from
    # 指向触发本次重校准的内容指纹; per-sample 深度仍在 bank_index[slug].depth。
    # scope=technical_chapters(Plan 4 Task 2): 聚合的每册 depth 已是技术章口径, 库级基准同口径
    # (消费方 load_depth_targets 只读 absolute_floor/global_median, 新增键无害)。
    depths = [e["depth"] for e in index.values() if isinstance(e, dict) and isinstance(e.get("depth"), dict)]
    floors = [d["absolute_floor"] for d in depths if isinstance(d.get("absolute_floor"), int)]
    medians = [d["global_median"] for d in depths if isinstance(d.get("global_median"), int)]
    bank_targets = {
        "absolute_floor": min(floors) if floors else result["depth_targets"]["absolute_floor"],
        "global_median": statistics.median(medians) if medians else result["depth_targets"]["global_median"],
        "paragraph_count": sum(int(d.get("paragraph_count", 0)) for d in depths),
        "scope": "technical_chapters",
        "calibrated_from": result["file_hash"],
    }

    reg_path = bank_dir / "registration.json"
    reg = _load_bank_json(reg_path, {"items": []}, require_items_list=True)
    items = [it for it in reg.get("items", []) if isinstance(it, dict) and it.get("slug") != slug]  # M-4: 旧行缺 slug 不丢
    items.append(result["registration_item"])
    items.sort(key=lambda it: str(it.get("slug", "")))  # M-4: 缺 slug 空串排首, 不崩

    # 元数据残留闸门(T7 评审 I-1): 序列化后的 bank_index/registration 全文跑正文同款
    # RESIDUAL_RE + --map 键原文名检查, 命中即 rc=1——此时零落盘(含切片/full.md)。
    meta_text = json.dumps(index, ensure_ascii=False, sort_keys=True) + "\n" + json.dumps({"items": items}, ensure_ascii=False, sort_keys=True)
    meta_hits = metadata_residual_scan(meta_text, mapping)
    if meta_hits:
        print(f"元数据残留扫描 {len(meta_hits)} 处命中——拒绝出库(rc=1, 零落盘): --title 等元数据字段不经正文脱敏, 请改用脱敏后题名或修订对照:", file=sys.stderr)
        for ln in meta_hits:
            print(f"  · {ln}", file=sys.stderr)
        return EXIT_ERROR

    # 两道闸门(正文+元数据)全过后才落盘
    slug_dir = bank_dir / slug
    chapters_dir = slug_dir / "chapters"
    if chapters_dir.is_file():  # M-6: 路径被文件占位(异常残留) → unlink 兜底再建目录
        chapters_dir.unlink()
    if chapters_dir.is_dir():  # 旧切片清场再重写——源文件修订后重编译不留陈旧 chNN
        shutil.rmtree(chapters_dir)
    chapters_dir.mkdir(parents=True, exist_ok=True)
    _write_text(slug_dir / "full.md", result["redacted"] + "\n")
    for fname, ch in chapter_files:
        _write_text(chapters_dir / fname, ch["text"] + "\n")
    _write_json(index_path, index)
    _write_json(bank_dir / "depth_targets.json", bank_targets)
    _write_json(reg_path, {"items": items})

    # 可选 RAGFlow bid_samples 域推送(Task 5 + Plan 4 Task 2 技术章检索域): 推送文本=技术章拼接文
    # (商务章=检索噪声不进语料; 文档名不变——同名先删再传幂等语义自动替换旧全册文档); 技术集为空 →
    # fail-closed 跳过推送**绝不回退推全册**, summary 增 ragflow_skip_reason=no_tech_chapter 且
    # stderr 列出全部章标题(供维护者修词表 TECH_TITLE_RE 或 --map)。位于一切本地产物落盘之后;
    # env 缺失/推送失败由 ragflow_push 内部自检降级为 warnings(main 不预检——M-1, 消除双份警告漂移),
    # rc 恒 EXIT_OK(spec: 本地衍生物已可用, 推送是辅助通道绝不阻塞出库); 未传 --ragflow-push 整段短路。
    summary = {
        "command": "bank_compile",
        "slug": slug,
        "chapters": len(result["chapters"]),
        "paragraphs": result["depth_targets"]["paragraph_count"],
        "absolute_floor": bank_targets["absolute_floor"],
        "global_median": bank_targets["global_median"],
        "residual": len(result["residual"]),
    }
    if args.ragflow_push:
        if result["tech_text"]:
            if ragflow_push(result["tech_text"], {"title": args.title}):
                print(f"RAGFlow 推送成功: {slug}.md", file=sys.stderr)
        else:
            print(
                "警告: 技术章筛选为空——RAGFlow 推送跳过(no_tech_chapter, fail-closed 不回退推全册)。全部章标题如下, 请核对标题词表(TECH_TITLE_RE)或 --map:",
                file=sys.stderr,
            )
            for ch in result["chapters"]:
                print(f"  · {ch['title']}", file=sys.stderr)
            summary["ragflow_skip_reason"] = "no_tech_chapter"

    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
