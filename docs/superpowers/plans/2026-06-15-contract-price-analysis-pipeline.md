# 合同分项价格分析 — 数据流水线实现计划 (Plan 1/3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 RAGFlow 合同分项价格提取 → 聚类 → 统计 → Excel 导出的核心数据流水线(技能 scripts 层 + PostgreSQL 持久化),并产出可驱动的 CLI。

**Architecture:** 全部逻辑放在 `skills/custom/contract-price-analysis/scripts/` 下作为自包含 Python 包(遵循 spec 的"不碰主后端扩展"约束)。持久化用 PostgreSQL `postgres-ext`,表用 `cpa_` 前缀。聚类用 DBSCAN,特征 = 文本向量 ⊕ 技术参数向量。测试与代码同目录(skill 内 `tests/`)。

**Tech Stack:** Python 3.12、httpx、scikit-learn、xlsxwriter、SQLAlchemy[asyncio] + asyncpg、pytest

---

## 计划拆分说明(spec 含 3 个独立子系统)

| Plan | 范围 | 状态 |
|------|------|------|
| **Plan 1(本计划)** | 核心数据流水线:ragflow_client → parser → clustering → stats → excel → db → cli | 本次编写 |
| Plan 2 | 管理页面 API 服务(FastAPI server,读写 cpa_ 表,触发流水线) | 依赖 Plan 1,后续编写 |
| Plan 3 | 前端管理页面(6 功能区,Next.js) | 依赖 Plan 2,后续编写 |

Plan 1 产出可独立运行、可测试的 CLI,Plan 2/3 在其之上构建。

**关于 gitignore:**`skills/custom/` 被 gitignore。本计划的代码与测试都落在此目录,本地 TDD 可运行,但不会被项目 CI 跟踪。这是 spec 批准的"自包含技能"决策的已知权衡。

---

## 文件结构

```
skills/custom/contract-price-analysis/
├── SKILL.md                          # 技能定义(技能层,Plan 1 末尾写)
├── requirements.txt                  # Python 依赖
├── scripts/
│   ├── __init__.py
│   ├── config.py                     # 配置(从环境变量读)
│   ├── models.py                     # SQLAlchemy ORM 模型(cpa_ 表)
│   ├── db.py                         # 异步 DB 会话工厂
│   ├── ragflow_client.py             # RAGFlow API 客户端 + 增量比对
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── base.py                   # 解析器接口 + ParsedItem 数据类
│   │   ├── table_parser.py           # 表格模式解析
│   │   ├── list_parser.py            # 清单列表模式解析
│   │   └── mixed_parser.py           # 混合模式(表格优先,回退清单)
│   ├── clustering/
│   │   ├── __init__.py
│   │   ├── vectorizer.py             # 文本+技术参数向量化
│   │   └── engine.py                 # DBSCAN 聚类
│   ├── stats.py                      # 均值/最大/最小/中位数/标准差
│   ├── excel_generator.py            # 6-Sheet Excel + 图表
│   └── cli.py                        # 入口:手动/定时触发完整流水线
└── tests/
    ├── conftest.py                   # pytest fixtures(test DB)
    ├── test_ragflow_client.py
    ├── test_parser.py
    ├── test_vectorizer.py
    ├── test_clustering_engine.py
    ├── test_stats.py
    └── test_excel_generator.py
```

---

## Task 1: 技能包脚手架 + 依赖 + 配置

**Files:**
- Create: `skills/custom/contract-price-analysis/requirements.txt`
- Create: `skills/custom/contract-price-analysis/scripts/__init__.py`
- Create: `skills/custom/contract-price-analysis/scripts/config.py`
- Test: `skills/custom/contract-price-analysis/tests/test_config.py`

- [ ] **Step 1: 写失败的测试**

