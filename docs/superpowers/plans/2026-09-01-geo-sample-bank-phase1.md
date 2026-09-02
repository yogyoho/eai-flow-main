# Geo Sample Bank — Phase 1（geo_samples 管理模块 MVP）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建成 geo_samples 扩展模块（上传→三分支解析→自动脱敏→人工抽审），50 份地质报告可走完 uploaded→reviewed 全流程；RAGFlow 分发与编译管线留 Phase 2。

**Architecture:** 仿 `contract_price` 第八个扩展模块（backend 8 文件 + 前端路由壳/领域层双层）；MinIO 单 bucket `geo-samples`（raw/work/clean 三前缀）；脱敏为纯函数规则引擎；Gateway 不 import skill（Phase 1 无 skill 依赖）。

**Tech Stack:** FastAPI + SQLAlchemy(共享 Base) + minio SDK + python-docx + pymupdf4llm + httpx(eai-flow-ocr) + Next.js/RSTest(TanStack Query)。

**Spec:** `docs/superpowers/specs/2026-09-01-geo-sample-bank-design.md` §2/§3/§9-Phase1。

**约定（每个任务通用）：**
- 后端测试命令一律 `cd backend && PYTHONPATH=. uv run pytest tests/<file> -v`；全量 `make test`；lint `make lint`（ruff, line 240）。
- 前端命令 `cd frontend && pnpm typecheck && pnpm lint`；单测 `pnpm test`。
- **并发会话活跃**：提交一律 pathspec（`git commit -m "..." -- <files>`），提交前 `git status --porcelain <files>` 确认只含自己的文件。
- 所有后端新文件头部带 `# EAI-CUSTOM: forked from app.extensions.contract_price (geo-sample-bank Phase 1, spec 2026-09-01)`。

---

### Task 1: 钉住 RAGFlow 镜像版本

**Files:**
- Modify: `docker/.env.docker:59`

- [ ] **Step 1: 修改 env**

```bash
# docker/.env.docker 第 59 行，把
RAGFLOW_IMAGE=infiniflow/ragflow:latest
# 改为
RAGFLOW_IMAGE=infiniflow/ragflow:v0.25.3
```

- [ ] **Step 2: 验证 compose 解析**

Run: `docker compose -f docker/docker-compose.ragflow.yaml config | grep image: | head -2`
Expected: 含 `infiniflow/ragflow:v0.25.3`

- [ ] **Step 3: Commit**

```bash
git add docker/.env.docker && git commit -m "chore(ragflow): pin dev image to v0.25.3 (eliminate latest drift, geo-sample-bank spec)" -- docker/.env.docker
```

---

### Task 2: backend 模块骨架 + models.py（gsb_ 三表）

**Files:**
- Create: `backend/app/extensions/geo_samples/__init__.py`
- Create: `backend/app/extensions/geo_samples/models.py`
- Test: `backend/tests/test_geo_samples_extension.py`

- [ ] **Step 1: 写失败测试**（镜像 `test_contract_price_extension.py` 的 Base 注册断言）

```python
"""Tests for the geo_samples extension (models, redactor, parsers, routes)."""

def test_gsb_models_registered_on_shared_base():
    import app.extensions.geo_samples  # noqa: F401
    from app.extensions.database import Base

    tables = set(Base.metadata.tables)
    assert {"gsb_documents", "gsb_redactions", "gsb_run_history"} <= tables
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_extension.py -v`
Expected: FAIL（`No module named app.extensions.geo_samples`）

- [ ] **Step 3: 写 models.py**

```python
# EAI-CUSTOM: forked from app.extensions.contract_price.models (geo-sample-bank Phase 1).
# gsb_ tables auto-create at gateway startup via shared Base; new columns MUST go
# through database.migrate_db() idempotent ALTER (create_all never adds columns).
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class GsbDocument(Base):
    """一份样例报告的资产行。status: uploaded→parsed→redacted→reviewed（Phase 2 追加 compiled）。"""

    __tablename__ = "gsb_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    file_name: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_type: Mapped[str] = mapped_column(String(16))  # docx / pdf
    stage: Mapped[str] = mapped_column(String(16), default="exploration")  # survey/detail/exploration
    mineral: Mapped[str] = mapped_column(String(32), default="copper")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="uploaded", index=True)
    parse_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)  # docx/pdf_text/pdf_ocr/failed
    raw_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)  # s3://geo-samples/raw/<report_id>/<file>
    work_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)  # s3://geo-samples/work/<report_id>/parsed.md（未脱敏中间件）
    clean_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)  # s3://geo-samples/clean/<report_id>/source.md
    redaction_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: {rule: count}
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class GsbRedaction(Base):
    """脱敏事件流水——只落位置与原文 hash，绝不落明文。"""

    __tablename__ = "gsb_redactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    rule: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))  # auto / review
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    original_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class GsbRunHistory(Base):
    __tablename__ = "gsb_run_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    run_type: Mapped[str] = mapped_column(String(16))  # parse / redact
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/done/failed
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 4: 建空 `__init__.py`（暂只导出 router 占位，Task 8 补全）**

```python
# EAI-CUSTOM: forked from app.extensions.contract_price (geo-sample-bank Phase 1).
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_extension.py -v`
Expected: PASS（1 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/geo_samples/ backend/tests/test_geo_samples_extension.py
git commit -m "feat(geo-samples): gsb_ models on shared Base (documents/redactions/run_history)" -- backend/app/extensions/geo_samples/ backend/tests/test_geo_samples_extension.py
```

---

### Task 3: storage.py（MinIO 单 bucket 三前缀）

**Files:**
- Create: `backend/app/extensions/geo_samples/storage.py`
- Test: `backend/tests/test_geo_samples_extension.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_storage_key_layout(monkeypatch):
    from app.extensions.geo_samples import storage

    calls = []
    monkeypatch.setattr(storage, "_client", lambda: MagicMock(put_object=lambda *a, **k: calls.append(k)))
    uri = storage.put_raw("rep1", "报告.docx", b"data")
    assert uri == "s3://geo-samples/raw/rep1/报告.docx"
    assert calls[0]["bucket"] == "geo-samples"
    assert calls[0]["object_name"] == "raw/rep1/报告.docx"
```

（文件顶部补 `from unittest.mock import MagicMock`）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_extension.py::test_storage_key_layout -v`
Expected: FAIL（`cannot import storage`）

- [ ] **Step 3: 写 storage.py**（fork 自 `app/extensions/contract_price/storage.py`，改 bucket/env/三函数）

```python
# EAI-CUSTOM: forked from app.extensions.contract_price.storage (geo-sample-bank Phase 1).
# Intentionally do NOT reuse app.extensions.config storage.minio_endpoint: that one
# defaults to localhost:9000, unreachable from inside the gateway container (same
# rationale as contract_price). Single bucket, three prefixes: raw/ work/ clean/.
import os

from minio import Minio

BUCKET = "geo-samples"
_endpoint = os.environ.get("GSB_MINIO_ENDPOINT", "ragflow-minio:9000")
_access = os.environ.get("GSB_MINIO_ACCESS_KEY", "minioadmin")
_secret = os.environ.get("GSB_MINIO_SECRET_KEY", "minioadmin")
_secure = os.environ.get("GSB_MINIO_SECURE", "false").lower() == "true"

_ensured = False


def _client() -> Minio:
    global _ensured
    mc = Minio(_endpoint, access_key=_access, secret_key=_secret, secure=_secure)
    if not _ensured and not mc.bucket_exists(BUCKET):
        mc.make_bucket(BUCKET)
    _ensured = True
    return mc


def put_raw(report_id: str, file_name: str, data: bytes) -> str:
    key = f"raw/{report_id}/{file_name}"
    _client().put_object(bucket=BUCKET, object_name=key, data=__import__("io").BytesIO(data), length=len(data))
    return f"s3://{BUCKET}/{key}"


def put_work(report_id: str, data: bytes) -> str:
    key = f"work/{report_id}/parsed.md"
    _client().put_object(bucket=BUCKET, object_name=key, data=__import__("io").BytesIO(data), length=len(data))
    return f"s3://{BUCKET}/{key}"


def put_clean(report_id: str, data: bytes) -> str:
    key = f"clean/{report_id}/source.md"
    _client().put_object(bucket=BUCKET, object_name=key, data=__import__("io").BytesIO(data), length=len(data))
    return f"s3://{BUCKET}/{key}"


