"""投标审查文档解析层(EAI-CUSTOM 2026-10-30,spec: bid-review evidence pipeline §2/D1/D4/D6/D8)。

上传字节 → 按格式解析为「段落流 segments + 图片资产 assets」:
- docx → python-docx:正文段落/表格(按文档流顺序)+ 内嵌图片枚举(OCR 文本按原位插回);
  docx 无页边界(D8):segment.page 恒 None,定位走 quote 片段窗口。
- pdf → PyMuPDF 逐页:文本层非空页直取(真页码);空文本层页(扫描页)渲染位图 → OCR,
  位图落 assets 备预览(盖章核对)。
- xlsx → openpyxl 每 sheet 一个 table 块(rows 双键,sheet 名注记;对齐审计⑤ 2026-11-05)。
- 独立图片(png/jpg/gif/bmp)→ 整图走 OCR 通路(对齐审计⑦ 2026-11-05)。
- 其他 → UTF-8 文本(v1 既有行为),按 ~2500 字符切段,page=None。

OCR 引擎伴随系统设置(spec §3):default_ocr_engine=builtin → eai-flow-ocr HTTP
(OCR_SERVICE_URL,rapidocr 家族);= 注册表名 → openai-vision 协议(paddleocr-vl 等)。
失效回退内建 + warning;单图 OCR 失败 → 空文本 segment(失败隔离,不炸任务)。

存储(spec §4.1,目录钉死 {base}/users/{owner}/bid_review/{task_id}/):
  raw/{role}__{slug}.bin   上传原始字节(上传请求内快速落盘,重活全在 parsing 阶段)
  docs/{slug}/segments.json  [{"seq","page","kind","text","asset_id"}]
  assets/{asset_id}.{ext}    原图(预览按需取)
engine_meta.docs 只存清单(doc_id/role/kind/pages/chars/assets/status),全文不上 wire(D6)。
"""

import asyncio
import hashlib
import io
import json
import logging
import os
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 内建 eai-flow-ocr 地址(cpa document_parser 同源约定;docker 网络内 hostname 直达)
OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", "http://eai-flow-ocr:8010")
# 扫描 PDF 逐页 OCR 并发上限(500 页扫描件串行会拖 20min+;4 并发已够压)
OCR_CONCURRENCY = 4
_TEXT_SEG_CHARS = 2500
_XLSX_MAX_ROWS = 500  # 每 sheet 行数上限(超大清单防 blocks 膨胀;截断在 text 侧自然呈现)
_ZIP_MAX_FILES = 20  # zip 材料包文件数上限(对齐审计⑥)
_ZIP_MAX_UNCOMPRESSED = 200 * 1024 * 1024  # 解压总量上限,ZipInfo.file_size 解压前预检

_A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
_R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "bmp": "image/bmp", "emf": "image/emf", "wmf": "image/x-wmf"}


def detect_kind(filename: str) -> str:
    lower = (filename or "").lower()
    if lower.endswith(".docx"):
        return "docx"
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith(".zip"):
        return "zip"
    if "." in lower and lower.rsplit(".", 1)[-1] in _MIME:
        return "image"
    return "text"


def _slug(role: str, doc_id: str) -> str:
    """文件系统安全 slug(md5 确定性;doc_id 保留原名给清单/证据 chip 显示)。"""
    return hashlib.md5(f"{role}:{doc_id}".encode()).hexdigest()[:16]


def task_dir(owner_id: str, task_id: str):
    """任务材料目录钉死(spec §4.1):{base}/users/{owner}/bid_review/{task_id}/。
    EAI-CUSTOM(2026-10-30 E2E 勘误):须用 base_dir(进程本地路径)——host_base_dir
    是沙箱卷挂载契约,在 gateway Linux 容器里解析成宿主 Windows 路径 `D:/...`,
    落盘变成字面 `D:` 相对目录;与 docmgr 等 app 层消费方同口径。"""
    from deerflow.config.paths import Paths, make_safe_user_id

    return Paths().base_dir / "users" / make_safe_user_id(owner_id) / "bid_review" / task_id


# ── 上传落盘(routers.create_task 调用;只写磁盘不解析)─────────────────


def save_raw(owner_id: str, task_id: str, role: str, filename: str, data: bytes) -> dict:
    """原始字节落盘 → 清单项(status=raw)。全文不进 DB(D6)。"""
    doc_id = filename or f"{role}-doc"
    d = task_dir(owner_id, task_id) / "raw"
    d.mkdir(parents=True, exist_ok=True)
    slug = _slug(role, doc_id)
    (d / f"{slug}.bin").write_bytes(data)
    return {"doc_id": doc_id, "role": role, "kind": detect_kind(filename), "slug": slug, "size": len(data), "chars": 0, "pages": 0, "assets": 0, "status": "raw"}