Create `tests/test_config.py`:
```python
import os

from scripts.config import get_config


def test_get_config_reads_env(monkeypatch):
    monkeypatch.setenv("RAGFLOW_API_KEY", "test-key-123")
    monkeypatch.setenv("RAGFLOW_BASE_URL", "http://example:9999/api/v1")
    monkeypatch.setenv("RAGFLOW_KB_ID", "kb-abc")
    cfg = get_config()
    assert cfg.ragflow_api_key == "test-key-123"
    assert cfg.ragflow_base_url == "http://example:9999/api/v1"
    assert cfg.ragflow_kb_id == "kb-abc"


def test_get_config_defaults(monkeypatch):
    monkeypatch.setenv("RAGFLOW_API_KEY", "k")
    monkeypatch.delenv("RAGFLOW_BASE_URL", raising=False)
    monkeypatch.delenv("RAGFLOW_KB_ID", raising=False)
    cfg = get_config()
    assert cfg.ragflow_base_url == "http://localhost:9380/api/v1"
    assert cfg.ragflow_kb_id == "a8e8f3dc660d11f1ad61e1631bd6f152"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd skills/custom/contract-price-analysis && PYTHONPATH=. python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: 写最小实现**

Create `scripts/__init__.py` (empty).

Create `scripts/config.py`:
```python
"""Configuration loaded from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    ragflow_api_key: str
    ragflow_base_url: str
    ragflow_kb_id: str
    database_url: str
    output_dir: str


def get_config() -> Config:
    return Config(
        ragflow_api_key=os.environ["RAGFLOW_API_KEY"],
        ragflow_base_url=os.environ.get(
            "RAGFLOW_BASE_URL", "http://localhost:9380/api/v1"
        ),
        ragflow_kb_id=os.environ.get(
            "RAGFLOW_KB_ID", "a8e8f3dc660d11f1ad61e1631bd6f152"
        ),
        database_url=os.environ.get(
            "CPA_DATABASE_URL",
            "postgresql+asyncpg://agentflow:agentflow123@postgres-ext:5432/agentflow",
        ),
        output_dir=os.environ.get(
            "CPA_OUTPUT_DIR", "/mnt/user-data/outputs/contract-price/"
        ),
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 创建 requirements.txt**

```
httpx>=0.27
scikit-learn>=1.4
xlsxwriter>=3.2
sqlalchemy[asyncio]>=2.0
asyncpg>=0.29
```

- [ ] **Step 6: 提交**

```bash
cd skills/custom/contract-price-analysis
git add -f requirements.txt scripts/__init__.py scripts/config.py tests/test_config.py
git commit -m "feat(cpa): scaffold skill package + config"
```

> Note: `skills/custom/` is gitignored, so use `git add -f` to force-track the new skill (or accept it stays local-only).

---

## Task 2: 数据库模型(cpa_ 表)与会话工厂

**Files:**
- Create: `skills/custom/contract-price-analysis/scripts/models.py`
- Create: `skills/custom/contract-price-analysis/scripts/db.py`
- Test: `skills/custom/contract-price-analysis/tests/test_db_models.py`

- [ ] **Step 1: 写失败的测试**

Create `tests/test_db_models.py`:
```python
import pytest
from sqlalchemy import select

from scripts.db import async_session, engine
from scripts.models import Base, CpaCluster, CpaDocument, CpaItem


@pytest.fixture
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_insert_document_and_item(setup_db, monkeypatch):
    monkeypatch.setenv(
        "CPA_DATABASE_URL", "postgresql+asyncpg://agentflow:agentflow123@postgres-ext:5432/agentflow"
    )
    async with async_session() as session:
        doc = CpaDocument(
            ragflow_doc_id="doc-1", doc_hash="h1", contract_no="C001",
            parse_mode="table", parse_status="parsed",
        )
        session.add(doc)
        await session.flush()
        item = CpaItem(
            document_id=doc.id, goods_name="高压开关柜",
            spec_model="KYN28", tech_params={"voltage_kv": 10},
            quantity=2, unit="台", unit_price=120000.00,
            source_contract_no="C001",
        )
        session.add(item)
        await session.commit()

    async with async_session() as session:
        result = await session.execute(select(CpaItem).where(CpaItem.goods_name == "高压开关柜"))
        fetched = result.scalar_one()
        assert fetched.unit_price == 120000.00
        assert fetched.tech_params["voltage_kv"] == 10
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=. python -m pytest tests/test_db_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.db'`

- [ ] **Step 3: 写最小实现**

Create `scripts/models.py`:
```python
"""SQLAlchemy ORM models for cpa_ tables (PostgreSQL postgres-ext)."""

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class CpaDocument(Base):
    __tablename__ = "cpa_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ragflow_doc_id: Mapped[str] = mapped_column(String(128), unique=True)
    doc_hash: Mapped[str] = mapped_column(String(128), index=True)
    contract_no: Mapped[Optional[str]] = mapped_column(String(100))
    supplier: Mapped[Optional[str]] = mapped_column(String(200))
    sign_date: Mapped[Optional[date]] = mapped_column()
    parse_mode: Mapped[str] = mapped_column(String(20))  # table/list/mixed
    parse_status: Mapped[str] = mapped_column(String(20))  # pending/parsed/failed
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    parsed_at: Mapped[Optional[datetime]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now, onupdate=utc_now
    )


class CpaItem(Base):
    __tablename__ = "cpa_items"
    __table_args__ = (
        Index("ix_cpa_items_cluster", "cluster_id"),
        Index("ix_cpa_items_contract", "source_contract_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cpa_documents.id"), nullable=False
    )
    goods_name: Mapped[str] = mapped_column(String(300))
    spec_model: Mapped[Optional[str]] = mapped_column(String(300))
    tech_params: Mapped[Optional[dict]] = mapped_column(JSONB)
    quantity: Mapped[Optional[float]] = mapped_column(Numeric(18, 3))
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 2))
    cluster_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cpa_clusters.id")
    )
    source_contract_no: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now)


class CpaCluster(Base):
    __tablename__ = "cpa_clusters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[str] = mapped_column(String(50))  # 设备/物资/配件/...
    representative_name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/confirmed/rejected
    stats: Mapped[Optional[dict]] = mapped_column(JSONB)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic lock
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now, onupdate=utc_now
    )


class CpaRunHistory(Base):
    __tablename__ = "cpa_run_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger_type: Mapped[str] = mapped_column(String(20))  # manual/scheduled
    scope: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))  # running/completed/failed
    docs_processed: Mapped[int] = mapped_column(Integer, default=0)
    items_extracted: Mapped[int] = mapped_column(Integer, default=0)
    clusters_formed: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    excel_path: Mapped[Optional[str]] = mapped_column(String(500))
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now)
    finished_at: Mapped[Optional[datetime]] = mapped_column()
```

Create `scripts/db.py`:
```python
"""Async DB engine + session factory for cpa_ tables."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from scripts.config import get_config

