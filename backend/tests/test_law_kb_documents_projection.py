"""法规标准库文件列表投影测试(EAI-CUSTOM, spec 2026-09-05)。

法规系统库无 documents 表记录(法规导入只写 laws 表 + 直传 RAGFlow),
知识库详情的文件列表/ chunks 视图按 laws 实时投影。
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.law.service import (
    get_law_in_kb,
    is_law_kb_name,
    project_law_as_document,
    project_laws_as_documents,
)

KB_ID = uuid.uuid4()
DATASET_ID = "ds-laws-1"


def _law(synced="synced", dataset=DATASET_ID, number="GB 50160-2008", title="石油化工企业设计防火标准", sector="石化"):
    return SimpleNamespace(
        id=str(uuid.uuid4()),  # 真实 Law.id 是 str
        law_number=number,
        title=title,
        is_synced=synced,
        ragflow_dataset_id=dataset,
        ragflow_document_id="rf-doc-1" if synced == "synced" else None,
        metadata_json={"sector": sector},
        created_at=datetime(2026, 9, 1, 8, 0, 0),
    )


def test_is_law_kb_name():
    assert is_law_kb_name("法规标准库 — 标准/规范") is True
    assert is_law_kb_name("法规标准库 — 法律/法规/规章") is True
    assert is_law_kb_name("合同知识库") is False
    assert is_law_kb_name("") is False
    assert is_law_kb_name(None) is False


def test_project_law_as_document_field_mapping():
    law = _law()
    doc = project_law_as_document(law, KB_ID)
    assert doc.id == uuid.UUID(law.id)  # 真实 Law.id 为 str,覆盖 Pydantic str→UUID coercion
    assert doc.knowledge_base_id == KB_ID
    assert doc.name == "【石化】GB 50160-2008 石油化工企业设计防火标准"
    assert doc.file_path == ""
    assert doc.file_size == 0
    assert doc.file_type is None
    assert doc.ragflow_document_id == "rf-doc-1"
    assert doc.status == "success"
    assert doc.error_message is None
    assert doc.created_at == datetime(2026, 9, 1, 8, 0, 0)


def test_project_law_status_mapping():
    assert project_law_as_document(_law(synced="failed"), KB_ID).status == "failed"
    assert project_law_as_document(_law(synced="pending"), KB_ID).status == "pending"
    assert project_law_as_document(_law(synced=None), KB_ID).status == "pending"
    # 无行业前缀
    assert project_law_as_document(_law(sector=None), KB_ID).name == "GB 50160-2008 石油化工企业设计防火标准"


@pytest.mark.asyncio
async def test_project_laws_as_documents_query_and_total():
    laws = [_law(), _law(synced="pending")]
    count_rm = MagicMock()
    count_rm.scalar.return_value = 2
    rows_rm = MagicMock()
    rows_rm.scalars.return_value.all.return_value = laws
    db = AsyncMock()
    db.execute.side_effect = [count_rm, rows_rm]
    kb = SimpleNamespace(id=KB_ID, ragflow_dataset_id=DATASET_ID, name="法规标准库 — 标准/规范")

    docs, total = await project_laws_as_documents(db, kb, skip=0, limit=100)

    assert total == 2
    assert len(docs) == 2
    assert docs[0].ragflow_document_id == "rf-doc-1"
    assert docs[1].status == "pending"
    # 投影 SQL 必须按 dataset 过滤(count 与分页都带 where,分页另带排序)——
    # 去掉过滤会跨库泄漏;断言 where 子串(列清单里本就含 ragflow_dataset_id,裸列名没 discriminating power),
    # 大小写不敏感、不脆断全串
    count_sql = str(db.execute.await_args_list[0].args[0]).lower()
    page_sql = str(db.execute.await_args_list[1].args[0]).lower()
    assert "where laws.ragflow_dataset_id" in count_sql
    assert "where laws.ragflow_dataset_id" in page_sql
    assert "order by" in page_sql


@pytest.mark.asyncio
async def test_get_law_in_kb_matches_dataset():
    law = _law()
    rm = MagicMock()
    rm.scalar_one_or_none.return_value = law
    db = AsyncMock()
    db.execute.return_value = rm
    kb = SimpleNamespace(id=KB_ID, ragflow_dataset_id=DATASET_ID)

    assert await get_law_in_kb(db, kb, law.id) is law

    other = _law(dataset="ds-other")
    rm2 = MagicMock()
    rm2.scalar_one_or_none.return_value = other
    db.execute.return_value = rm2
    assert await get_law_in_kb(db, kb, other.id) is None

    rm3 = MagicMock()
    rm3.scalar_one_or_none.return_value = None
    db.execute.return_value = rm3
    assert await get_law_in_kb(db, kb, str(uuid.uuid4())) is None  # doc_id 为 str,同 Law.id String(36)