def get_object(uri: str) -> bytes:
    """s3://bucket/key → bytes（work/clean/preview 通用读取）。"""
    prefix = f"s3://{BUCKET}/"
    assert uri.startswith(prefix), f"unexpected uri: {uri}"
    resp = _client().get_object(BUCKET, uri[len(prefix):])
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def object_exists(uri: str) -> bool:
    prefix = f"s3://{BUCKET}/"
    if not uri.startswith(prefix):
        return False
    from minio.error import S3Error

    try:
        _client().stat_object(BUCKET, uri[len(prefix):])
        return True
    except S3Error:
        return False
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_extension.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/storage.py backend/tests/test_geo_samples_extension.py
git commit -m "feat(geo-samples): MinIO storage (geo-samples bucket, raw/work/clean prefixes)" -- backend/app/extensions/geo_samples/storage.py backend/tests/test_geo_samples_extension.py
```

---

### Task 4: redactor.py（两档脱敏规则引擎，纯函数）

**Files:**
- Create: `backend/app/extensions/geo_samples/redactor.py`
- Test: `backend/tests/test_geo_samples_redactor.py`

- [ ] **Step 1: 写失败测试**

```python
"""两档脱敏规则引擎：auto=替换****、review=只标记；地质数值永不脱敏。"""

from app.extensions.geo_samples.redactor import MASK, redact_text


def test_auto_replaces_cert_and_coords():
    md = "探矿权证号C5300002023000001，坐标 X 3546123.45, Y 38456789.12。\n联系电话13812345678。"
    clean, events = redact_text(md)
    assert "C5300002023000001" not in clean
    assert MASK in clean
    assert "13812345678" not in clean
    rules = {e["rule"] for e in events if e["replaced"]}
    assert "exploration_cert" in rules
    assert "coord_pair" in rules
    assert "phone" in rules


def test_review_mode_flags_but_does_not_replace():
    md = "项目负责人：张三丰"
    clean, events = redact_text(md)
    assert "张三丰" in clean  # 不替换
    assert any(e["rule"] == "person_field" and not e["replaced"] for e in events)


def test_geo_numbers_never_redacted():
    """红线：品位/厚度/资源量等地质数值必须原样保留（东川样例口径）。"""
    md = "平均品位0.85%，最小可采厚度1.00m，资源量77.36万吨，涌水量11850m3/d。"
    clean, events = redact_text(md)
    assert clean == md
    assert events == []


def test_events_record_hash_not_plaintext():
    import hashlib

    _, events = redact_text("证号C5300002023000002")
    e = events[0]
    assert e["original_hash"] == hashlib.sha256(b"C5300002023000002").hexdigest()
    assert "C5300002023000002" not in str(e)


def test_overlapping_matches_keep_first():
    md = "云南XX勘查院有限公司"
    clean, events = redact_text(md)
    assert "云南" in clean or MASK in clean  # 不崩溃即可；重叠命中只记一条
    assert len([e for e in events if e["replaced"]]) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_redactor.py -v`
Expected: FAIL（No module named）

- [ ] **Step 3: 写 redactor.py**

```python
# EAI-CUSTOM: geo-sample-bank Phase 1 脱敏规则引擎（spec 2026-09-01 §3.3）。
# 两档制：auto=替换为 MASK；review=只记事件不替换。红线：不含任何匹配地质数值的规则——
# 品位/厚度/资源量/涌水量等数字必须原样保留（脱敏会毁掉 SL3 指纹库与深度标定）。
from __future__ import annotations

import hashlib
import re

MASK = "****"