# ── OCR 客户端(双引擎,spec §3)───────────────────────────────────────


async def _ocr_builtin(name: str, data: bytes, mime: str) -> str:
    """eai-flow-ocr POST {base}/ocr(multipart)→ pages[*].text 拼接。失败重试 1 次 → ""。
    EAI-CUSTOM(2026-10-30 E2E 勘误,bug-3703):服务 Phase 0 只收 PDF("only .pdf is
    supported"),图片类(docx 内嵌图/PDF 扫描页,parse 层交付的就是图片字节)先以
    fitz 包一层单页 PDF 再投递,复用同一服务契约。"""
    url = OCR_SERVICE_URL.rstrip("/") + "/ocr"
    if not mime.endswith("pdf"):
        import fitz

        buf = io.BytesIO()
        with fitz.open() as doc:
            page = doc.new_page(width=612, height=792)
            page.insert_image(page.rect, stream=data)
            buf.write(doc.tobytes())
        data, mime, name = buf.getvalue(), "application/pdf", f"{name}.pdf"
    last: Exception | None = None
    for _ in range(2):
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(url, files={"file": (name, data, mime)})
                resp.raise_for_status()
                pages = resp.json().get("pages") or []
                return "\n\n".join(str(p.get("text") or "") for p in pages if p.get("text")).strip()
        except Exception as exc:  # noqa: BLE001
            last = exc
    logger.warning("builtin OCR failed for %s: %r", name, last)
    return ""


