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
    async with httpx.AsyncClient(timeout=600.0) as client:
        for page_no, png_b64, ptext in pages:
            if ptext:
                page_texts[page_no] = ptext
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
            content = ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            # PaddleOCR-VL 系输出标记流;会遵循 HTML 指令的服务输出 <table>——两者都转行。
            if any(m in content for m in _TABLE_MARKERS):
                page_rows = parse_table_marker_stream(content)
            else:
                page_rows = html_tables_to_rows(content)
            for ti, rows in enumerate(page_rows):
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
            rows=t.get("rows", []),
            cell_bboxes=t.get("cell_bboxes", []),
            page_preview_b64="",
            mean_confidence=float(t.get("mean_confidence", 0.0)),
            tokens=t.get("tokens", []) or [],
        )
        for t in data.get("tables", [])
    ]
    page_texts = {int(k): v for k, v in (data.get("page_texts") or {}).items()}
    return tables, page_texts, list(data.get("orientation_fixed_pages", []) or [])