def _p(pattern: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(pattern, flags)


RULES: list[tuple[str, re.Pattern[str], str]] = [
    # ── auto 档：身份类，直接替换 ──
    ("exploration_cert", _p(r"\bC\d{10,16}\b"), "auto"),  # 探矿许可证号（bug-2216 形态 C+行政区划+年+序号）
    ("uscc", _p(r"\b[0-9A-HJ-NPQRTUWXY]{18}\b"), "auto"),  # 统一社会信用代码
    ("coord_pair", _p(r"X\s*[:：]?\s*\d{6,8}(?:\.\d+)?\s*[,，、]\s*Y\s*[:：]?\s*\d{6,8}(?:\.\d+)?", re.I), "auto"),  # 高斯 XY 对
    ("latlon", _p(r"\d{1,3}°\d{1,2}(?:′\d{1,2}(?:\.\d+)?)?″?\s*[NSEW]"), "auto"),  # 经纬度（带方位字母）
    ("phone", _p(r"\b1[3-9]\d{9}\b"), "auto"),
    ("tel", _p(r"\b0\d{2,3}-\d{7,8}\b"), "auto"),
    ("email", _p(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "auto"),
    ("org_name", _p(r"[一-龥（）()]{2,24}(?:有限公司|股份有限公司|集团有限公司|勘查院|勘察院|研究院|设计院|地质队|地质大队)"), "auto"),
    # ── review 档：高误报，只标记待审 ──
    ("person_field", _p(r"(?:负责人|编制人|审核人|审查人|项目经理|技术负责人)[：:]\s*[一-龥]{2,4}"), "review"),
]


def redact_text(md: str) -> tuple[str, list[dict]]:
    """返回 (脱敏后文本, 事件列表)。事件含 rule/mode/start/end/original_hash/replaced。"""
    spans: list[tuple[int, int, str, str]] = []  # (start, end, rule, mode)
    for rule, rx, mode in RULES:
        for m in rx.finditer(md):
            spans.append((m.start(), m.end(), rule, mode))
    # 重叠消解：按 start 升序、end 降序保留最先/最长者
    spans.sort(key=lambda s: (s[0], -s[1]))
    kept: list[tuple[int, int, str, str]] = []
    for s in spans:
        if kept and s[0] < kept[-1][1]:
            continue
        kept.append(s)

    events: list[dict] = []
    out = md
    for start, end, rule, mode in reversed(kept):  # 从尾向头替换，偏移不失效
        original = md[start:end]
        replaced = mode == "auto"
        if replaced:
            out = out[:start] + MASK + out[end:]
        events.append(
            {
                "rule": rule,
                "mode": mode,
                "start": start,
                "end": end,
                "original_hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "replaced": replaced,
            }
        )
    events.reverse()  # 恢复文档顺序
    return out, events
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_redactor.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/redactor.py backend/tests/test_geo_samples_redactor.py
git commit -m "feat(geo-samples): two-tier redaction engine (auto replace / review flag, geo-number red line)" -- backend/app/extensions/geo_samples/redactor.py backend/tests/test_geo_samples_redactor.py
```

---

### Task 5: parsers.py（三分支解析：docx / pdf_text / 扫描→OCR）

**Files:**
- Create: `backend/app/extensions/geo_samples/parsers.py`
- Test: `backend/tests/test_geo_samples_parsers.py`

- [ ] **Step 1: 写失败测试**

```python
"""三分支解析：docx→md（含 OLE 占位）、pdf 文字版、扫描判定异常。"""

import io

import pytest


def _build_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("第1章 总论", level=1)
    doc.add_paragraph("本矿区位于云南省。")
    doc.add_heading("1.1 编制依据", level=2)
    doc.add_paragraph("依据DZ/T 0214-2020。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "矿体编号"
    table.cell(0, 1).text = "品位%"
    table.cell(1, 0).text = "Ⅰ号"
    table.cell(1, 1).text = "0.85"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_to_markdown_structure():
    from app.extensions.geo_samples.parsers import docx_to_markdown

    md = docx_to_markdown(_build_docx())
    assert md.startswith("## 第1章 总论")
    assert "### 1.1 编制依据" in md
    assert "| 矿体编号 | 品位% |" in md
    assert "| --- | --- |" in md
    assert "| Ⅰ号 | 0.85 |" in md


def test_docx_ole_formula_placeholder():
    """段落含 OLE 对象（公式）且无文本 → [公式:pN] 占位。"""
    from docx import Document
    from docx.oxml.ns import qn
    from app.extensions.geo_samples.parsers import docx_to_markdown

    doc = Document()
    p = doc.add_paragraph()
    p._p.append(p._p.makeelement(qn("w:object"), {}))
    buf = io.BytesIO()
    doc.save(buf)
    assert "[公式:p1]" in docx_to_markdown(buf.getvalue())


def test_pdf_scan_detection_raises():
    from app.extensions.geo_samples.parsers import ScannedPdfError, pdf_text_to_markdown

    # 1 页几乎无文本 → 判定扫描件
    fake_pdf = _make_pdf_with_text("仅几个字")
    with pytest.raises(ScannedPdfError):
        pdf_text_to_markdown(fake_pdf)


def _make_pdf_with_text(text: str) -> bytes:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def test_ocr_dispatch_contracts(monkeypatch):
    from app.extensions.geo_samples import parsers

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"pages": [{"page_no": 1, "text": "OCR 第一页"}, {"page_no": 2, "text": "OCR 第二页"}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, files=None):
            captured["url"] = url
            captured["files"] = files
            return FakeResp()

    monkeypatch.setattr(parsers.httpx, "AsyncClient", FakeClient)

    import asyncio

    md = asyncio.run(parsers.ocr_pdf_to_markdown(b"pdfbytes"))
    assert "http" in captured["url"] and captured["url"].endswith("/ocr")
    assert "OCR 第一页" in md and "OCR 第二页" in md
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_parsers.py -v`
Expected: FAIL（No module named）

- [ ] **Step 3: 写 parsers.py**

```python
# EAI-CUSTOM: geo-sample-bank Phase 1 三分支解析（spec §3.3）。
# docx→python-docx 结构化转 md；pdf 文字版→pymupdf4llm；字符密度稀疏判定扫描件→eai-flow-ocr。
# MathType OLE 公式不解析，落 [公式:pN] 占位（W1 比拟法公式人工转录先例）。
from __future__ import annotations

import io
import os

import httpx

OCR_TIMEOUT = 1800.0  # contract_price document_parser 同款


class ScannedPdfError(Exception):
    """文字密度低于阈值——判定为扫描件，须走 OCR。"""


def docx_to_markdown(data: bytes) -> str:
    import docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    formula_no = 0
    for block in doc.iter_inner_content():  # python-docx>=1.1：按文档顺序交错产出段落/表格
        if isinstance(block, Paragraph):
            text = block.text.strip()
            style = (block.style.name or "").lower() if block.style is not None else ""
            if not text:
                # OLE 公式对象：w:object 元素存在且无文本 → 占位
                if block._p.findall(".//" + qn("w:object")):
                    formula_no += 1
                    lines.append(f"[公式:p{formula_no}]")
                continue
            if style.startswith("heading 1") or style == "title":
                lines.append(f"## {text}")
            elif style.startswith("heading 2"):
                lines.append(f"### {text}")
            elif style.startswith(("heading 3", "heading 4", "heading 5")):
                lines.append(f"#### {text}")
            else:
                lines.append(text)
        elif isinstance(block, Table):
            rows = [[c.text.strip().replace("|", "\\|") for c in r.cells] for r in block.rows]
            if not rows:
                continue
            header = rows[0]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")
            for r in rows[1:]:
                lines.append("| " + " | ".join(r) + " |")
    return "\n\n".join(lines)


def pdf_text_to_markdown(data: bytes) -> str:
    import fitz
    import pymupdf4llm

    doc = fitz.open(stream=data, filetype="pdf")
    total_chars = sum(len(p.get_text()) for p in doc)
    density = total_chars / max(len(doc), 1)
    if density < 200:  # 每页<200字符 → 扫描件（harness file_conversion 稀疏回退同思路，改抛错转 OCR）
        raise ScannedPdfError(f"文字密度 {density:.0f} 字符/页 < 200，判定扫描件，需 OCR")
    return pymupdf4llm.to_markdown(doc)


async def ocr_pdf_to_markdown(data: bytes, base_url: str | None = None) -> str:
    url = (base_url or os.environ.get("OCR_SERVICE_URL", "http://eai-flow-ocr:8010")).rstrip("/") + "/ocr"
    async with httpx.AsyncClient(timeout=OCR_TIMEOUT) as client:
        resp = await client.post(url, files={"file": ("doc.pdf", data, "application/pdf")})
        resp.raise_for_status()
    pages = resp.json().get("pages", [])
    return "\n\n".join(p.get("text", "") for p in pages)


async def parse_document(file_name: str, data: bytes) -> tuple[str, str]:
    """统一入口 → (markdown, parse_mode)。docx 分支同步、pdf 分支可能转 OCR。"""
    lower = file_name.lower()
    if lower.endswith(".docx"):
        return docx_to_markdown(data), "docx"
    if lower.endswith(".pdf"):
        try:
            return pdf_text_to_markdown(data), "pdf_text"
        except ScannedPdfError:
            return await ocr_pdf_to_markdown(data), "pdf_ocr"
    raise ValueError(f"不支持的文件类型: {file_name}（仅 .docx/.pdf）")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_parsers.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/parsers.py backend/tests/test_geo_samples_parsers.py
git commit -m "feat(geo-samples): three-branch parsing (docx md / pdf text / scan->OCR, OLE placeholder)" -- backend/app/extensions/geo_samples/parsers.py backend/tests/test_geo_samples_parsers.py
```

---

### Task 6: crud.py + schemas.py

**Files:**
- Create: `backend/app/extensions/geo_samples/crud.py`
- Create: `backend/app/extensions/geo_samples/schemas.py`
- Test: `backend/tests/test_geo_samples_extension.py`（追加）

- [ ] **Step 1: 写失败测试**（镜像 cpa 的 find_duplicate mock 测试）

```python
@pytest.mark.asyncio
async def test_find_duplicate_document_matches_cross_filename():
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import crud
    from app.extensions.geo_samples.models import GsbDocument

    existing = GsbDocument(
        report_id="rep-a", file_name="a.pdf", file_hash="h1", file_type="pdf", raw_uri="s3://geo-samples/raw/rep-a/a.pdf"
    )

    def session_returning(row):
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=row)
        session.execute = AsyncMock(return_value=result)
        return session

    dup = await crud.find_duplicate_document(session_returning(existing), "h1", exclude_uri="s3://geo-samples/raw/rep-b/b.pdf")
    assert dup is existing
    assert await crud.find_duplicate_document(session_returning(None), "h1", exclude_uri="s3://geo-samples/raw/x/x.pdf") is None


def test_schemas_roundtrip():
    from app.extensions.geo_samples.schemas import DocumentOut, ReviewRequest, UploadMeta

    meta = UploadMeta(report_id="rep-1", stage="exploration", mineral="gold", year=2019)
    assert meta.mineral == "gold"
    assert ReviewRequest(decision="reject", note="漏脱矿权人").decision == "reject"
    assert DocumentOut.model_fields["status"].annotation is not None
```

（文件顶部补 `import pytest`）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_extension.py -v`
Expected: FAIL（cannot import crud/schemas）

- [ ] **Step 3: 写 crud.py 与 schemas.py**

`crud.py`：

```python
# EAI-CUSTOM: forked from app.extensions.contract_price.crud (geo-sample-bank Phase 1).
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import GsbDocument, GsbRedaction, GsbRunHistory


async def find_duplicate_document(db: AsyncSession, file_hash: str, exclude_uri: str | None = None) -> GsbDocument | None:
    """同 hash 不同 storage_uri → 重复（同 uri=原地重传不算）。"""
    stmt = select(GsbDocument).where(GsbDocument.file_hash == file_hash)
    rows = (await db.execute(stmt)).scalars().all()
    for row in rows:
        if row.raw_uri and row.raw_uri != exclude_uri:
            return row
    return None


async def get_document(db: AsyncSession, document_id: str) -> GsbDocument | None:
    return (await db.execute(select(GsbDocument).where(GsbDocument.id == document_id))).scalar_one_or_none()


async def get_document_by_report_id(db: AsyncSession, report_id: str) -> GsbDocument | None:
    return (await db.execute(select(GsbDocument).where(GsbDocument.report_id == report_id))).scalar_one_or_none()


async def list_documents(db: AsyncSession, stage: str | None = None, mineral: str | None = None,
                         status: str | None = None, skip: int = 0, limit: int = 50) -> list[GsbDocument]:
    stmt = select(GsbDocument).order_by(GsbDocument.created_at.desc())
    if stage:
        stmt = stmt.where(GsbDocument.stage == stage)
    if mineral:
        stmt = stmt.where(GsbDocument.mineral == mineral)
    if status:
        stmt = stmt.where(GsbDocument.status == status)
    stmt = stmt.offset(skip).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def list_redactions(db: AsyncSession, document_id: str) -> list[GsbRedaction]:
    stmt = select(GsbRedaction).where(GsbRedaction.document_id == document_id).order_by(GsbRedaction.start)
    return list((await db.execute(stmt)).scalars().all())


async def add_redactions(db: AsyncSession, document_id: str, events: list[dict]) -> None:
    for e in events:
        db.add(GsbRedaction(document_id=document_id, rule=e["rule"], mode=e["mode"], start=e["start"],
                            end=e["end"], original_hash=e["original_hash"]))


async def create_run(db: AsyncSession, document_id: str | None, run_type: str) -> GsbRunHistory:
    run = GsbRunHistory(document_id=document_id, run_type=run_type)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def finish_run(db: AsyncSession, run_id: str, status: str, detail: str | None = None) -> None:
    from datetime import datetime

    run = (await db.execute(select(GsbRunHistory).where(GsbRunHistory.id == run_id))).scalar_one_or_none()
    if run:
        run.status = status
        run.detail = detail
        run.finished_at = datetime.utcnow()
        await db.commit()


async def has_running_run(db: AsyncSession, document_id: str, run_type: str) -> bool:
    stmt = select(GsbRunHistory).where(GsbRunHistory.document_id == document_id,
                                       GsbRunHistory.run_type == run_type,
                                       GsbRunHistory.status == "running")
    return (await db.execute(stmt)).scalar_one_or_none() is not None
```

`schemas.py`：

```python
# EAI-CUSTOM: forked from app.extensions.contract_price.schemas (geo-sample-bank Phase 1).
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

ALLOWED_STAGES = {"survey", "detail", "exploration"}
ALLOWED_MINERALS = {"copper", "coal", "gold", "iron", "lead_zinc", "other"}
ALLOWED_STATUSES = {"uploaded", "parsed", "redacted", "reviewed", "failed"}


class UploadMeta(BaseModel):
    report_id: str = Field(min_length=2, max_length=128, pattern=r"^[a-z0-9][a-z0-9\-_]*$")
    stage: str = "exploration"
    mineral: str = "copper"
    year: int | None = None
    region: str | None = None


class ReviewRequest(BaseModel):
    decision: str  # approve / reject
    note: str | None = None


class RedactionOut(BaseModel):
    id: str
    rule: str
    mode: str
    start: int
    end: int
    original_hash: str


class DocumentOut(BaseModel):
    id: str
    report_id: str
    file_name: str
    file_type: str
    stage: str
    mineral: str
    year: int | None
    region: str | None
    status: str
    parse_mode: str | None
    redaction_summary: str | None
    review_note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: str
    document_id: str | None
    run_type: str
    status: str
    detail: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_extension.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/crud.py backend/app/extensions/geo_samples/schemas.py backend/tests/test_geo_samples_extension.py
git commit -m "feat(geo-samples): crud + pydantic schemas (dedup/status filters/review)" -- backend/app/extensions/geo_samples/crud.py backend/app/extensions/geo_samples/schemas.py backend/tests/test_geo_samples_extension.py
```

---

### Task 7: service.py（状态机编排 + 后台任务）

**Files:**
- Create: `backend/app/extensions/geo_samples/service.py`
- Test: `backend/tests/test_geo_samples_service.py`

- [ ] **Step 1: 写失败测试**（monkeypatch storage/parsers，验证状态迁移与失败落账）

```python
"""服务编排：parse→parsed、redact→redacted、异常→failed+run 落账。"""

import pytest


@pytest.mark.asyncio
async def test_run_parse_happy_path(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import crud, service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r1", file_name="a.docx", file_hash="h", file_type="docx", status="uploaded",
                      raw_uri="s3://geo-samples/raw/r1/a.docx")
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def _get(db_, did):
        return doc

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.storage, "get_object", lambda uri: b"docx-bytes")
    monkeypatch.setattr(service.parsers, "parse_document", AsyncMock(return_value=("# 报告\n正文", "docx")))
    monkeypatch.setattr(service.storage, "put_work", lambda rid, data: f"s3://geo-samples/work/{rid}/parsed.md")

    await service.run_parse(db, "doc-1", run_id="run-1")

    assert doc.status == "parsed"
    assert doc.parse_mode == "docx"
    assert doc.work_uri == "s3://geo-samples/work/r1/parsed.md"


@pytest.mark.asyncio
async def test_run_parse_failure_marks_failed(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r2", file_name="a.pdf", file_hash="h", file_type="pdf", status="uploaded",
                      raw_uri="s3://geo-samples/raw/r2/a.pdf")
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def _get(db_, did):
        return doc

    async def _boom(*a, **k):
        raise RuntimeError("parse exploded")

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.storage, "get_object", lambda uri: b"x")
    monkeypatch.setattr(service.parsers, "parse_document", _boom)
    monkeypatch.setattr(service.crud, "finish_run", AsyncMock())

    await service.run_parse(db, "doc-2", run_id="run-2")
    assert doc.status == "failed"
    service.crud.finish_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_redact_writes_clean_and_summary(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r3", file_name="a.docx", file_hash="h", file_type="docx", status="parsed",
                      work_uri="s3://geo-samples/work/r3/parsed.md")
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _get(db_, did):
        return doc

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.storage, "get_object", lambda uri: "证号C5300002023000003 正文".encode("utf-8"))
    monkeypatch.setattr(service.storage, "put_clean", lambda rid, data: f"s3://geo-samples/clean/{rid}/source.md")
    monkeypatch.setattr(service.crud, "add_redactions", AsyncMock())

    await service.run_redact(db, "doc-3", run_id="run-3")

    assert doc.status == "redacted"
    assert doc.redaction_summary is not None and "exploration_cert" in doc.redaction_summary
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_service.py -v`
Expected: FAIL（No module named service）

- [ ] **Step 3: 写 service.py**

```python
# EAI-CUSTOM: forked from app.extensions.contract_price.service (geo-sample-bank Phase 1).
# Phase 1 无 skill 依赖——解析/脱敏全部 in-process async；compile 子进程模式留 Phase 2。
from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from . import crud, parsers, storage

log = logging.getLogger("geo_samples.service")


async def run_parse(db: AsyncSession, document_id: str, run_id: str) -> None:
    """后台任务：raw → md（work/）。任何异常 → status=failed + run 落账，不抛出。"""
    doc = await crud.get_document(db, document_id)
    if doc is None:
        await crud.finish_run(db, run_id, "failed", "document not found")
        return
    try:
        raw = storage.get_object(doc.raw_uri)
        md, mode = await parsers.parse_document(doc.file_name, raw)
        doc.work_uri = storage.put_work(doc.report_id, md.encode("utf-8"))
        doc.parse_mode = mode
        doc.status = "parsed"
        await db.commit()
        await crud.finish_run(db, run_id, "done", f"mode={mode}")
    except Exception as exc:  # noqa: BLE001 —— 后台任务必须吞异常落账
        log.exception("parse failed for %s", doc.report_id)
        doc.status = "failed"
        doc.parse_mode = "failed"
        await db.commit()
        await crud.finish_run(db, run_id, "failed", str(exc))


async def run_redact(db: AsyncSession, document_id: str, run_id: str) -> None:
    """后台任务：work/parsed.md → 规则脱敏 → clean/source.md + 事件流水。"""
    from .redactor import redact_text

    doc = await crud.get_document(db, document_id)
    if doc is None:
        await crud.finish_run(db, run_id, "failed", "document not found")
        return
    try:
        text = storage.get_object(doc.work_uri).decode("utf-8")
        clean, events = redact_text(text)
        doc.clean_uri = storage.put_clean(doc.report_id, clean.encode("utf-8"))
        await crud.add_redactions(db, doc.id, events)
        summary: dict[str, int] = {}
        for e in events:
            summary[e["rule"]] = summary.get(e["rule"], 0) + 1
        doc.redaction_summary = json.dumps(summary, ensure_ascii=False)
        doc.status = "redacted"
        await db.commit()
        await crud.finish_run(db, run_id, "done", json.dumps(summary, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        log.exception("redact failed for %s", doc.report_id)
        doc.status = "failed"
        await db.commit()
        await crud.finish_run(db, run_id, "failed", str(exc))


async def apply_review(db: AsyncSession, document_id: str, decision: str, note: str | None) -> None:
    """人工抽审闸门：approve → reviewed；reject → 退回 redacted 并留 note。"""
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise ValueError("document not found")
    if doc.status != "redacted":
        raise ValueError(f"仅 redacted 状态可审（当前 {doc.status}）")
    if decision not in ("approve", "reject"):
        raise ValueError("decision 必须是 approve/reject")
    doc.status = "reviewed" if decision == "approve" else "redacted"
    doc.review_note = note
    await db.commit()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_service.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/service.py backend/tests/test_geo_samples_service.py
git commit -m "feat(geo-samples): status machine orchestration (parse/redact background, review gate)" -- backend/app/extensions/geo_samples/service.py backend/tests/test_geo_samples_service.py
```

---

### Task 8: routers.py + __init__.py + Gateway 注册

**Files:**
- Create: `backend/app/extensions/geo_samples/routers.py`
- Modify: `backend/app/extensions/geo_samples/__init__.py`
- Modify: `backend/app/gateway/app.py`（顶部 import 区 + include_router 区，锚：`app.py:921` contract_price include 行之后）
- Test: `backend/tests/test_geo_samples_extension.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_router_exposes_all_functional_areas():
    from app.extensions.geo_samples import router

    paths = {r.path for r in router.routes}
    base = "/api/extensions/geo-samples"
    assert f"{base}/documents" in paths
    assert f"{base}/documents/upload" in paths
    assert any("parse" in p for p in paths)
    assert any("/redact" in p for p in paths)
    assert any("review" in p for p in paths)
    assert any("redactions" in p for p in paths)
    assert f"{base}/runs" in paths


def test_all_endpoints_require_permission_source_level():
    """静态源码断言：每个 @router. 端点附近都有 _PERM/require_permission 防护。"""
    import inspect

    from app.extensions.geo_samples import routers

    src = inspect.getsource(routers)
    endpoints = src.count("@router.")
    guarded = src.count("= _PERM") + src.count("require_permission(")
    assert guarded >= endpoints, f"{endpoints} 个端点仅 {guarded} 处权限防护"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_extension.py -v`
Expected: FAIL（cannot import router）

- [ ] **Step 3: 写 routers.py**

```python
# EAI-CUSTOM: forked from app.extensions.contract_price.routers (geo-sample-bank Phase 1).
# 所有端点统一 require_permission("geo_samples:access")（最粗粒度，与 cpa 模式一致；
# 细粒度审核权限留待有真实角色需求再加）。
from __future__ import annotations

import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db

from . import crud, schemas, service, storage

router = APIRouter(prefix="/api/extensions/geo-samples", tags=["Geo Sample Bank"])
_PERM = Depends(require_permission("geo_samples:access"))


@router.get("/documents")
async def list_documents(stage: str | None = None, mineral: str | None = None, status: str | None = None,
                         skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db), _: object = _PERM):
    rows = await crud.list_documents(db, stage=stage, mineral=mineral, status=status, skip=skip, limit=limit)
    return {"items": [schemas.DocumentOut.model_validate(r).model_dump() for r in rows], "skip": skip, "limit": limit}


@router.get("/documents/{document_id}")
async def get_document(document_id: str, db: AsyncSession = Depends(get_db), _: object = _PERM):
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise HTTPException(404, "样例不存在")
    return schemas.DocumentOut.model_validate(doc).model_dump()


@router.post("/documents/upload")
async def upload_document(background: BackgroundTasks, file: UploadFile = File(...),
                          report_id: str = Form(...), stage: str = Form("exploration"),
                          mineral: str = Form("copper"), year: int | None = Form(None),
                          region: str | None = Form(None), db: AsyncSession = Depends(get_db),
                          _: object = _PERM):
    name = file.filename or ""
    if not name.lower().endswith((".docx", ".pdf")):
        raise HTTPException(400, "仅支持 .docx/.pdf")
    meta = schemas.UploadMeta(report_id=report_id, stage=stage, mineral=mineral, year=year, region=region)
    if meta.stage not in schemas.ALLOWED_STAGES or meta.mineral not in schemas.ALLOWED_MINERALS:
        raise HTTPException(400, "stage/mineral 取值非法")
    if await crud.get_document_by_report_id(db, meta.report_id):
        raise HTTPException(409, f"report_id {meta.report_id} 已存在")
    data = await file.read()
    digest = hashlib.sha256(data).hexdigest()
    dup = await crud.find_duplicate_document(db, digest, exclude_uri=None)
    if dup is not None:
        raise HTTPException(409, "相同内容的样例已存在（file_hash 命中）")
    file_type = "docx" if name.lower().endswith(".docx") else "pdf"
    raw_uri = storage.put_raw(meta.report_id, name, data)
    doc = schemas.DocumentOut.model_validate(
        _create_document(db, meta, name, digest, file_type, raw_uri)
    )
    if await crud.has_running_run(db, doc.id, "parse"):
        raise HTTPException(409, "该样例已有解析任务在跑")
    run = await crud.create_run(db, doc.id, "parse")
    background.add_task(service.run_parse, db, doc.id, run.id)
    return {"document": doc.model_dump(), "run_id": run.id}


def _create_document(db, meta, name, digest, file_type, raw_uri):
    from .models import GsbDocument

    doc = GsbDocument(report_id=meta.report_id, file_name=name, file_hash=digest, file_type=file_type,
                      stage=meta.stage, mineral=meta.mineral, year=meta.year, region=meta.region,
                      status="uploaded", raw_uri=raw_uri)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/documents/{document_id}/parse")
async def parse_document(document_id: str, background: BackgroundTasks, db: AsyncSession = Depends(get_db),
                         _: object = _PERM):
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise HTTPException(404, "样例不存在")
    if await crud.has_running_run(db, document_id, "parse"):
        raise HTTPException(409, "解析任务已在跑")
    run = await crud.create_run(db, document_id, "parse")
    background.add_task(service.run_parse, db, document_id, run.id)
    return {"run_id": run.id}


@router.post("/documents/{document_id}/redact")
async def redact_document(document_id: str, background: BackgroundTasks, db: AsyncSession = Depends(get_db),
                          _: object = _PERM):
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise HTTPException(404, "样例不存在")
    if doc.status != "parsed":
        raise HTTPException(409, f"仅 parsed 状态可脱敏（当前 {doc.status}）")
    if await crud.has_running_run(db, document_id, "redact"):
        raise HTTPException(409, "脱敏任务已在跑")
    run = await crud.create_run(db, document_id, "redact")
    background.add_task(service.run_redact, db, document_id, run.id)
    return {"run_id": run.id}


@router.get("/documents/{document_id}/redactions")
async def list_redactions(document_id: str, db: AsyncSession = Depends(get_db), _: object = _PERM):
    rows = await crud.list_redactions(db, document_id)
    return {"items": [schemas.RedactionOut.model_validate(r).model_dump() for r in rows]}


@router.post("/documents/{document_id}/review")
async def review_document(document_id: str, body: schemas.ReviewRequest, db: AsyncSession = Depends(get_db),
                          _: object = _PERM):
    try:
        await service.apply_review(db, document_id, body.decision, body.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    doc = await crud.get_document(db, document_id)
    return schemas.DocumentOut.model_validate(doc).model_dump()


@router.get("/runs")
async def list_runs(db: AsyncSession = Depends(get_db), _: object = _PERM):
    from sqlalchemy import select

    from .models import GsbRunHistory

    rows = list((await db.execute(select(GsbRunHistory).order_by(GsbRunHistory.created_at.desc()).limit(50))).scalars())
    return {"items": [schemas.RunOut.model_validate(r).model_dump() for r in rows]}
```

- [ ] **Step 4: 补 `__init__.py` 导出**

```python
# EAI-CUSTOM: forked from app.extensions.contract_price (geo-sample-bank Phase 1).
from .models import GsbDocument, GsbRedaction, GsbRunHistory
from .routers import router

__all__ = ["router", "GsbDocument", "GsbRedaction", "GsbRunHistory"]
```

- [ ] **Step 5: Gateway 注册**（`backend/app/gateway/app.py`）

在 contract_price import 行（约 `:15`）后加：

```python
from app.extensions.geo_samples import router as geo_samples_router  # noqa: E402
```

在 `app.include_router(contract_price_router)`（约 `:921`）后加：

```python
app.include_router(geo_samples_router)  # Geo sample bank management API (EAI-CUSTOM)
```

- [ ] **Step 6: 跑测试确认通过 + gateway 冒烟**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_extension.py tests/test_geo_samples_service.py tests/test_geo_samples_redactor.py tests/test_geo_samples_parsers.py -v && PYTHONPATH=. python -c "import app.gateway.app"`
Expected: 全部 PASS；import 无异常

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/geo_samples/routers.py backend/app/extensions/geo_samples/__init__.py backend/app/gateway/app.py backend/tests/test_geo_samples_extension.py
git commit -m "feat(geo-samples): API routes + gateway wiring (upload/parse/redact/review/runs)" -- backend/app/extensions/geo_samples/routers.py backend/app/extensions/geo_samples/__init__.py backend/app/gateway/app.py backend/tests/test_geo_samples_extension.py
```

---

### Task 9: 权限四处联动 + 表加列迁移位

**Files:**
- Modify: `config/permissions.yaml`（contract_price 块在 `:126`，spare_parts 在 `:150`）
- Modify: `config/roles_custom.yaml`（镜像 contract-price 的角色授权行）
- Modify: `backend/app/extensions/database.py`（app registry 锚 `:1538` `"path": "/contract-price"` 邻块）
- Modify: `backend/app/extensions/license/service.py:37`（allowlist）

- [ ] **Step 1: permissions.yaml 加模块块**（紧随 spare_parts 块之后，同层级缩进）

```yaml
  # ─── 地质样例库（应用中心 → 地质管理；克隆自 contract_price，spec 2026-09-01 geo-sample-bank）───
  geo_samples:
    display_name: "地质样例库"
    nav_id: "nav:geo-samples"
    pages:
      - gsb:page:documents
      - gsb:page:review
      - gsb:page:tasks
```

- [ ] **Step 2: roles_custom.yaml 授权镜像**。先 `grep -n "cpa:page\|contract" config/roles_custom.yaml` 找到持有 contract_price 页面的角色块，给同一批角色追加：

```yaml
        - nav:geo-samples
        - gsb:page:documents
        - gsb:page:review
        - gsb:page:tasks
```

- [ ] **Step 3: database.py app-center 注册**。镜像 `:1538` 邻近的 contract-price 条目 dict，追加同构条目（保持同一 list 内）：

```python
                        {
                            "app_id": "geology",
                            "title": "地质样例库",
                            "path": "/geo-samples",
                            "license": "geo_samples",
                            "icon": "map",
                        },
```

（以邻块实际字段为准逐字段对齐——若邻块无 icon 键则不加。）

- [ ] **Step 4: license allowlist**（`backend/app/extensions/license/service.py:37` 邻行）：

```python
    "geo_samples",
```

- [ ] **Step 5: 验证**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_extension_registry.py tests/test_extension_gateway_wiring.py -v && PYTHONPATH=. python -c "from app.extensions.auth.registry import PermissionRegistry; r=PermissionRegistry(); print('geo_samples' in r.modules if hasattr(r,'modules') else 'ok')"`
Expected: PASS / 无异常且注册表可加载

- [ ] **Step 6: Commit**

```bash
git add config/permissions.yaml config/roles_custom.yaml backend/app/extensions/database.py backend/app/extensions/license/service.py
git commit -m "feat(geo-samples): permission four-place registration (yaml/roles/app-registry/license)" -- config/permissions.yaml config/roles_custom.yaml backend/app/extensions/database.py backend/app/extensions/license/service.py
```

---

### Task 10: 前端 types + api + hooks + api 测试

**Files:**
- Create: `frontend/src/extensions/geo-samples/types.ts`
- Create: `frontend/src/extensions/geo-samples/api.ts`
- Create: `frontend/src/extensions/geo-samples/hooks.ts`
- Test: `frontend/tests/unit/extensions/geo-samples/api.test.ts`

- [ ] **Step 1: 写失败测试**（镜像 `frontend/tests/unit/extensions/contract-price/api.test.ts` 的 rstest 模式——`rs.mock` 必须在 import 之前）

```typescript
import { describe, expect, rs, test } from "@rstest/core";

// EAI-CUSTOM: rs.mock is NOT fully hoisted under rstest — the module import
// must follow the mock (same pattern as extensions/contract-price/api.test.ts).
rs.mock("@/extensions/api/client", () => ({
  authFetch: rs.fn(),
}));

import { authFetch } from "@/extensions/api/client";
import { geoSamplesApi, qs } from "@/extensions/geo-samples/api";

function lastCall(): [string, RequestInit] {
  const calls = rs.mocked(authFetch).mock.calls;
  return calls[calls.length - 1] as unknown as [string, RequestInit];
}

describe("qs", () => {
  test("skips empty values", () => {
    expect(qs({ stage: "exploration", status: "", mineral: undefined })).toBe("?stage=exploration");
  });
});

describe("geoSamplesApi", () => {
  test("listDocuments builds URL with filters", async () => {
    rs.mocked(authFetch).mockResolvedValue({ items: [], skip: 0, limit: 50 });
    await geoSamplesApi.listDocuments({ stage: "exploration", mineral: "gold", status: "redacted" });
    const [url] = lastCall();
    expect(url).toContain("/geo-samples/documents");
    expect(url).toContain("mineral=gold");
  });

  test("review POSTs decision", async () => {
    rs.mocked(authFetch).mockResolvedValue({ id: "d1", status: "reviewed" });
    await geoSamplesApi.review("d1", { decision: "approve", note: null });
    const [url, opts] = lastCall();
    expect(url).toBe("/geo-samples/documents/d1/review");
    expect(opts.method).toBe("POST");
  });

  test("uploadDocument uses FormData", async () => {
    rs.mocked(authFetch).mockResolvedValue({ document: {}, run_id: "r1" });
    const fd = new FormData();
    await geoSamplesApi.uploadDocument(fd);
    const [, opts] = lastCall();
    expect(opts.method).toBe("POST");
    expect(opts.body).toBeInstanceOf(FormData);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && pnpm test -- geo-samples`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写 types.ts / api.ts / hooks.ts**

`types.ts`：

```typescript
// EAI-CUSTOM: geo-sample-bank Phase 1 (spec 2026-09-01).
export type GsbStatus = "uploaded" | "parsed" | "redacted" | "reviewed" | "failed";
export type GsbStage = "survey" | "detail" | "exploration";

export interface GsbDocument {
  id: string;
  report_id: string;
  file_name: string;
  file_type: string;
  stage: GsbStage;
  mineral: string;
  year: number | null;
  region: string | null;
  status: GsbStatus;
  parse_mode: string | null;
  redaction_summary: string | null;
  review_note: string | null;
  created_at: string;
}

export interface GsbRedaction {
  id: string;
  rule: string;
  mode: "auto" | "review";
  start: number;
  end: number;
  original_hash: string;
}

export interface GsbRun {
  id: string;
  document_id: string | null;
  run_type: "parse" | "redact";
  status: "running" | "done" | "failed";
  detail: string | null;
  created_at: string;
  finished_at: string | null;
}
```

`api.ts`（`authFetch` 来自 `@/extensions/api/client`，与 contract-price 同源）：

```typescript
// EAI-CUSTOM: forked from extensions/contract-price/api.ts (geo-sample-bank Phase 1).
import { authFetch } from "@/extensions/api/client";
import type { GsbDocument, GsbRedaction, GsbRun } from "./types";

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const pairs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return pairs.length ? `?${pairs.join("&")}` : "";
}

const BASE = "/geo-samples";

export const geoSamplesApi = {
  async listDocuments(filters: { stage?: string; mineral?: string; status?: string; skip?: number; limit?: number }) {
    return authFetch<{ items: GsbDocument[]; skip: number; limit: number }>(`${BASE}/documents${qs(filters)}`);
  },
  async getDocument(id: string) {
    return authFetch<GsbDocument>(`${BASE}/documents/${id}`);
  },
  async uploadDocument(form: FormData) {
    return authFetch<{ document: GsbDocument; run_id: string }>(`${BASE}/documents/upload`, { method: "POST", body: form });
  },
  async parse(id: string) {
    return authFetch<{ run_id: string }>(`${BASE}/documents/${id}/parse`, { method: "POST" });
  },
  async redact(id: string) {
    return authFetch<{ run_id: string }>(`${BASE}/documents/${id}/redact`, { method: "POST" });
  },
  async review(id: string, body: { decision: "approve" | "reject"; note: string | null }) {
    return authFetch<GsbDocument>(`${BASE}/documents/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
  async listRedactions(id: string) {
    return authFetch<{ items: GsbRedaction[] }>(`${BASE}/documents/${id}/redactions`);
  },
  async listRuns() {
    return authFetch<{ items: GsbRun[] }>(`${BASE}/runs`);
  },
};
```

`hooks.ts`：

```typescript
// EAI-CUSTOM: forked from extensions/contract-price/hooks.ts (geo-sample-bank Phase 1).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { geoSamplesApi } from "./api";

export function useGsbDocuments(filters: { stage?: string; mineral?: string; status?: string }) {
  return useQuery({
    queryKey: ["gsb-documents", filters],
    queryFn: () => geoSamplesApi.listDocuments(filters),
    refetchInterval: 5000, // 后台 parse/redact 进行中时表格自刷新
  });
}

export function useGsbRedactions(documentId: string | null) {
  return useQuery({
    queryKey: ["gsb-redactions", documentId],
    queryFn: () => geoSamplesApi.listRedactions(documentId!),
    enabled: documentId != null,
  });
}

export function useGsbRuns() {
  return useQuery({ queryKey: ["gsb-runs"], queryFn: () => geoSamplesApi.listRuns(), refetchInterval: 5000 });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["gsb-documents"] });
    void qc.invalidateQueries({ queryKey: ["gsb-runs"] });
  };
}

export function useGsbUpload() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (form: FormData) => geoSamplesApi.uploadDocument(form),
    onSuccess: invalidate,
  });
}

export function useGsbAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async ({ id, action }: { id: string; action: "parse" | "redact" }) => {
      if (action === "parse") return geoSamplesApi.parse(id);
      return geoSamplesApi.redact(id);
    },
    onSuccess: invalidate,
  });
}

export function useGsbReview() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (args: { id: string; decision: "approve" | "reject"; note: string | null }) =>
      geoSamplesApi.review(args.id, { decision: args.decision, note: args.note }),
    onSuccess: invalidate,
  });
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && pnpm test -- geo-samples`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/geo-samples/ frontend/tests/unit/extensions/geo-samples/
git commit -m "feat(geo-samples): frontend types/api/hooks + rstest coverage" -- frontend/src/extensions/geo-samples/ frontend/tests/unit/extensions/geo-samples/
```

---

### Task 11: 前端三页 + 路由壳

**Files:**
- Copy: `frontend/src/extensions/contract-price/components/ui/table.tsx` → `frontend/src/extensions/geo-samples/components/ui/table.tsx`
- Create: `frontend/src/extensions/geo-samples/components/DocumentsView.tsx`
- Create: `frontend/src/extensions/geo-samples/components/ReviewView.tsx`
- Create: `frontend/src/extensions/geo-samples/components/TasksView.tsx`
- Create: `frontend/src/app/geo-samples/layout.tsx`
- Create: `frontend/src/app/geo-samples/page.tsx`（documents）
- Create: `frontend/src/app/geo-samples/review/page.tsx`
- Create: `frontend/src/app/geo-samples/tasks/page.tsx`

- [ ] **Step 1: 复制轻量 table 原语**

```bash
mkdir -p frontend/src/extensions/geo-samples/components/ui
cp frontend/src/extensions/contract-price/components/ui/table.tsx frontend/src/extensions/geo-samples/components/ui/table.tsx
```

- [ ] **Step 2: DocumentsView**（表格 + 筛选 + 上传 + 动作按钮；PageHeader/StatCard 若 contract-price 有则同路径复用，无则纯标题）

```tsx
"use client";

// EAI-CUSTOM: geo-sample-bank Phase 1 DocumentsView.
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { useGsbAction, useGsbDocuments, useGsbUpload } from "@/extensions/geo-samples/hooks";
import type { GsbDocument } from "@/extensions/geo-samples/types";

const STATUS_ZH: Record<string, string> = {
  uploaded: "已上传", parsed: "已解析", redacted: "已脱敏", reviewed: "已过审", failed: "失败",
};

export function DocumentsView() {
  const router = useRouter();
  const [stage, setStage] = useState("");
  const [mineral, setMineral] = useState("");
  const [status, setStatus] = useState("");
  const { data, isLoading } = useGsbDocuments({ stage: stage || undefined, mineral: mineral || undefined, status: status || undefined });
  const upload = useGsbUpload();
  const action = useGsbAction();
  const fileRef = useRef<HTMLInputElement>(null);
  const reportIdRef = useRef<HTMLInputElement>(null);

  function onUpload() {
    const file = fileRef.current?.files?.[0];
    const reportId = reportIdRef.current?.value.trim();
    if (!file || !reportId) {
      alert("请填写 report_id（小写字母-数字）并选择 .docx/.pdf 文件");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("report_id", reportId);
    if (stage) fd.append("stage", stage);
    if (mineral) fd.append("mineral", mineral);
    upload.mutate(fd, {
      onSuccess: () => {
        if (fileRef.current) fileRef.current.value = "";
        if (reportIdRef.current) reportIdRef.current.value = "";
      },
      onError: (e) => alert(`上传失败: ${String(e)}`),
    });
  }

  const docs: GsbDocument[] = data?.items ?? [];

  return (
    <div className="space-y-4 p-6">
      <h1 className="text-xl font-semibold">样例文档库</h1>
      <div className="flex flex-wrap items-center gap-2">
        <input ref={reportIdRef} placeholder="report_id（如 2019-qianxi-gold-expl）"
               className="rounded border px-2 py-1 text-sm" />
        <input ref={fileRef} type="file" accept=".docx,.pdf" className="text-sm" />
        <button onClick={onUpload} disabled={upload.isPending}
                className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">上传</button>
        <span className="mx-2 h-5 w-px bg-gray-300" />
        <select value={stage} onChange={(e) => setStage(e.target.value)} className="rounded border px-2 py-1 text-sm">
          <option value="">全部阶段</option>
          <option value="survey">普查</option>
          <option value="detail">详查</option>
          <option value="exploration">勘探</option>
        </select>
        <select value={mineral} onChange={(e) => setMineral(e.target.value)} className="rounded border px-2 py-1 text-sm">
          <option value="">全部矿种</option>
          <option value="copper">铜</option>
          <option value="coal">煤</option>
          <option value="gold">金</option>
          <option value="iron">铁</option>
          <option value="lead_zinc">铅锌</option>
          <option value="other">其他</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border px-2 py-1 text-sm">
          <option value="">全部状态</option>
          {Object.entries(STATUS_ZH).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      {isLoading ? (
        <p className="text-sm text-gray-500">加载中…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2">report_id</th><th>文件</th><th>阶段</th><th>矿种</th>
              <th>状态</th><th>脱敏摘要</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id} className="border-b">
                <td className="py-2 font-mono text-xs">{d.report_id}</td>
                <td>{d.file_name}</td>
                <td>{d.stage}</td>
                <td>{d.mineral}</td>
                <td>{STATUS_ZH[d.status] ?? d.status}</td>
                <td className="max-w-48 truncate text-xs text-gray-500">{d.redaction_summary ?? "—"}</td>
                <td className="space-x-1">
                  {d.status === "uploaded" && (
                    <button onClick={() => action.mutate({ id: d.id, action: "parse" })}
                            className="rounded border px-2 py-0.5 text-xs">解析</button>
                  )}
                  {d.status === "parsed" && (
                    <button onClick={() => action.mutate({ id: d.id, action: "redact" })}
                            className="rounded border px-2 py-0.5 text-xs">脱敏</button>
                  )}
                  {d.status === "redacted" && (
                    <button onClick={() => router.push("/geo-samples/review")}
                            className="rounded border px-2 py-0.5 text-xs">抽审</button>
                  )}
                  {d.status === "failed" && (
                    <button onClick={() => action.mutate({ id: d.id, action: "parse" })}
                            className="rounded border px-2 py-0.5 text-xs text-red-600">重试</button>
                  )}
                </td>
              </tr>
            ))}
            {docs.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-gray-400">暂无样例</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 3: ReviewView**（选中文档 → 拉脱敏事件清单 → approve/reject）

```tsx
"use client";

// EAI-CUSTOM: geo-sample-bank Phase 1 ReviewView — 审「漏脱」看命中清单，不看全文。
import { useState } from "react";

import { useGsbDocuments, useGsbRedactions, useGsbReview } from "@/extensions/geo-samples/hooks";

export function ReviewView() {
  const [docId, setDocId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const { data } = useGsbDocuments({ status: "redacted" });
  const { data: reds } = useGsbRedactions(docId);
  const review = useGsbReview();
  const docs = data?.items ?? [];

  return (
    <div className="space-y-4 p-6">
      <h1 className="text-xl font-semibold">脱敏抽审</h1>
      <div className="flex gap-2">
        <select onChange={(e) => setDocId(e.target.value || null)} value={docId ?? ""}
                className="rounded border px-2 py-1 text-sm">
          <option value="">选择待审样例（{docs.length}）</option>
          {docs.map((d) => <option key={d.id} value={d.id}>{d.report_id}（{d.file_name}）</option>)}
        </select>
      </div>
      {docId && (
        <div className="space-y-3">
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left text-gray-500">
              <th className="py-1">规则</th><th>档位</th><th>位置</th><th>原文哈希（前12）</th>
            </tr></thead>
            <tbody>
              {(reds?.items ?? []).map((r) => (
                <tr key={r.id} className={r.mode === "review" ? "bg-amber-50" : ""}>
                  <td className="py-1">{r.rule}</td>
                  <td>{r.mode === "auto" ? "自动替换" : "待审标记"}</td>
                  <td className="font-mono text-xs">{r.start}–{r.end}</td>
                  <td className="font-mono text-xs">{r.original_hash.slice(0, 12)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
                    placeholder="审核备注（reject 时必填理由）" className="w-full rounded border p-2 text-sm" />
          <div className="flex gap-2">
            <button onClick={() => review.mutate({ id: docId, decision: "approve", note: note || null })}
                    className="rounded bg-green-600 px-3 py-1 text-sm text-white">通过（reviewed）</button>
            <button onClick={() => review.mutate({ id: docId, decision: "reject", note: note || "未写理由" })}
                    className="rounded bg-red-600 px-3 py-1 text-sm text-white">驳回（退回脱敏）</button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: TasksView**

```tsx
"use client";

// EAI-CUSTOM: geo-sample-bank Phase 1 TasksView.
import { useGsbRuns } from "@/extensions/geo-samples/hooks";

export function TasksView() {
  const { data } = useGsbRuns();
  const runs = data?.items ?? [];
  return (
    <div className="space-y-4 p-6">
      <h1 className="text-xl font-semibold">运行记录</h1>
      <table className="w-full text-sm">
        <thead><tr className="border-b text-left text-gray-500">
          <th className="py-1">类型</th><th>状态</th><th>文档</th><th>详情</th><th>时间</th>
        </tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className="border-b">
              <td className="py-1">{r.run_type}</td>
              <td className={r.status === "failed" ? "text-red-600" : r.status === "running" ? "text-amber-600" : "text-green-600"}>{r.status}</td>
              <td className="font-mono text-xs">{r.document_id?.slice(0, 8) ?? "—"}</td>
              <td className="max-w-72 truncate text-xs text-gray-500">{r.detail ?? "—"}</td>
              <td className="text-xs">{new Date(r.created_at).toLocaleString()}</td>
            </tr>
          ))}
          {runs.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-gray-400">暂无运行</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 5: 路由壳**（layout 的 navItems+canPage 模式镜像 `app/contract-price/layout.tsx:20-33`）

`frontend/src/app/geo-samples/layout.tsx`：

```tsx
"use client";

// EAI-CUSTOM: forked from app/contract-price/layout.tsx (geo-sample-bank Phase 1).
import { usePathname } from "next/navigation";
import Link from "next/link";

import { usePermission } from "@/extensions/roles";

const navItems = [
  { href: "/geo-samples", label: "样例文档库", pageId: "gsb:page:documents" },
  { href: "/geo-samples/review", label: "脱敏抽审", pageId: "gsb:page:review" },
  { href: "/geo-samples/tasks", label: "运行记录", pageId: "gsb:page:tasks" },
];

export default function GeoSamplesLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  const visible = isLoading ? navItems : navItems.filter((n) => canPage(n.pageId));
  return (
    <div className="min-h-screen">
      <nav className="flex gap-4 border-b px-6 py-3 text-sm">
        {visible.map((n) => (
          <Link key={n.href} href={n.href}
                className={pathname === n.href ? "font-semibold text-blue-600" : "text-gray-600"}>
            {n.label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
```

（若 `@/extensions/roles` 的 `usePermission` 导出路径与 contract-price layout 实际 import 不符，以 `app/contract-price/layout.tsx` 顶部真实 import 为准照抄同一路径。）

`frontend/src/app/geo-samples/page.tsx`：

```tsx
import { DocumentsView } from "@/extensions/geo-samples/components/DocumentsView";

export default function Page() {
  return <DocumentsView />;
}
```

`frontend/src/app/geo-samples/review/page.tsx`：

```tsx
import { ReviewView } from "@/extensions/geo-samples/components/ReviewView";

export default function Page() {
  return <ReviewView />;
}
```

`frontend/src/app/geo-samples/tasks/page.tsx`：

```tsx
import { TasksView } from "@/extensions/geo-samples/components/TasksView";

export default function Page() {
  return <TasksView />;
}
```

- [ ] **Step 6: 验证**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: 0 error（既有 warning 不计）

- [ ] **Step 7: Commit**

```bash
git add frontend/src/extensions/geo-samples/ frontend/src/app/geo-samples/
git commit -m "feat(geo-samples): three pages + route shell (documents/review/tasks, canPage nav)" -- frontend/src/extensions/geo-samples/ frontend/src/app/geo-samples/
```

---

### Task 12: 全量回归 + 容器重启冒烟

- [ ] **Step 1: 后端全量**

Run: `cd backend && make lint && make test`
Expected: lint 0 error；测试全绿（既有失败项以 main-dev-fork 基线为准，不新增失败）

- [ ] **Step 2: 前端全量**

Run: `cd frontend && pnpm typecheck && pnpm lint && pnpm test`
Expected: 0 error；测试全绿

- [ ] **Step 3: 容器重启 + API 冒烟**

```bash
docker compose -p eai-docker restart gateway frontend
sleep 20
docker compose -p eai-docker ps          # gateway/frontend 均 Up
docker compose -p eai-docker logs gateway --tail 30   # 无 geo_samples import 报错
# 浏览器登录（admin@eai-flow.com / Admin@2026）→ :2026/geo-samples → 三页可达、权限可见
# 注意：gateway 8001 未向 host 发布，探活走 docker logs 或 nginx 入口
```

Expected: gateway 健康；三页渲染、上传一个测试 docx 走通 uploaded→parsed→redacted→reviewed

- [ ] **Step 4: Commit（如容器验证有修补）**

```bash
git status --porcelain   # 确认无遗漏文件
# 如有修补，按前述 pathspec 模式提交
```

---

## Phase 1 完成判据（验收）

1. `make test` / `pnpm test` / typecheck / lint 全绿
2. 浏览器实测：1 份真实 docx 报告走完 uploaded→parsed→redacted→reviewed，ReviewView 命中清单可见且原文哈希不落明文
3. MinIO 控制台可见 `geo-samples` bucket 的 raw/work/clean 三层对象；**clean 的 source.md 中地质数值未被脱敏**
4. 权限验证：未授权角色不可见三页（permissions 四联动生效）

## 范围裁剪注记（相对 spec 的显式偏差）

- **预览 PNG 对照延后 Phase 2**：spec §3.2 ReviewView 含「预览 PNG 对照」，其数据源是 eai-flow-ocr 返回的 `preview_png_b64`，存储通道需要改动 `parsers.ocr_pdf_to_markdown` 返回签名并落 MinIO——Phase 1 抽审以「命中清单 + 原文哈希 + 计数摘要」闭环（审「漏脱」的目的已达成），预览对照随 Phase 2 分发一起落地。
- **批量上传（并发池）缩为单文件上传**：spec §3.2 DocumentsView 含「批量上传+并发池」（contract-price 同款），Phase 1 实现为单文件逐份上传——50 份验收走人工循环可达成；批量并发池随 Phase 2 批量入库一起落（届时一并处理终审 R2 连接占用 / R3 limit=50 计数上限）。
- **`POST /pipeline/compile` 不在本期**（spec §5 明确 Phase 2），TasksView 只展示 parse/redact 运行。

## Phase 2 预告（另立计划）

bank_compile 编译管线、depth_targets 多基线、resolve_targets 扩展、SKILL.md 契约升级、SL3 自动扩容、RAGFlow 切片分发与分块质量验收——以本计划产出的 reviewed 样例为输入。