async def _ocr_openai_vision(entry: dict, name: str, data: bytes, mime: str) -> str:
    """注册表外接(OpenAI 兼容 vision 协议,同 cpa 外接路径)。失败重试 1 次 → ""。"""
    import base64

    b64 = base64.b64encode(data).decode()
    url = entry["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": entry["model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "逐字转写图片中的全部文字(含表格,用 | 分隔单元格),不要解释,不要遗漏。"},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ],
    }
    last: Exception | None = None
    for _ in range(2):
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {entry['api_key']}"})
                resp.raise_for_status()
                return str(resp.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:  # noqa: BLE001
            last = exc
    logger.warning("openai-vision OCR(%s)failed for %s: %r", entry["name"], name, last)
    return ""


async def build_ocr_fn(db: AsyncSession):
    """系统设置 default_ocr_engine → OCR callable (name, bytes, mime) -> str(spec §3)。"""
    from app.extensions.ocr_resolve import resolve_default_ocr_entry

    entry = await resolve_default_ocr_entry(db)
    if entry is None:
        return _ocr_builtin
    logger.info("bid_review parse OCR engine: %s(openai-vision)", entry["name"])

    async def _fn(name: str, data: bytes, mime: str) -> str:
        return await _ocr_openai_vision(entry, name, data, mime)

    return _fn


# ── 解析(parsing 阶段调用)────────────────────────────────────────────


def _write_asset(base: Path, asset_id: str, ext: str, data: bytes) -> None:
    adir = base / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    (adir / f"{asset_id}.{ext}").write_bytes(data)


def _asset_id(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()[:16]


def _parse_docx_sync(data: bytes) -> list[dict]:
    """docx → 流序块(p=段落文本/图,tbl=表格行文本,图只挑出不解析)。

    纯 CPU 段;OCR 在 parse_raw 的 async 段做。返回块:
    {kind: "text"|"table", text} | {kind: "table", text, rows} | {kind: "image", blob, ext}。
    table 块另带 rows 二维数组(对齐审计④,2026-11-05——|a|b| 拍平文本仅供模型通路,
    结构化消费方走 rows;两键并存零互斥)。
    """
    import docx as docx_lib
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx_lib.Document(io.BytesIO(data))
    blocks: list[dict] = []
    for child in document.element.body.iterchildren():
        local = child.tag.rsplit("}", 1)[-1]
        if local == "p":
            for blip in child.findall(f".//{_A_BLIP}"):
                rid = blip.get(_R_EMBED)
                part = document.part.related_parts.get(rid) if rid else None
                if part is None:
                    continue
                blob = part.blob
                ext = str(part.partname).rsplit(".", 1)[-1].lower() if "." in str(part.partname) else "png"
                blocks.append({"kind": "image", "blob": blob, "ext": ext if ext in _MIME else "png"})
            para = Paragraph(child, document)
            text = para.text.strip()
            if text:
                blocks.append({"kind": "text", "text": text})
        elif local == "tbl":
            rows: list[str] = []
            row_cells: list[list[str]] = []
            for row in Table(child, document).rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                rows.append("| " + " | ".join(cells) + " |")
                row_cells.append(cells)
            if rows:
                blocks.append({"kind": "table", "text": "\n".join(rows), "rows": row_cells})
    return blocks


def _parse_pdf_sync(data: bytes) -> tuple[list[dict], dict[int, bytes]]:
    """pdf → 逐页块:文本页 {kind:"text", page, text};扫描页(空文本层)→ 渲染位图
    返回待 OCR(调用方 async 段处理)。返回 (blocks, {page: png_bytes})。"""
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    blocks: list[dict] = []
    scans: dict[int, bytes] = {}
    for page in doc:
        n = page.number + 1
        text = (page.get_text("text") or "").strip()
        if text:
            blocks.append({"kind": "text", "page": n, "text": text})
            continue
        png = page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
        scans[n] = png
        blocks.append({"kind": "scan", "page": n})
    return blocks, scans


def _parse_xlsx_sync(data: bytes) -> list[dict]:
    """xlsx → 每 sheet 一个 table 块(rows 二维数组 + |a|b| 拍平文本,docx 表④同款
    双键;对齐审计⑤ 2026-11-05 新入口)。openpyxl 守卫式导入(缺依赖 → ValueError
    per-file 隔离,不炸任务);data_only=True 取公式计算值,read_only 流式读;
    sheet 名注记进 text 首行(模型与人工都能定位来源页);每 sheet 上限
    _XLSX_MAX_ROWS 行。"""
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as e:  # pragma: no cover - 容器实测 3.1.5 在位
        raise ValueError("xlsx 解析需 openpyxl(缺依赖按单文件失败隔离)") from e

    blocks: list[dict] = []
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        for ws in wb.worksheets:
            rows: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                rows.append(["" if c is None else str(c).strip().replace("\n", " ") for c in row])
                if len(rows) >= _XLSX_MAX_ROWS:
                    break
            if not rows:
                continue
            text = "\n".join("| " + " | ".join(cells) + " |" for cells in rows)
            blocks.append({"kind": "table", "text": f"[sheet: {ws.title}]\n{text}", "rows": rows})
    finally:
        wb.close()
    return blocks


def _blocks_for_bytes(filename: str, data: bytes) -> list[dict]:
    """单成员字节 → 块(按扩展名分派;zip 成员与独立上传共用,对齐审计⑥ 2026-11-05)。
    zip 内 PDF 扫描页转诚实占位段(跨成员页号冲突+定位契约按单文档页码,OCR 挂账);
    嵌套 zip 显式拒绝(否则二进制走文本通路产 mojibake)。"""
    kind = detect_kind(filename)
    if kind == "docx":
        return _parse_docx_sync(data)
    if kind == "pdf":
        blocks, scans = _parse_pdf_sync(data)
        if scans:
            blocks = [{"kind": "text", "text": f"[第 {b['page']} 页为扫描页:zip 内 PDF 暂不支持扫描页 OCR,请单独上传该 PDF]"} if b["kind"] == "scan" else b for b in blocks]
        return blocks
    if kind == "xlsx":
        return _parse_xlsx_sync(data)
    if kind == "zip":
        raise ValueError(f"嵌套 zip 不支持: {filename}")
    if kind == "image":
        ext = filename.rsplit(".", 1)[-1].lower()
        return [{"kind": "image", "blob": data, "ext": ext if ext in _MIME else "png"}]
    return _parse_text_sync(data)


def _unzip_blocks(data: bytes) -> list[dict]:
    """zip 材料包安全解包(对齐审计⑥,2026-11-05):文件数 ≤_ZIP_MAX_FILES;解压总量
    ≤_ZIP_MAX_UNCOMPRESSED(ZipInfo.file_size 解压前预检,不落盘不炸内存);成员名
    拒绝对路径与 ..(zip-slip)。逐成员 _blocks_for_bytes 分派,块附 source=成员名
    (seg 透传,证据定位可见来源文件)。违规 → ValueError per-file 隔离。"""
    import zipfile

    out: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = [i for i in zf.infolist() if not i.is_dir()]
        if len(members) > _ZIP_MAX_FILES:
            raise ValueError(f"zip 内文件数 {len(members)} 超上限 {_ZIP_MAX_FILES}")
        total = sum(i.file_size for i in members)
        if total > _ZIP_MAX_UNCOMPRESSED:
            raise ValueError(f"zip 解压总量 {total} 字节超上限 {_ZIP_MAX_UNCOMPRESSED}")
        for info in members:
            name = info.filename
            parts = name.replace("\\", "/").split("/")
            if name.startswith("/") or ".." in parts:
                raise ValueError(f"zip 内不安全路径: {name}")
            for b in _blocks_for_bytes(name, zf.read(info)):
                out.append({**b, "source": name})
    return out


def _parse_text_sync(data: bytes) -> list[dict]:
    """UTF-8 文本(v1 既有行为)→ ~2500 字符段(换行边界断),page=None。"""
    text = data.decode("utf-8", "replace")
    blocks: list[dict] = []
    buf: list[str] = []
    size = 0
    for line in text.splitlines():
        buf.append(line)
        size += len(line) + 1
        if size >= _TEXT_SEG_CHARS:
            blocks.append({"kind": "text", "text": "\n".join(buf)})
            buf, size = [], 0
    if buf:
        blocks.append({"kind": "text", "text": "\n".join(buf)})
    return blocks


def derive_parse_confidence(segs: list[dict]) -> dict:
    """B3 解析置信(EAI-CUSTOM 2026-11-01,spec §5):文档级 confidence = 无损解析
    字符占比——text/table 段为解析器直取(无损),ocr 段为图片转写(拉低占比)。
    这是可解释的派生口径,非 OCR 引擎自报分数(builtin/openai-vision 两通道均不
    回传分数,不伪造页级数字);low_conf_pages = OCR 空文本页段(识别失败,置信按
    0 记,连续页合并区间);docx 内嵌图无页边界,失败张数走 parse_note。"""
    lossless = sum(len(s.get("text") or "") for s in segs if s.get("kind") in ("text", "table"))
    ocr = sum(len(s.get("text") or "") for s in segs if s.get("kind") == "ocr")
    total = lossless + ocr
    confidence = round(lossless / total, 2) if total > 0 else (0.0 if segs else None)

    low_pages: list[dict] = []
    failed_imgs = 0
    run: tuple[int, int] | None = None  # (page_from, page_to) 连续空 OCR 页
    for s in segs:
        page = s.get("page")
        if s.get("kind") == "ocr" and not (s.get("text") or "").strip():
            if page is None:
                failed_imgs += 1
            else:
                run = (run[0], page) if run else (page, page)
            continue
        if run:
            low_pages.append({"page_from": run[0], "page_to": run[1], "confidence": 0.0, "note": "OCR 未产出文本"})
            run = None
    if run:
        low_pages.append({"page_from": run[0], "page_to": run[1], "confidence": 0.0, "note": "OCR 未产出文本"})

    return {
        "confidence": confidence,
        "low_conf_pages": low_pages,
        "parse_note": f"{failed_imgs} 张内嵌图片 OCR 未产出文本" if failed_imgs else None,
    }


async def parse_raw(owner_id: str, task_id: str, entry: dict, ocr_fn) -> dict:
    """raw → segments.json + assets,返回更新后的清单项。CPU 段 to_thread 卸载,
    OCR 段按 OCR_CONCURRENCY 有界并发(扫描大 PDF 场景)。单图失败 → 空文本
    segment 保留占位(定位弹层显「未定位到原文」),失败隔离不炸任务。"""
    base = task_dir(owner_id, task_id)
    raw_path = base / "raw" / f"{entry['slug']}.bin"
    data = raw_path.read_bytes()
    kind = entry.get("kind") or "text"

    if kind == "docx":
        blocks = await asyncio.to_thread(_parse_docx_sync, data)
        scans: dict[int, bytes] = {}
    elif kind == "pdf":
        blocks, scans = await asyncio.to_thread(_parse_pdf_sync, data)
    elif kind == "xlsx":  # 对齐审计⑤(2026-11-05)
        blocks, scans = await asyncio.to_thread(_parse_xlsx_sync, data), {}
    elif kind == "zip":  # 对齐审计⑥(2026-11-05):材料包解包逐成员解析
        blocks, scans = await asyncio.to_thread(_unzip_blocks, data), {}
    elif kind == "image":  # 对齐审计⑦(2026-11-05):独立图片直传,走既有 ocr_fn 通路
        ext = str(entry.get("doc_id") or "").rsplit(".", 1)[-1].lower()
        blocks, scans = [{"kind": "image", "blob": data, "ext": ext if ext in _MIME else "png"}], {}
    else:
        blocks, scans = await asyncio.to_thread(_parse_text_sync, data), {}

    segs: list[dict] = []
    assets: list[dict] = []
    seq = 0
    # OCR 并发清理:先把带图块定案为 (idx, name, blob, mime) 任务表,有界并发跑,原序回填
    prepared: list[dict] = []
    jobs: dict[int, tuple[str, bytes, str]] = {}
    for b in blocks:
        if b["kind"] == "image":
            aid = _asset_id(b["blob"])
            _write_asset(base, aid, b["ext"], b["blob"])
            assets.append({"asset_id": aid, "ext": b["ext"]})
            prepared.append({**b, "asset_id": aid})
            jobs[len(prepared) - 1] = (f"asset-{aid}.{b['ext']}", b["blob"], _MIME.get(b["ext"], "image/png"))
        elif b["kind"] == "scan":
            png = scans[b["page"]]
            aid = _asset_id(png)
            _write_asset(base, aid, "png", png)
            assets.append({"asset_id": aid, "ext": "png"})
            prepared.append({**b, "asset_id": aid})
            jobs[len(prepared) - 1] = (f"page-{b['page']}.png", png, "image/png")
        else:
            prepared.append(b)

    sem = asyncio.Semaphore(OCR_CONCURRENCY)

    async def _run(name: str, blob: bytes, mime: str) -> str:
        async with sem:
            return await ocr_fn(name, blob, mime)

    ocr_by_idx = dict(zip(jobs.keys(), await asyncio.gather(*(_run(n, b, m) for n, b, m in jobs.values())))) if jobs else {}

    for i, b in enumerate(prepared):
        if b["kind"] == "text":
            seg = {"seq": seq, "page": b.get("page"), "kind": "text", "text": b["text"], "source": b.get("source"), "asset_id": None}
        elif b["kind"] == "table":
            seg = {"seq": seq, "page": None, "kind": "table", "text": b["text"], "rows": b.get("rows"), "source": b.get("source"), "asset_id": None}
        else:  # image | scan
            seg = {"seq": seq, "page": b.get("page"), "kind": "ocr", "text": (ocr_by_idx.get(i) or "").strip(), "asset_id": b["asset_id"]}
        segs.append(seg)
        seq += 1

    ddir = base / "docs" / entry["slug"]
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / "segments.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    chars = sum(len(s["text"]) for s in segs)
    pages = len({s["page"] for s in segs if s["page"] is not None})
    # B3:解析置信派生键(confidence/low_conf_pages/parse_note)随清单项进 engine_meta.docs
    return {**entry, "chars": chars, "pages": pages, "assets": len(assets), "status": "parsed", **derive_parse_confidence(segs)}


# ── 取数(worker._load_docs / routers 取数端点消费)───────────────────


def load_segments(owner_id: str, task_id: str, slug: str) -> list[dict]:
    p = task_dir(owner_id, task_id) / "docs" / slug / "segments.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def docs_from_entries(owner_id: str, task_id: str, entries: list[dict], shard_chars: int = 30_000) -> list[dict]:
    """清单 → worker._load_docs 形态 [{doc_id, role, text}](全文由 segments 拼回;
    只在此内存形态短暂聚合,不落 wire)。未解析(raw)条目跳过。

    EAI-CUSTOM(2026-10-30 抽取 v2,spec D5/D7):带页 segment 前插 [[p.N]] 标记
    (模型 provenance.page 锚点,docx 无页不插——D8 诚实降级);单文档超 shard_chars
    按 segment 边界切成同 doc_id 多片段(extract 层贪心装箱成分片 prompt,几百页
    大文档不进单 prompt,provenance.doc_id 仍为真名)。"""
    out: list[dict] = []
    for e in entries:
        if not isinstance(e, dict) or e.get("status") != "parsed":
            continue
        doc_id = str(e.get("doc_id") or "doc")
        role = str(e.get("role") or "unknown")
        buf: list[str] = []
        size = 0
        for s in load_segments(owner_id, task_id, str(e.get("slug") or "")):
            text = str(s.get("text") or "")
            if not text:
                continue
            page = s.get("page")
            if page is not None:
                text = f"[[p.{page}]]\n{text}"
            if buf and size + len(text) > shard_chars:
                out.append({"doc_id": doc_id, "role": role, "text": "\n".join(buf)})
                buf, size = [], 0
            buf.append(text)
            size += len(text)
        if buf:
            out.append({"doc_id": doc_id, "role": role, "text": "\n".join(buf)})
    return out


def excerpt_window(segs: list[dict], hit_seq: int, before: int = 10, after: int = 10) -> list[dict]:
    """docx/text 定位窗口(D8):命中 segment ±N 条。"""
    lo = max(0, hit_seq - before)
    hi = min(len(segs), hit_seq + after + 1)
    return segs[lo:hi]