_engine = create_async_engine(get_config().database_url, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def init_schema() -> None:
    """Create cpa_ tables if they do not exist."""
    from scripts.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_db_models.py -v`
Expected: PASS (requires reachable postgres-ext; in Docker, run from gateway container or set `CPA_DATABASE_URL` to a reachable test DB)

> Note: This test needs a live PostgreSQL. In Docker dev, run via the gateway container: `docker compose -p eai-docker exec gateway python -m pytest <path>`. For pure unit testing without a DB, see Task 3 onward (those mock the DB).

- [ ] **Step 5: 提交**

```bash
git add -f scripts/models.py scripts/db.py tests/test_db_models.py
git commit -m "feat(cpa): add cpa_ ORM models + async session factory"
```

---

## Task 3: RAGFlow 客户端 + 增量比对

**Files:**
- Create: `skills/custom/contract-price-analysis/scripts/ragflow_client.py`
- Test: `skills/custom/contract-price-analysis/tests/test_ragflow_client.py`

- [ ] **Step 1: 写失败的测试**

Create `tests/test_ragflow_client.py`:
```python
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from scripts.ragflow_client import RagflowClient, list_documents


def _mock_response(status_code: int, json_data: dict) -> httpx.Response:
    request = httpx.Request("GET", "http://x")
    return httpx.Response(status_code, json=json_data, request=request)


@pytest.mark.asyncio
async def test_list_documents_returns_docs():
    payload = {
        "code": 0,
        "data": [
            {"id": "doc-a", "name": "合同1.pdf", "hash": "h1", "run": "DONE"},
            {"id": "doc-b", "name": "合同2.pdf", "hash": "h2", "run": "DONE"},
        ],
    }
    client = RagflowClient(base_url="http://x", api_key="k", kb_id="kb")
    with patch.object(client._http, "get", new=AsyncMock(return_value=_mock_response(200, payload))):
        docs = await client.list_documents()
    assert [d["id"] for d in docs] == ["doc-a", "doc-b"]


@pytest.mark.asyncio
async def test_filter_changed_documents():
    docs = [
        {"id": "doc-a", "name": "c1", "hash": "h1"},
        {"id": "doc-b", "name": "c2", "hash": "h2"},
        {"id": "doc-c", "name": "c3", "hash": "h3"},
    ]
    # doc-a already cached with same hash; doc-b cached with stale hash; doc-c new
    cached = {"doc-a": "h1", "doc-b": "h-old"}
    changed = RagflowClient.filter_changed(docs, cached)
    assert [d["id"] for d in changed] == ["doc-b", "doc-c"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=. python -m pytest tests/test_ragflow_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.ragflow_client'`

- [ ] **Step 3: 写最小实现**

Create `scripts/ragflow_client.py`:
```python
"""RAGFlow REST API client with incremental change detection."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RagflowClient:
    def __init__(self, base_url: str, api_key: str, kb_id: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.kb_id = kb_id
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def list_documents(self) -> list[dict[str, Any]]:
        """List all documents in the knowledge base. Returns raw doc dicts."""
        resp = await self._http.get(f"/datasets/{self.kb_id}/documents", params={"page": 1, "page_size": 1000})
        resp.raise_for_status()
        body = resp.json()
        # RAGFlow returns {"code":0,"data":[...]}
        if body.get("code") != 0:
            raise RuntimeError(f"RAGFlow error: {body}")
        return body.get("data", [])

    async def get_document_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        """Retrieve parsed chunks (text/tables) for a document."""
        resp = await self._http.get(
            f"/datasets/{self.kb_id}/documents/{doc_id}/chunks",
            params={"page": 1, "page_size": 1000},
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(f"RAGFlow error: {body}")
        return body.get("data", [])

    async def close(self) -> None:
        await self._http.aclose()

    @staticmethod
    def filter_changed(
        remote_docs: list[dict[str, Any]], cached_hashes: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Return only docs that are new or whose hash changed since last cache."""
        changed = []
        for doc in remote_docs:
            doc_id = doc["id"]
            new_hash = doc.get("hash")
            if cached_hashes.get(doc_id) != new_hash:
                changed.append(doc)
        return changed


async def list_documents(cfg) -> list[dict[str, Any]]:
    client = RagflowClient(cfg.ragflow_base_url, cfg.ragflow_api_key, cfg.ragflow_kb_id)
    try:
        return await client.list_documents()
    finally:
        await client.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_ragflow_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 提交**

```bash
git add -f scripts/ragflow_client.py tests/test_ragflow_client.py
git commit -m "feat(cpa): add RAGFlow client with incremental change detection"
```

---

## Task 4: 文档解析器(表格 / 清单 / 混合)

**Files:**
- Create: `skills/custom/contract-price-analysis/scripts/parser/__init__.py`
- Create: `skills/custom/contract-price-analysis/scripts/parser/base.py`
- Create: `skills/custom/contract-price-analysis/scripts/parser/table_parser.py`
- Create: `skills/custom/contract-price-analysis/scripts/parser/list_parser.py`
- Create: `skills/custom/contract-price-analysis/scripts/parser/mixed_parser.py`
- Test: `skills/custom/contract-price-analysis/tests/test_parser.py`

- [ ] **Step 1: 写失败的测试**

Create `tests/test_parser.py`:
```python
from scripts.parser import parse_chunks, ParsedItem
from scripts.parser.table_parser import TableParser
from scripts.parser.list_parser import ListParser


def test_table_parser_extracts_rows():
    # Simulated chunk content from RAGFlow (Markdown table)
    chunk = (
        "| 序号 | 货物名称 | 规格型号 | 技术参数 | 数量 | 单位 | 单价(元) |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | 高压开关柜 | KYN28-12 | 电压10kV 电流630A | 2 | 台 | 120000 |\n"
        "| 2 | 变压器 | SCB13 | 容量1000kVA | 1 | 台 | 85000 |"
    )
    parser = TableParser()
    items = parser.parse(chunk)
    assert len(items) == 2
    assert items[0].goods_name == "高压开关柜"
    assert items[0].unit_price == 120000.0
    assert items[0].tech_params["电压"] == "10kV"


def test_list_parser_extracts_lines():
    chunk = (
        "1. 高压开关柜 KYN28-12，电压10kV，数量2台，单价120000元\n"
        "2. 变压器 SCB13，容量1000kVA，数量1台，单价85000元"
    )
    parser = ListParser()
    items = parser.parse(chunk)
    assert len(items) == 2
    assert items[1].goods_name == "变压器"
    assert items[1].unit_price == 85000.0


def test_parse_chunks_dispatches_by_mode():
    table_chunk = "| 货物名称 | 单价 |\n|---|---|\n| 开关柜 | 100 |"
    items = parse_chunks([table_chunk], mode="table")
    assert len(items) == 1
    assert items[0].goods_name == "开关柜"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=. python -m pytest tests/test_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.parser'`

- [ ] **Step 3: 写最小实现**

Create `scripts/parser/__init__.py`:
```python
"""Document parsers for contract price line-items."""

import re
from dataclasses import dataclass, field
from typing import Optional

from scripts.parser.list_parser import ListParser
from scripts.parser.mixed_parser import MixedParser
from scripts.parser.table_parser import TableParser


@dataclass
class ParsedItem:
    goods_name: str
    spec_model: Optional[str] = None
    tech_params: dict = field(default_factory=dict)
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None


def _parse_price(text: str) -> Optional[float]:
    """Extract the first numeric price from a string like '120000' or '120000元'."""
    m = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    return float(m.group(1)) if m else None


_PARSERS = {"table": TableParser, "list": ListParser, "mixed": MixedParser}


def parse_chunks(chunks: list[str], mode: str = "table") -> list[ParsedItem]:
    parser_cls = _PARSERS.get(mode, TableParser)
    parser = parser_cls()
    items: list[ParsedItem] = []
    for chunk in chunks:
        items.extend(parser.parse(chunk))
    return items
```

Create `scripts/parser/base.py`:
```python
from abc import ABC, abstractmethod

from scripts.parser import ParsedItem


class BaseParser(ABC):
    @abstractmethod
    def parse(self, chunk: str) -> list[ParsedItem]:
        ...
```

Create `scripts/parser/table_parser.py`:
```python
import re

from scripts.parser import ParsedItem, _parse_price
from scripts.parser.base import BaseParser

_TECH_KV = re.compile(r"([电压电流容量功率频率压力温度]{1,4})\s*[:：]?\s*(\d+(?:\.\d+)?)\s*([a-zA-Zµμ²³/]*)")


class TableParser(BaseParser):
    def parse(self, chunk: str) -> list[ParsedItem]:
        items = []
        for line in chunk.splitlines():
            if not line.startswith("|") or "---" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2 or cells[0] in ("序号", "合计", "名称"):
                continue
            name = self._find_cell(cells, ["货物名称", "名称", "设备名称"])
            price = _parse_price(self._find_cell(cells, ["单价", "单价(元)", "价格"]) or "")
            if name and price:
                spec = self._find_cell(cells, ["规格型号", "规格", "型号"])
                tech = self._find_cell(cells, ["技术参数", "参数"])
                qty = self._parse_qty(self._find_cell(cells, ["数量"]) or "")
                unit = self._find_cell(cells, ["单位"])
                items.append(
                    ParsedItem(
                        goods_name=name, spec_model=spec,
                        tech_params=self._extract_tech(tech or spec or ""),
                        quantity=qty, unit=unit, unit_price=price,
                    )
                )
        return items

    @staticmethod
    def _find_cell(cells: list[str], candidates: list[str]) -> str:
        # Heuristic: match header position is complex; fall back to value cells.
        return ""

    @staticmethod
    def _parse_qty(text: str):
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(m.group(1)) if m else None

    @staticmethod
    def _extract_tech(text: str) -> dict:
        return {k: f"{v}{u}" for k, v, u in _TECH_KV.findall(text)}
```

> Note: The `_find_cell` heuristic above is a stub. Real header-position mapping is implemented in Step 4 after the test pinpoints exact cell indices. See refinement below.

- [ ] **Step 4: 完善表格解析器以通过测试**

Replace `TableParser` body's `_find_cell` and `parse` with a header-aware implementation:

```python
import re

from scripts.parser import ParsedItem, _parse_price
from scripts.parser.base import BaseParser

_TECH_KV = re.compile(r"([电压电流容量功率频率压力温度]{1,4})\s*[:：]?\s*(\d+(?:\.\d+)?)\s*([a-zA-Zµμ²³/]*)")
_HEADER_MAP = {
    "货物名称": "name", "名称": "name", "设备名称": "name",
    "规格型号": "spec", "规格": "spec", "型号": "spec",
    "技术参数": "tech", "参数": "tech",
    "数量": "qty", "单位": "unit",
    "单价": "price", "单价(元)": "price", "价格": "price",
}


class TableParser(BaseParser):
    def parse(self, chunk: str) -> list[ParsedItem]:
        lines = [l for l in chunk.splitlines() if l.startswith("|")]
        if not lines:
            return []
        header = [c.strip() for c in lines[0].strip("|").split("|")]
        col = {}
        for idx, h in enumerate(header):
            for key, role in _HEADER_MAP.items():
                if key in h and role not in col:
                    col[role] = idx
        items = []
        for line in lines[1:]:
            if "---" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            get = lambda r: cells[col[r]] if r in col and col[r] < len(cells) else ""
            name = get("name")
            price = _parse_price(get("price"))
            if not name or price is None:
                continue
            tech_text = get("tech") or get("spec") or ""
            items.append(
                ParsedItem(
                    goods_name=name, spec_model=get("spec") or None,
                    tech_params=self._extract_tech(tech_text),
                    quantity=self._parse_qty(get("qty")), unit=get("unit") or None,
                    unit_price=price,
                )
            )
        return items

    @staticmethod
    def _parse_qty(text: str):
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(m.group(1)) if m else None

    @staticmethod
    def _extract_tech(text: str) -> dict:
        return {k: f"{v}{u}" for k, v, u in _TECH_KV.findall(text)}
```

Create `scripts/parser/list_parser.py`:
```python
import re

from scripts.parser import ParsedItem, _parse_price
from scripts.parser.base import BaseParser

_LINE = re.compile(
    r"^\s*\d+[\.、)]\s*(?P<name>[^,，0-9]+?)\s*"
    r"(?P<spec>[A-Za-z0-9\-]+)?[，,]?\s*"
    r"(?P<rest>.*)$"
)
_TECH_KV = re.compile(r"([电压电流容量功率频率压力温度]{1,4})\s*[:：]?\s*(\d+(?:\.\d+)?)\s*([a-zA-Zµμ²³/]*)")
_QTY = re.compile(r"数量\s*[:：]?\s*(\d+(?:\.\d+)?)\s*([台套件个吨米块])?")
_PRICE = re.compile(r"单价\s*[:：]?\s*(\d+(?:[\.,]?\d+)*)\s*元")


class ListParser(BaseParser):
    def parse(self, chunk: str) -> list[ParsedItem]:
        items = []
        for line in chunk.splitlines():
            m = _LINE.match(line)
            if not m:
                continue
            name = m.group("name").strip()
            rest = m.group("rest") + (m.group("spec") or "")
            pm = _PRICE.search(rest)
            if not name or not pm:
                continue
            qm = _QTY.search(rest)
            items.append(
                ParsedItem(
                    goods_name=name,
                    spec_model=m.group("spec") or None,
                    tech_params={k: f"{v}{u}" for k, v, u in _TECH_KV.findall(rest)},
                    quantity=float(qm.group(1)) if qm else None,
                    unit=qm.group(2) if qm else None,
                    unit_price=float(pm.group(1).replace(",", "")),
                )
            )
        return items
```

Create `scripts/parser/mixed_parser.py`:
```python
from scripts.parser import ParsedItem
from scripts.parser.base import BaseParser
from scripts.parser.table_parser import TableParser
from scripts.parser.list_parser import ListParser


class MixedParser(BaseParser):
    """Tables first; if a chunk yields no table rows, try the list parser."""

    def __init__(self):
        self._table = TableParser()
        self._list = ListParser()

    def parse(self, chunk: str) -> list[ParsedItem]:
        table_items = self._table.parse(chunk)
        if table_items:
            return table_items
        return self._list.parse(chunk)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_parser.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 提交**

```bash
git add -f scripts/parser/ tests/test_parser.py
git commit -m "feat(cpa): add table/list/mixed document parsers"
```

---

## Task 5: 向量化器(文本 + 技术参数)

**Files:**
- Create: `skills/custom/contract-price-analysis/scripts/clustering/__init__.py`
- Create: `skills/custom/contract-price-analysis/scripts/clustering/vectorizer.py`
- Test: `skills/custom/contract-price-analysis/tests/test_vectorizer.py`

- [ ] **Step 1: 写失败的测试**

Create `tests/test_vectorizer.py`:
```python
import numpy as np

from scripts.clustering.vectorizer import Vectorizer


def test_same_name_different_params_have_different_vectors():
    v = Vectorizer()
    a = v.transform("高压开关柜", {"电压": "10kV", "电流": "630A"})
    b = v.transform("高压开关柜", {"电压": "35kV", "电流": "3150A"})
    assert not np.allclose(a, b)


def test_different_writings_of_same_goods_are_close():
    v = Vectorizer()
    a = v.transform("高压开关柜", {"电压": "10kV"})
    b = v.transform("10kV高压开关柜", {"电压": "10kV"})
    # TF-IDF cosine distance between the two text features should be small
    sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    assert sim > 0.5


def test_param_vector_standardizes_numeric_values():
    v = Vectorizer()
    vec = v.transform("变压器", {"容量": "1000kVA"})
    assert vec.shape[0] > 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=. python -m pytest tests/test_vectorizer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现**

Create `scripts/clustering/__init__.py` (empty).

Create `scripts/clustering/vectorizer.py`:
```python
"""Feature vectorizer: TF-IDF on goods name/spec + standardized tech params."""

import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

_NUM = re.compile(r"(\d+(?:\.\d+)?)")
_UNIT = re.compile(r"([a-zA-Zµμ²³/]+)")


class Vectorizer:
    def __init__(self):
        self._text = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))

    def fit(self, samples: list[tuple[str, dict]]) -> "Vectorizer":
        texts = [f"{name} {spec}" for name, spec in [(s[0], "") for s in samples]]
        self._text.fit(texts)
        self._param_keys = sorted({k for _, params in samples for k in params})
        return self

    def transform(self, goods_name: str, tech_params: dict) -> np.ndarray:
        text_vec = self._text.transform([goods_name]).toarray()[0]
        param_vec = np.array([self._numval(tech_params.get(k, "0")) for k in getattr(self, "_param_keys", [])])
        if param_vec.size:
            std = param_vec.std() + 1e-9
            param_vec = (param_vec - param_vec.mean()) / std
        return np.concatenate([text_vec, param_vec])

    @staticmethod
    def _numval(text: str) -> float:
        m = _NUM.search(str(text))
        return float(m.group(1)) if m else 0.0
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_vectorizer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add -f scripts/clustering/__init__.py scripts/clustering/vectorizer.py tests/test_vectorizer.py
git commit -m "feat(cpa): add text+param vectorizer"
```

---

## Task 6: DBSCAN 聚类引擎

**Files:**
- Create: `skills/custom/contract-price-analysis/scripts/clustering/engine.py`
- Test: `skills/custom/contract-price-analysis/tests/test_clustering_engine.py`

- [ ] **Step 1: 写失败的测试**

Create `tests/test_clustering_engine.py`:
```python
from scripts.clustering.engine import cluster_items, ClusterResult


def test_clusters_group_similar_goods():
    samples = [
        ("高压开关柜", {"电压": "10kV", "电流": "630A"}),
        ("10kV高压开关柜", {"电压": "10kV", "电流": "630A"}),
        ("变压器", {"容量": "1000kVA"}),
        ("电力变压器", {"容量": "1000kVA"}),
        ("特殊定制非标设备ABC", {"电压": "999kV"}),  # outlier
    ]
    result = cluster_items(samples, eps=0.6, min_samples=2)
    # Expect 2 clusters + 1 noise label (-1)
    non_noise = {r for r in result.labels if r != -1}
    assert len(non_noise) == 2
    assert -1 in result.labels  # outlier detected
    assert result.labels[0] == result.labels[1]  # the two 开关柜 together
    assert result.labels[2] == result.labels[3]  # the two 变压器 together


def test_noise_items_separated():
    samples = [("A设备", {}), ("B设备", {}), ("C设备", {})]
    result = cluster_items(samples, eps=0.3, min_samples=2)
    assert all(l == -1 for l in result.labels)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=. python -m pytest tests/test_clustering_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现**

Create `scripts/clustering/engine.py`:
```python
"""DBSCAN clustering over vectorized goods samples."""

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import normalize

from scripts.clustering.vectorizer import Vectorizer


@dataclass
class ClusterResult:
    labels: list[int]  # -1 == noise/outlier
    representatives: dict[int, str]  # cluster label -> representative name


def cluster_items(
    samples: list[tuple[str, dict]], eps: float = 0.6, min_samples: int = 2
) -> ClusterResult:
    vec = Vectorizer().fit(samples)
    matrix = np.array([vec.transform(name, params) for name, params in samples])
    if matrix.size == 0:
        return ClusterResult(labels=[], representatives={})
    normalized = normalize(matrix)
    db = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit(normalized)
    labels = db.labels_.tolist()
    reps: dict[int, str] = {}
    for label, (name, _) in zip(labels, samples):
        if label == -1:
            continue
        reps.setdefault(label, name)
    return ClusterResult(labels=labels, representatives=reps)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_clustering_engine.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 提交**

```bash
git add -f scripts/clustering/engine.py tests/test_clustering_engine.py
git commit -m "feat(cpa): add DBSCAN clustering engine"
```

---

## Task 7: 统计计算

**Files:**
- Create: `skills/custom/contract-price-analysis/scripts/stats.py`
- Test: `skills/custom/contract-price-analysis/tests/test_stats.py`

- [ ] **Step 1: 写失败的测试**

Create `tests/test_stats.py`:
```python
from scripts.stats import compute_stats


def test_compute_stats_basic():
    prices = [100.0, 200.0, 300.0, 400.0, 500.0]
    s = compute_stats(prices)
    assert s["count"] == 5
    assert s["mean"] == 300.0
    assert s["min"] == 100.0
    assert s["max"] == 500.0
    assert s["median"] == 300.0
    assert s["std"] > 0


def test_compute_stats_empty():
    s = compute_stats([])
    assert s["count"] == 0
    assert s["mean"] is None


def test_compute_stats_outlier_flag():
    prices = [100.0, 110.0, 105.0, 100000.0]
    s = compute_stats(prices)
    # 100000 is far beyond mean+3*std → flagged
    assert s["outlier_count"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=. python -m pytest tests/test_stats.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现**

Create `scripts/stats.py`:
```python
"""Aggregate statistics over a group of unit prices."""

import statistics
from typing import Optional


def compute_stats(prices: list[float]) -> dict:
    if not prices:
        return {"count": 0, "mean": None, "min": None, "max": None, "median": None, "std": None, "outlier_count": 0}
    mean = statistics.mean(prices)
    std = statistics.pstdev(prices) if len(prices) > 1 else 0.0
    threshold = mean + 3 * std
    outliers = sum(1 for p in prices if p > threshold)
    return {
        "count": len(prices),
        "mean": round(mean, 2),
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "median": round(statistics.median(prices), 2),
        "std": round(std, 2),
        "outlier_count": outliers,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_stats.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add -f scripts/stats.py tests/test_stats.py
git commit -m "feat(cpa): add price statistics computation"
```

---

## Task 8: Excel 生成器(6 Sheet + 图表)

**Files:**
- Create: `skills/custom/contract-price-analysis/scripts/excel_generator.py`
- Test: `skills/custom/contract-price-analysis/tests/test_excel_generator.py`

- [ ] **Step 1: 写失败的测试**

Create `tests/test_excel_generator.py`:
```python
import os

from scripts.excel_generator import generate_excel


def test_generate_excel_creates_workbook(tmp_path):
    groups = [
        {
            "name": "高压开关柜", "category": "设备",
            "stats": {"count": 3, "mean": 120000.0, "min": 100000.0, "max": 150000.0, "median": 120000.0, "std": 20000.0, "outlier_count": 0},
            "items": [
                {"goods_name": "高压开关柜", "spec_model": "KYN28", "unit_price": 100000.0, "source_contract_no": "C001", "sign_date": "2024-01-01", "supplier": "供应商A"},
                {"goods_name": "10kV高压开关柜", "spec_model": "KYN28", "unit_price": 150000.0, "source_contract_no": "C002", "sign_date": "2024-02-01", "supplier": "供应商B"},
            ],
        }
    ]
    out = tmp_path / "report.xlsx"
    path = generate_excel(groups, str(out))
    assert os.path.exists(path)
    assert path.endswith(".xlsx")


def test_generate_excel_has_six_sheets(tmp_path):
    import openpyxl

    groups = [
        {"name": "设备A", "category": "设备",
         "stats": {"count": 1, "mean": 100.0, "min": 100.0, "max": 100.0, "median": 100.0, "std": 0.0, "outlier_count": 0},
         "items": [{"goods_name": "设备A", "unit_price": 100.0, "source_contract_no": "C1", "sign_date": "2024-01-01", "supplier": "S1"}]},
    ]
    out = tmp_path / "r.xlsx"
    path = generate_excel(groups, str(out))
    wb = openpyxl.load_workbook(path)
    assert len(wb.sheetnames) >= 6
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=. python -m pytest tests/test_excel_generator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现**

Create `scripts/excel_generator.py`:
```python
"""Generate a 6-sheet Excel report with charts via xlsxwriter."""

import xlsxwriter


def generate_excel(groups: list[dict], output_path: str) -> str:
    workbook = xlsxwriter.Workbook(output_path)
    bold = workbook.add_format({"bold": True, "bg_color": "#F2F2F2", "border": 1})
    money = workbook.add_format({"num_format": "#,##0.00", "border": 1})
    text = workbook.add_format({"border": 1})
    outlier_fmt = workbook.add_format({"bg_color": "#FFC7CE", "border": 1})

    # Sheet 1: summary
    ws1 = workbook.add_worksheet("汇总总表")
    headers = ["类别", "代表名称", "样本数", "均值", "最大值", "最小值", "中位数", "标准差", "异常值数"]
    for c, h in enumerate(headers):
        ws1.write(0, c, h, bold)
    for r, g in enumerate(groups, start=1):
        s = g["stats"]
        ws1.write(r, 0, g["category"], text)
        ws1.write(r, 1, g["name"], text)
        ws1.write(r, 2, s["count"], text)
        for c, key in enumerate(["mean", "max", "min", "median", "std"], start=3):
            ws1.write_number(r, c, s.get(key) or 0, money)
        ws1.write(r, 8, s["outlier_count"], text)
    ws1.freeze_panes(1, 2)

    # Sheet 2: line items
    ws2 = workbook.add_worksheet("分项明细")
    item_headers = ["货物名称", "规格型号", "技术参数", "单价", "来源合同", "签订日期", "供应商"]
    for c, h in enumerate(item_headers):
        ws2.write(0, c, h, bold)
    row = 1
    for g in groups:
        for it in g["items"]:
            fmt = outlier_fmt if it.get("is_outlier") else text
            ws2.write(row, 0, it["goods_name"], text)
            ws2.write(row, 1, it.get("spec_model", ""), text)
            ws2.write(row, 2, str(it.get("tech_params", "")), text)
            ws2.write_number(row, 3, it["unit_price"], money)
            ws2.write(row, 4, it.get("source_contract_no", ""), text)
            ws2.write(row, 5, it.get("sign_date", ""), text)
            ws2.write(row, 6, it.get("supplier", ""), text)
            row += 1
    ws2.freeze_panes(1, 0)

    # Sheets 3-6: charts (one chart type per sheet)
    _add_chart_sheet(workbook, "图表-价格分布", groups, "boxstock")
    _add_chart_sheet(workbook, "图表-价格趋势", groups, "line")
    _add_chart_sheet(workbook, "图表-供应商对比", groups, "column")
    _add_chart_sheet(workbook, "图表-区间分布", groups, "scatter")

    workbook.close()
    return output_path


def _add_chart_sheet(workbook, name, groups, chart_type):
    ws = workbook.add_worksheet(name)
    # write a small data table the chart reads from, then the chart
    ws.write(0, 0, "组", workbook.add_format({"bold": True}))
    ws.write(0, 1, "均值", workbook.add_format({"bold": True}))
    for r, g in enumerate(groups, start=1):
        ws.write(r, 0, g["name"])
        ws.write_number(r, 1, g["stats"]["mean"] or 0)
    chart = workbook.add_chart({"type": chart_type if chart_type != "boxstock" else "column"})
    chart.add_series({
        "name": name,
        "categories": [name, 1, 0, len(groups), 0],
        "values": [name, 1, 1, len(groups), 1],
    })
    chart.set_title({"name": name})
    ws.insert_chart("D2", chart)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_excel_generator.py -v`
Expected: PASS (2 passed). Add `openpyxl` to `requirements.txt` if the second test needs it.

- [ ] **Step 5: 提交**

```bash
git add -f scripts/excel_generator.py tests/test_excel_generator.py requirements.txt
git commit -m "feat(cpa): add 6-sheet Excel generator with charts"
```

---

## Task 9: CLI 流水线编排(端到端)

**Files:**
- Create: `skills/custom/contract-price-analysis/scripts/cli.py`
- Test: `skills/custom/contract-price-analysis/tests/test_cli.py`

- [ ] **Step 1: 写失败的测试**

Create `tests/test_cli.py`:
```python
from unittest.mock import AsyncMock, patch

import pytest

from scripts.cli import run_pipeline


@pytest.mark.asyncio
async def test_run_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("RAGFLOW_API_KEY", "k")
    monkeypatch.setenv("CPA_OUTPUT_DIR", str(tmp_path))

    fake_docs = [{"id": "d1", "name": "合同1.pdf", "hash": "h1"}]
    fake_chunks = [
        "| 序号 | 货物名称 | 规格型号 | 数量 | 单位 | 单价 |\n|---|---|---|---|---|---|\n| 1 | 高压开关柜 | KYN28 | 2 | 台 | 120000 |"
    ]

    with patch("scripts.cli.RagflowClient") as MockClient, \
         patch("scripts.cli.init_schema", new=AsyncMock()):
        instance = MockClient.return_value
        instance.list_documents = AsyncMock(return_value=fake_docs)
        instance.get_document_chunks = AsyncMock(return_value=fake_chunks)
        instance.filter_changed = AsyncMock(return_value=fake_docs)
        instance.close = AsyncMock()
        # DB writes mocked out (no live DB in unit test)
        with patch("scripts.cli._persist", new=AsyncMock(return_value=([], []))) as persist_mock:
            groups = await run_pipeline(mode="table", trigger="manual")

    assert isinstance(groups, list)
    assert persist_mock.await_count >= 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=. python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现**

Create `scripts/cli.py`:
```python
"""End-to-end pipeline orchestration: pull → parse → cluster → stats → excel."""

import logging
from typing import Any

from scripts.config import get_config
from scripts.db import init_schema
from scripts.excel_generator import generate_excel
from scripts.parser import parse_chunks
from scripts.ragflow_client import RagflowClient
from scripts.clustering.engine import cluster_items
from scripts.stats import compute_stats

logger = logging.getLogger(__name__)


async def _persist(documents, items_clusters):
    """Persist documents + items + clusters to cpa_ tables.

    Returns (groups_for_excel, run_summary). Implementation uses async_session.
    """
    from scripts.db import async_session
    from scripts.models import CpaCluster, CpaDocument, CpaItem

    groups: list[dict[str, Any]] = []
    async with async_session() as session:
        for doc in documents:
            session.add(CpaDocument(**{k: doc[k] for k in doc if k in CpaDocument.__table__.columns}))
        # (full persistence of items/clusters omitted for brevity in this step;
        #  filled in from parse + cluster results)
        await session.commit()
    return groups, {}


async def run_pipeline(mode: str = "table", trigger: str = "manual") -> list[dict[str, Any]]:
    cfg = get_config()
    await init_schema()
    client = RagflowClient(cfg.ragflow_base_url, cfg.ragflow_api_key, cfg.ragflow_kb_id)
    try:
        docs = await client.list_documents()
        changed = client.filter_changed(docs, cached_hashes={})  # TODO(Task10): load from DB
        all_items: list[tuple[str, dict, float]] = []
        for doc in changed:
            try:
                chunks = await client.get_document_chunks(doc["id"])
                texts = [c.get("content_with_weight", c.get("content", "")) for c in chunks]
                parsed = parse_chunks(texts, mode=mode)
                for p in parsed:
                    all_items.append((p.goods_name, p.tech_params, p.unit_price or 0.0))
            except Exception as e:
                logger.warning("Failed to parse doc %s: %s", doc.get("id"), e)
    finally:
        await client.close()

    # Cluster
    samples = [(name, params) for name, params, _ in all_items]
    result = cluster_items(samples)

    # Group + stats
    groups: list[dict[str, Any]] = []
    for label in sorted(l for l in set(result.labels) if l != -1):
        idxs = [i for i, l in enumerate(result.labels) if l == label]
        prices = [all_items[i][2] for i in idxs]
        groups.append({
            "name": result.representatives[label],
            "category": "未分类",
            "stats": compute_stats(prices),
            "items": [{"goods_name": all_items[i][0], "unit_price": all_items[i][2]} for i in idxs],
        })

    await _persist(changed, result)

    import os
    out_path = os.path.join(cfg.output_dir, f"contract-price-{trigger}.xlsx")
    os.makedirs(cfg.output_dir, exist_ok=True)
    generate_excel(groups, out_path)
    logger.info("Excel written to %s", out_path)
    return groups


def main():
    import asyncio
    import argparse

    parser = argparse.ArgumentParser(description="Contract price analysis pipeline")
    parser.add_argument("--mode", choices=["table", "list", "mixed"], default="table")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    args = parser.parse_args()
    asyncio.run(run_pipeline(mode=args.mode, trigger=args.trigger))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `PYTHONPATH=. python -m pytest tests/test_cli.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 提交**

```bash
git add -f scripts/cli.py tests/test_cli.py
git commit -m "feat(cpa): add end-to-end CLI pipeline orchestration"
```

---

## Task 10: 技能定义(SKILL.md)+ 文档 + 整体冒烟

**Files:**
- Create: `skills/custom/contract-price-analysis/SKILL.md`
- Create: `skills/custom/contract-price-analysis/README.md`

- [ ] **Step 1: 写 SKILL.md**

Create `SKILL.md`:
```markdown
---
name: contract-price-analysis
description: |
  当用户需要从 RAGFlow 合同知识库中提取分项价格、对同类货物（设备/物资/配件）按
  名称+技术参数聚类归并、计算单价均值/最大/最小值并导出带图表的 Excel 报告时使用此技能。
  触发场景：用户提及"合同价格分析""分项价格汇总""货物单价对比""采购价格统计"
  "合同分项提取""聚类分析价格"等关键词；或需要批量统计合同中同类货物价格时。
  支持手动触发和定时增量更新。
---

# 合同分项价格分析技能

## ⛏️ 关键规则

1. 本技能通过 `scripts/cli.py` 执行数据流水线，产出 Excel 报告到 `/mnt/user-data/outputs/contract-price/`。
2. 解析模式（表格/清单/混合）由用户在调用时指定，默认 `table`。
3. 聚类基于"货物名称 + 技术参数"双维度，使用 DBSCAN 自动归并同类货物。
4. 自动聚类结果需用户在管理页面（`/contract-price/clusters`）审核后统计才生效。
5. 缓存与持久化使用 PostgreSQL `postgres-ext`，表前缀 `cpa_`。

## 工作流

### 步骤1：确认参数
- 解析模式（表格/清单/混合）
- 触发方式（手动/定时）
- 分析范围（全部合同/指定时间段/指定项目）

### 步骤2：执行流水线
运行：`python -m scripts.cli --mode <table|list|mixed> --trigger <manual|scheduled>`

### 步骤3：报告结果
向用户报告：处理合同数、提取分项数、聚类组数、待审核组数、Excel 路径。

## 依赖
- 环境变量：`RAGFLOW_API_KEY`、`RAGFLOW_BASE_URL`、`RAGFLOW_KB_ID`、`CPA_DATABASE_URL`
- Python 包：见 `requirements.txt`
- 数据库：PostgreSQL `postgres-ext`

## 参考文档
- 设计文档：`docs/superpowers/specs/2026-06-15-contract-price-analysis-design.md`
- 实现计划：`docs/superpowers/plans/2026-06-15-contract-price-analysis-pipeline.md`
```

- [ ] **Step 2: 写 README.md**

Create `README.md`:
```markdown
# 合同分项价格分析技能

从 RAGFlow 合同知识库提取分项价格，按名称+技术参数聚类，计算单价统计量，导出 Excel。

## 快速开始

```bash
cd skills/custom/contract-price-analysis
pip install -r requirements.txt
export RAGFLOW_API_KEY=<your-key>
python -m scripts.cli --mode table --trigger manual
```

## 测试

```bash
PYTHONPATH=. python -m pytest tests/ -v
```

## 流水线阶段

1. **拉取增量** — RAGFlow API + doc_hash 比对
2. **解析分项** — table/list/mixed 三模式
3. **向量化** — 文本 TF-IDF ⊕ 技术参数标准化
4. **聚类** — DBSCAN
5. **统计** — 均值/最大/最小/中位数/标准差/异常值
6. **导出** — 6-Sheet Excel + 图表

## 架构
见 `docs/superpowers/specs/2026-06-15-contract-price-analysis-design.md`。
```

- [ ] **Step 3: 运行全部测试（冒烟）**

Run: `PYTHONPATH=. python -m pytest tests/ -v`
Expected: All tests PASS (config, ragflow_client, parser, vectorizer, clustering, stats, excel, cli). DB-integration test (Task 2) requires a live PostgreSQL — skip with `-k "not test_db"` if no DB available.

- [ ] **Step 4: 提交**

```bash
git add -f SKILL.md README.md
git commit -m "feat(cpa): add skill definition + README"
```

---

## Self-Review(计划自检)

**1. Spec 覆盖(Plan 1 范围)**

| Spec 要求 | 覆盖任务 |
|-----------|----------|
| ragflow_client + 增量比对 | Task 3 ✅ |
| parser(table/list/mixed) | Task 4 ✅ |
| 向量化(文本+参数) | Task 5 ✅ |
| DBSCAN 聚类 | Task 6 ✅ |
| 统计(均值/最大/最小/中位数/标准差/异常值) | Task 7 ✅ |
| Excel 6-Sheet + 图表 | Task 8 ✅ |
| cpa_ 表(PostgreSQL) | Task 2 ✅ |
| CLI 流水线编排 | Task 9 ✅ |
| 配置(环境变量) | Task 1 ✅ |
| SKILL.md 技能定义 | Task 10 ✅ |

**未在 Plan 1 覆盖(留给 Plan 2/3)**:
- 管理页面 API 服务(FastAPI server)→ Plan 2
- 前端 6 页面 → Plan 3
- 定时任务调度器实现(Plan 1 CLI 接受 `--trigger scheduled`,实际调度器部署在 Plan 2 或 docker-compose)
- `_persist` 的完整实现(Plan 1 Task 9 是骨架,Plan 2 补全聚类持久化与增量 hash 加载)
- 用户审核分组的状态机(`pending`/`confirmed`)→ Plan 2 API

**2. Placeholder 扫描**
- Task 9 `_persist` 标注"骨架,Plan 2 补全" — 已明确边界,非模糊占位
- Task 9 `filter_changed(cached_hashes={})` 的 TODO(Task10) — 已标注增量 hash 加载留待 Plan 2
- 无 "TBD"/"implement later"/"add error handling" 等违规占位

**3. 类型/命名一致性**
- `ParsedItem`(Task 4)字段 `goods_name/spec_model/tech_params/quantity/unit/unit_price` 在 Task 9 CLI 中引用一致 ✅
- `cluster_items` 返回 `ClusterResult(labels, representatives)`(Task 6),CLI(Task 9)使用 `.labels`/`.representatives` 一致 ✅
- `compute_stats`(Task 7)返回 dict 键 `count/mean/min/max/median/std/outlier_count`,Excel 生成器(Task 8)与 CLI(Task 9)引用一致 ✅
- `generate_excel(groups, output_path)` 签名一致 ✅

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-15-contract-price-analysis-pipeline.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派发独立 subagent,任务间评审,快速迭代

**2. Inline Execution** — 在当前会话按任务批量执行,带检查点

**Which approach?**
