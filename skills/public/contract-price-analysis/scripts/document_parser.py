"""Parse a contract file via the eai-flow-ocr HTTP service -> TableExtract list.

The heavy OCR (rapid-layout + rapid-table + rapidocr) lives in the standalone
eai-flow-ocr container; this module just POSTs the file and reshapes the JSON
into TableExtract per detected table. Downstream (table_classifier +
price_validator, called from cli.run_pipeline) decides which tables are
goods/price tables and validates the numbers.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# ponytail: retry transient OCR worker crashes (RemoteProtocolError) up to 2
# times with backoff — scanned PDFs can OOM a worker on first pass but a lone
# retry against a fresh worker usually succeeds. 3 total attempts, 30s/60s
# backoff, enough headroom without blowing the per-doc timeout.
_RETRY_MAX = 3
_RETRY_BACKOFF = [30, 60]


@dataclass
class TableExtract:
    page_no: int
    table_idx: int
    bbox: list               # page-relative [x1,y1,x2,y2] normalized 0~1
    rows: list               # list of rows; each row = list of cell text
    cell_bboxes: list        # parallel to rows: rows of cell bbox (0~1 vs page)
    page_preview_b64: str
    mean_confidence: float = 0.0
    extra: dict = field(default_factory=dict)
    tokens: list = field(default_factory=list)  # 行级 OCR token(页归一化0~1,与 cell_bboxes 同规格;P1 几何层)


def _norm_tokens(raw_tokens, page_w, page_h) -> list:
    """OCR 服务 tokens(页绝对像素) → 页归一化 0~1(与 cell_bboxes 同规格;
    P1 几何层缓存 v2)。旧服务无 tokens / 缺页宽高 → 空列表(几何层自然放弃)。"""
    if not raw_tokens or not (page_w and page_h):
        return []
    out = []
    for tok in raw_tokens:
        b = (tok or {}).get("box") or []
        if len(b) < 4:
            continue
        out.append(
            {
                "text": str((tok or {}).get("text", "")),
                "box": [
                    float(b[0]) / page_w,
                    float(b[1]) / page_h,
                    float(b[2]) / page_w,
                    float(b[3]) / page_h,
                ],
                "score": float((tok or {}).get("score", 0.0)),
            }
        )
    return out


async def parse_document(
    file_bytes: bytes,
    filename: str,
    ocr_service_url: str,
    last_pages: int = 0,
    backend: str = "builtin",
    openai_cfg: dict | None = None,
) -> tuple:
    """Call the OCR frontend, return (list[TableExtract], page_texts, orientation_fixed).

    M3 (spec §3.4): backend 分派——
      - "builtin"(缺省): httpx 调 eai-flow-ocr,路径与引入前逐字节一致;
      - "openai-vision": pymupdf 光栅化 → OpenAI 兼容 vision chat → HTML 表格
        → 同一 TableExtract 契约(cell bbox=None,页码保留,溯源 UI 降级为仅页图)。
    openai_cfg = {base_url, api_key, model}(provider 名只用于缓存分键/审计,由 cli 处理)。

    page_texts is {page_no: full_page_text} (builtin 仅前几页;openai-vision 取
    PDF 原生文本层,扫描件通常为空)。orientation_fixed 仅 builtin 产生。

    last_pages > 0 时仅 OCR 末 N 页。

    Large PDFs take minutes (per-page layout+table+ocr), so the timeout is long.
    """
    if backend == "openai-vision":
        cfg = openai_cfg or {}
        return await parse_document_openai_vision(
            file_bytes,
            filename,
            base_url=str(cfg.get("base_url") or ""),
            api_key=str(cfg.get("api_key") or ""),
            model=str(cfg.get("model") or ""),
            last_pages=last_pages,
        )
    url = ocr_service_url.rstrip("/") + "/ocr"
    # 137-page scanned contracts take ~14-16 min of OCR; 900s was too tight
    # (cold-start after a rebuild pushed one run to 15.6min → ReadTimeout with
    # an empty message that looked like a silent failure). 1800s gives margin.
    last_exc: Exception | None = None
    for attempt in range(1, _RETRY_MAX + 1):
        try:
            async with httpx.AsyncClient(timeout=1800.0) as client:
                resp = await client.post(
                    url,
                    files={"file": (filename, file_bytes, "application/octet-stream")},
                    data={"last_pages": last_pages} if last_pages else None,
                )
                resp.raise_for_status()
                data = resp.json()
            break  # success — exit retry loop
        except httpx.RemoteProtocolError as exc:
            last_exc = exc
            if attempt < _RETRY_MAX:
                wait = _RETRY_BACKOFF[attempt - 1] if attempt - 1 < len(_RETRY_BACKOFF) else 60
                logger.warning(
                    "OCR server disconnected (attempt %d/%d), retrying in %ds: %s",
                    attempt, _RETRY_MAX, wait, exc,
                )
                await asyncio.sleep(wait)
            else:
                raise

    tables: list[TableExtract] = []
    page_texts: dict[int, str] = {}
    orientation_fixed: list[int] = list(data.get("orientation_fixed_pages", []) or [])
    for page in data.get("pages", []):
        preview = page.get("preview_png_b64", "")
        page_no = page.get("page_no", 0)
        ptext = page.get("text", "") or ""
        if ptext:
            page_texts[page_no] = ptext
        for ti, t in enumerate(page.get("tables", [])):
            raw_rows = t.get("rows", []) or []
            rows_text = [
                [(c.get("text", "") if isinstance(c, dict) else str(c)) for c in row]
                for row in raw_rows
            ]
            rows_bbox = [
                [
                    (c.get("bbox", [0, 0, 0, 0]) if isinstance(c, dict) else [0, 0, 0, 0])
                    for c in row
                ]
                for row in raw_rows
            ]
            tokens = _norm_tokens(t.get("tokens"), page.get("page_width"), page.get("page_height"))
            tables.append(
                TableExtract(
                    page_no=page_no,
                    table_idx=ti,
                    bbox=t.get("bbox", [0, 0, 0, 0]),
                    rows=rows_text,
                    cell_bboxes=rows_bbox,
                    page_preview_b64=preview,
                    mean_confidence=float(t.get("mean_confidence", 0.0)),
                    tokens=tokens,
                )
            )
    return tables, page_texts, orientation_fixed


def to_cache(tables: list[TableExtract], page_texts: dict[int, str], orientation_fixed=()) -> dict:
    """OCR 结构化结果的缓存形态(剔 preview b64——预览 PNG 本就单独存 MinIO)。"""
    return {
        "v": 1,
        "page_texts": {str(k): v for k, v in page_texts.items()},
        "orientation_fixed_pages": list(orientation_fixed),
        "tables": [
            {
                "page_no": t.page_no,
                "table_idx": t.table_idx,
                "bbox": t.bbox,
                "rows": t.rows,
                "cell_bboxes": t.cell_bboxes,
                "mean_confidence": t.mean_confidence,
                "tokens": list(getattr(t, "tokens", None) or []),
            }
            for t in tables
        ],
    }


# ── M3 openai-vision 前端(spec §3.4)──────────────────────────────────────

# PaddleOCR-VL 系按元素级固定指令训练:表格识别的触发指令就是 "Table Recognition:"
# (实测:中文自然语言/"OCR:" 会退化成纯文本平铺甚至死循环撑满 max_tokens)。
_VISION_PROMPT = "Table Recognition:"

# 模型原生输出为标记流(非 HTML):<fcel>text=有值格、<lcel>=与左格合并、
# <ucel>=与上格合并、<ecel>=空格、<nl>=行尾。官方 paddleocr 客户端内置
# 标记流→HTML 转换;直调 API 时由 parse_table_marker_stream 在本地重建行。
_TABLE_MARKERS = ("<fcel>", "<lcel>", "<ecel>", "<ucel>")


# ── EAI-CUSTOM 2026-10-29 BUG-D: LaTeX 数学转义 → Unicode 归一化 ──────────
# 生产实证(木饰面/钢筋补充协议): PaddleOCR-VL 是 VLM,把单元格里的孤立符号
# (Φ/×/±…)按数学公式序列化成 LaTeX(\Phi/\times),有时还裹行内定界符 \( \);
# 相邻页输出形态不稳定(\Phi vs \(\Phi\)),temperature=0 压不住解码非确定性。
# 实测换 "OCR:" prompt 保符号丢表格结构(0 张表,分项提取全军覆没;见
# _VISION_PROMPT 注释)——必须保留 "Table Recognition:" 保结构,下游归一化。
# 设计红线(生产 38 项回归固化):
#   1) 命令替换自带词界语义:未知命令(\foo)与 \Philips 类前缀词原样保留,
#      宁可不清理也不破坏文本;
#   2) 绝不碰裸 $ ——合同里 $ 多为货币金额;只去 \$ 的反斜杠、保留 $ 本体;
#   3) 末步只压 [ \t] 横向空白,不动 \n(page_texts 靠换行切行喂元数据正则);
#   4) 幂等:已归一/纯文本输入逐字节不变,可安全重复挂载(活体+缓存路径)。
_LATEX_TEXT_WRAP = re.compile(r"\\text\s*\{([^{}]*)\}")
_LATEX_MATH_DELIM = re.compile(r"\\[\(\)\[\]]")
_LATEX_ESC_DOLLAR = re.compile(r"\\\$")
# 命令名或单个版式空白命令(\<space> \, \; \: \!)。负向断言防 \Philips 误换。
_LATEX_CMD = re.compile(r"\\([A-Za-z]+|[ ,;:!])(?![A-Za-z])")
_LATEX_SUP_RE = re.compile(r"\^\{([^{}]{1,3})\}")
_LATEX_SUP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "n": "ⁿ", "i": "ⁱ",
    "°": "°",  # ^{\circ} 已被命令步转成 ^{°},此处剥壳留符号
}
_LATEX_SYMBOLS = {
    # 希腊字母(小写 + VLM 常用变体)
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "omicron": "ο", "pi": "π", "rho": "ρ", "sigma": "σ",
    "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω",
    # 希腊字母(大写;生产实测直接相关的 Phi/Omega 在内)
    "Alpha": "Α", "Beta": "Β", "Gamma": "Γ", "Delta": "Δ", "Epsilon": "Ε",
    "Zeta": "Ζ", "Eta": "Η", "Theta": "Θ", "Iota": "Ι", "Kappa": "Κ",
    "Lambda": "Λ", "Mu": "Μ", "Nu": "Ν", "Xi": "Ξ", "Omicron": "Ο",
    "Pi": "Π", "Rho": "Ρ", "Sigma": "Σ", "Tau": "Τ", "Upsilon": "Υ",
    "Phi": "Φ", "Chi": "Χ", "Psi": "Ψ", "Omega": "Ω",
    # 运算符/关系符
    "times": "×", "div": "÷", "pm": "±", "mp": "∓", "cdot": "·",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "equiv": "≡", "approx": "≈", "sim": "∼", "propto": "∝",
    "infty": "∞", "degree": "°", "circ": "°", "prime": "′",
    "ldots": "…", "cdots": "⋯", "percent": "%", "permille": "‰",
    # 版式空白
    "quad": " ", "qquad": "  ", "thinspace": " ", "thin": " ",
    " ": " ", ",": " ", ";": " ", ":": " ", "!": "",
}


def normalize_latex_math(text: str) -> str:
    """LaTeX 数学转义 → Unicode 归一化(BUG-D,2026-10-29 生产实证)。

    只处理含反斜杠的输入(纯文本零成本短路);幂等;六步清洗见上方红线注释。
    挂载:parse_document_openai_vision 两分支汇合处逐 cell(活体解析)+
    from_cache 重建 rows(旧 OCR 缓存仍带脏值,否则缓存命中重解析会冲掉
    数据库回填成果)。"""
    if not text or "\\" not in text:
        return text
    out = str(text)
    for _ in range(3):
        out = _LATEX_TEXT_WRAP.sub(r"\1", out)  # 1) \text{...} → 内部文本
    out = _LATEX_MATH_DELIM.sub("", out)  # 2) \( \) \[ \] 定界符 → 删
    out = _LATEX_ESC_DOLLAR.sub("$", out)  #    \$ 只去转义符,保留 $
    # 3) 命令 → Unicode;未知命令原样保留
    out = _LATEX_CMD.sub(lambda m: _LATEX_SYMBOLS.get(m.group(1), m.group(0)), out)
    # 4) ^{2} → ²(未映射内容原样保留)
    out = _LATEX_SUP_RE.sub(lambda m: _LATEX_SUP.get(m.group(1), m.group(0)), out)
    out = out.replace("\\\\", " ")  # 5) 残余 LaTeX 换行 \\ → 空格
    return re.sub(r"[ \t]{2,}", " ", out).strip()  # 6) 压横向空白(不动 \n)


def parse_table_marker_stream(content: str) -> list[list[list[str]]]:
    """PaddleOCR-VL 标记流 → list[tables[rows[cells]]](整个响应当一张表)。

    网格语义:每个标记占一个格;<lcel>/<ucel> 为合并占位,文本只保留在
    首格(与官方 HTML 转换的 colspan/rowspan 展开等价的行表示)。
    无任何标记 → [](输出不是标记流,由调用方回退 HTML 分支)。"""
    if not content or not any(m in content for m in _TABLE_MARKERS):
        return []
    rows: list[list[str]] = []
    for line in content.split("<nl>"):
        cells: list[str] = []
        pending: list[str] | None = None  # <fcel> 后正在收集的文本
        for part in re.split(r"(<fcel>|<lcel>|<ecel>|<ucel>)", line):
            if part in _TABLE_MARKERS:
                if pending is not None:
                    cells.append("".join(pending).strip())
                    pending = None
                if part == "<fcel>":
                    pending = []
                else:  # lcel/ucel/ecel = 合并/空占位格
                    cells.append("")
            elif pending is not None:
                pending.append(part)
        if pending is not None:
            cells.append("".join(pending).strip())
        if cells:
            rows.append(cells)
    return [rows] if rows else []


def html_tables_to_rows(html: str) -> list[list[list[str]]]:
    """HTML 表格 → list[rows[list[cell text]]](stdlib HTMLParser,容错)。
    供会遵循 HTML 输出指令的 vision 服务回退用(PaddleOCR-VL 系走标记流)。"""
    from html.parser import HTMLParser

    class _T(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.tables: list[list[list[str]]] = []
            self._table_depth = 0
            self._rows: list[list[str]] = []
            self._row: list[str] | None = None
            self._cell: list[str] | None = None

        def handle_starttag(self, tag, attrs):
            if tag == "table":
                self._table_depth += 1
            elif self._table_depth and tag == "tr":
                self._row = []
            elif self._table_depth and tag in ("td", "th"):
                self._cell = []

        def handle_endtag(self, tag):
            if tag == "table":
                if self._table_depth:
                    self._table_depth -= 1
                    # 提交本级收集的行(嵌套表按深度分隔,内层先入 tables)
                    if self._rows:
                        self.tables.append(self._rows)
                    self._rows = []
                    self._row = None
            elif tag == "tr" and self._row is not None:
                self._rows.append(self._row)
                self._row = None
            elif tag in ("td", "th") and self._cell is not None:
                if self._row is None:
                    self._row = []
                self._row.append("".join(self._cell).strip())
                self._cell = None

        def handle_data(self, data):
            if self._cell is not None:
                self._cell.append(data)

    p = _T()
    p.feed(html or "")
    return [rows for rows in p.tables if rows]


async def parse_document_openai_vision(
    file_bytes: bytes,
    filename: str,
    base_url: str,
    api_key: str = "",
    model: str = "",
    last_pages: int = 0,
) -> tuple:
    """pymupdf 光栅化每页 PNG → OpenAI 兼容 vision chat(completions,指令
    "Table Recognition:")→ 标记流/HTML → 同一 TableExtract 契约。
    cell bbox=None → cell_bboxes/tokens 恒空、bbox 取零框,溯源 UI 现成降级
    (``hasBox = !!bbox && bbox.length === 4``)。
    page_texts 取 PDF 原生文本层(扫描件为空,项目字段正则自然跳过)。"""
    import base64

    import fitz  # pymupdf

    base = (base_url or "").strip().rstrip("/")
    if not base or not (model or "").strip():
        raise ValueError("openai-vision OCR requires base_url and model")
    headers = {"Content-Type": "application/json"}
    if (api_key or "").strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    pdf = fitz.open(stream=file_bytes, filetype="pdf")
    pages: list[tuple[int, str, str]] = []
    start = max(0, pdf.page_count - last_pages) if last_pages else 0
    for pno in range(start, pdf.page_count):
        pix = pdf[pno].get_pixmap(dpi=150)
        png = base64.b64encode(pix.tobytes("png")).decode()
        pages.append((pno + 1, png, pdf[pno].get_text() or ""))
    pdf.close()

    tables: list[TableExtract] = []
    page_texts: dict[int, str] = {}
    # 页级瞬时故障重试(对齐 builtin 的 _RETRY 习语): LAN 服务 ConnectError/
    # RemoteProtocolError/ReadTimeout 常见(服务重启/端口代理抖动),一次即败
    # 整文档 failed 代价过高——每页最多 3 次(5/15s backoff),重试期间挂起即可恢复。
    _VISION_RETRY_MAX = 3
    _VISION_RETRY_BACKOFF = [5, 15]
    async with httpx.AsyncClient(timeout=600.0) as client:
        for page_no, png_b64, ptext in pages:
            if ptext:
                page_texts[page_no] = ptext
            resp = None
            for attempt in range(1, _VISION_RETRY_MAX + 1):
                try:
                    resp = await client.post(
                        f"{base}/chat/completions",
                        headers=headers,
                        json={
                            "model": model,
                            "max_tokens": 8000,
                            "temperature": 0,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "image_url",
                                            "image_url": {"url": f"data:image/png;base64,{png_b64}"},
                                        },
                                        {"type": "text", "text": _VISION_PROMPT},
                                    ],
                                }
                            ],
                        },
                    )
                    resp.raise_for_status()
                    break
                except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadTimeout) as exc:
                    if attempt < _VISION_RETRY_MAX:
                        wait = _VISION_RETRY_BACKOFF[min(attempt - 1, len(_VISION_RETRY_BACKOFF) - 1)]
                        logger.warning(
                            "vision call p%s attempt %d/%d failed (%s), retrying in %ss",
                            page_no, attempt, _VISION_RETRY_MAX, exc, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        raise
            content = ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            # PaddleOCR-VL 系输出标记流;会遵循 HTML 指令的服务输出 <table>——两者都转行。
            if any(m in content for m in _TABLE_MARKERS):
                page_tables = parse_table_marker_stream(content)
            else:
                page_tables = html_tables_to_rows(content)
            # EAI-CUSTOM 2026-10-29 BUG-D: 逐 cell 归一化后再进 TableExtract 与
            # page_texts 重建(下方 page_text_lines 从同一批 cell 拼行,两条下游
            # 同时覆盖);幂等,干净值逐字节不变。
            page_tables = [
                [[normalize_latex_math(c) for c in row] for row in tbl]
                for tbl in page_tables
            ]
            # M3 实测(钢材采购 签字版): 封面元数据(日期:/甲方:/合同编号:)只在
            # 文字行里——页内全部格文本(含纯文字行的单格行)拼回 page_texts,
            # 元数据正则才能扫全本(扫描件原生文本层为空,否则 page_texts 恒缺)。
            page_text_lines = [
                cell for table in page_tables for row in table for cell in row if cell
            ]
            row_text = "\n".join(page_text_lines)
            if ptext:
                page_texts[page_no] = ptext
            elif row_text:
                page_texts[page_no] = row_text
            for ti, rows in enumerate(page_tables):
                tables.append(
                    TableExtract(
                        page_no=page_no,
                        table_idx=ti,
                        bbox=[0, 0, 0, 0],
                        rows=rows,
                        cell_bboxes=[[list(0 for _ in range(4)) for _ in row] for row in rows],
                        page_preview_b64=png_b64,
                        mean_confidence=0.0,
                        tokens=[],
                    )
                )
    return tables, page_texts, []


def from_cache(data: dict) -> tuple:
    """缓存 → (tables, page_texts, orientation_fixed)。preview 恒为空串(缓存命中
    重解析时预览 PNG 在首解析已落 MinIO,preview_prefix 不变)。旧缓存无
    orientation_fixed_pages 键 → 空列表(与无纠偏等价)。"""
    tables = [
        TableExtract(
            page_no=t["page_no"],
            table_idx=t["table_idx"],
            bbox=t.get("bbox", [0, 0, 0, 0]),
            # EAI-CUSTOM 2026-10-29 BUG-D: 修复前的旧 OCR 缓存 rows 仍带 LaTeX
            # 转义(\Phi/\times)——缓存命中重解析会原样带回已回填库的脏值,
            # 冲掉数据回填成果;重建时同步归一化(幂等,干净缓存零影响)。
            rows=[[normalize_latex_math(c) for c in row] for row in t.get("rows", [])],
            cell_bboxes=t.get("cell_bboxes", []),
            page_preview_b64="",
            mean_confidence=float(t.get("mean_confidence", 0.0)),
            tokens=t.get("tokens", []) or [],
        )
        for t in data.get("tables", [])
    ]
    page_texts = {int(k): v for k, v in (data.get("page_texts") or {}).items()}
    # M3 实测(钢材采购 签字版): marker 流旧缓存不存 page_texts(文字全在 rows
    # 里,扫描件原生文本层又为空)——从行文本重建,元数据正则(合同编号/日期/
    # 甲方…)才能扫全本;已存 page_texts 的页(原生文本层)不覆盖。
    for t in tables:
        if page_texts.get(t.page_no):
            continue
        txt = "\n".join(c for row in t.rows for c in row if c)
        if txt:
            page_texts[t.page_no] = txt
    return tables, page_texts, list(data.get("orientation_fixed_pages", []) or [])


if __name__ == "__main__":  # ponytail self-check: BUG-D 生产 38 项回归的固化子集
    dirty_cases = [
        # 生产真实脏值(钢筋补充协议 p2/p3、木饰面合同货物清单)
        ("HRB400E \\Phi 8mm", "HRB400E Φ 8mm"),
        ("HRB400E \\(\\Phi\\) 20mm", "HRB400E Φ 20mm"),
        ("强电线槽 \\(100 \\times 100 \\times 1.2\\)", "强电线槽 100 × 100 × 1.2"),
        ("HPB300 \\Phi 6mm", "HPB300 Φ 6mm"),
        ("抗拉强度 \\geq 400MPa", "抗拉强度 ≥ 400MPa"),
        ("偏差 \\pm 0.5mm", "偏差 ± 0.5mm"),
        ("\\Omega 50\\Omega", "Ω 50Ω"),
        # 上标步: ^{\circ} 先经命令步转 ^{°} 再剥壳(注意: 无反斜杠输入在入口
        # 短路返回——与生产版一致,纯 ^{2} 不转换,实际脏 cell 都含 \Phi/\times)
        ("\\Phi 25m^{2}", "Φ 25m²"),
        ("角度 45^{\\circ}", "角度 45°"),
    ]
    for src, want in dirty_cases:
        got = normalize_latex_math(src)
        assert got == want, f"{src!r} → {got!r}, want {want!r}"

    for src in [
        "ZCB-HZZX2ZS-0201-2026-0210",
        "1,234,567.89",
        "2026年9月10日",
        "HRB400E Φ 8mm",  # 已归一形态
        "强电线槽 100 × 100 × 1.2",
        "(常规括号)文本",
        "$500",  # 裸 $ 不碰
        "纯中文无符号",
    ]:
        got = normalize_latex_math(src)
        assert got == src, f"no-op 违约: {src!r} → {got!r}"

    # 边界红线
    assert normalize_latex_math("\\Philips 电动工具") == "\\Philips 电动工具"  # 前缀词不误换
    assert normalize_latex_math("\\$500") == "$500"  # 只去转义符,$ 本体保留
    assert normalize_latex_math("\\foo 12") == "\\foo 12"  # 未知命令保留
    got = normalize_latex_math("a\\times b\nc  d")
    assert got == "a× b\nc d", got  # 命令换+横向压; \n 不被压(page_texts 切行依赖)
    # 幂等
    for src, _ in dirty_cases:
        once = normalize_latex_math(src)
        assert normalize_latex_math(once) == once, src
    # from_cache: 旧缓存 rows 重建时归一化,page_texts 拼行同步干净
    tables, page_texts, _ = from_cache({
        "tables": [{"page_no": 2, "table_idx": 0, "rows": [["HPB300 \\Phi 6mm", "100 \\times 100"]]}],
    })
    assert tables[0].rows == [["HPB300 Φ 6mm", "100 × 100"]], tables[0].rows
    assert page_texts[2] == "HPB300 Φ 6mm\n100 × 100", page_texts.get(2)
    print("ok")
