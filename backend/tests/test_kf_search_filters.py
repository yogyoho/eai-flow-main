"""kf_search_knowledge 的 filters 两段式过滤单测(FakeRF 直驱 handler)。"""

import json
from types import SimpleNamespace

import pytest

from app.extensions.knowledge_factory.mcp_server.tools import search_tools

COND = {
    "logic": "and",
    "conditions": [{"name": "sector", "comparison_operator": "is", "value": "环境评价"}],
}
KB_ROWS = [
    SimpleNamespace(name="法规标准库 — 标准/规范", ragflow_dataset_id="ds-std"),
    SimpleNamespace(name="法规标准库 — 法律", ragflow_dataset_id="ds-legal"),
]


class _StubResult:
    def scalars(self):
        return self

    def all(self):
        return KB_ROWS


class _StubDB:
    async def execute(self, stmt):
        return _StubResult()


class FakeRF:
    """RAGFlowClient 假件:记录 chat 调用,list_documents 返回预设 ids。"""

    def __init__(self, filtered_ids):
        self.filtered_ids = filtered_ids  # ds_id -> id 列表;未出现在字典里的库 = 过滤器不覆盖(整库)
        self.chat_calls = []

    async def list_documents(self, dataset_id, page=1, size=100, metadata_condition=None, orderby=None, desc=None):
        ids = self.filtered_ids.get(dataset_id, [])
        return {"data": {"docs": [{"id": i} for i in ids], "total": len(ids)}}

    async def chat(self, dataset_id, query, top_k=5, similarity_threshold=0.2, document_ids=None):
        self.chat_calls.append((dataset_id, document_ids))
        chunks = []
        for i, doc_id in enumerate(document_ids or ["fallback-doc"]):
            chunks.append(
                {
                    "content": f"chunk-{doc_id}-{i}",
                    "similarity": 0.9 - i * 0.1,
                    "dataset_id": dataset_id if isinstance(dataset_id, str) else "joint",
                    "document_keyword": f"doc-{str(doc_id)[:6]}",
                }
            )
        return {"code": 0, "data": {"chunks": chunks}}


@pytest.fixture
def fake_rf(monkeypatch):
    holder = {}

    def install(filtered_ids):
        rf = FakeRF(filtered_ids)
        monkeypatch.setattr("app.extensions.knowledge.client.RAGFlowClient", lambda: rf)
        holder["rf"] = rf
        return rf

    return install


@pytest.fixture
def run_db():
    """_run_in_db 假件:用 stub db 同步执行 loader。"""

    async def runner(fn):
        return await fn(_StubDB())

    return runner


def _parse(result):
    return json.loads(result[0].text)


@pytest.mark.asyncio
async def test_filters_route_per_kb_with_document_ids(fake_rf, run_db):
    rf = fake_rf({"ds-std": ["doc-a", "doc-b"], "ds-legal": []})
    result = _parse(await search_tools.handle_kf_search_knowledge({"query": "环境 影响", "filters": {"sector": "环境评价"}}, run_db))

    # ds-legal 零命中被跳过;ds-std 的检索带收敛后的 document_ids(合并后的 parser_config 语义锚点)
    assert all(ds == "ds-std" for ds, _ in rf.chat_calls)
    assert rf.chat_calls[0][1] == ["doc-a", "doc-b"]
    assert result["filters_applied"] == COND
    assert result["chunk_count"] == 2


@pytest.mark.asyncio
async def test_filters_unknown_key_returns_error(fake_rf, run_db):
    fake_rf({})
    result = _parse(await search_tools.handle_kf_search_knowledge({"query": "q", "filters": {"hacker": "x"}}, run_db))
    assert "unsupported filter key" in result["error"]


@pytest.mark.asyncio
async def test_no_filters_keeps_joint_call(fake_rf, run_db, monkeypatch):
    rf = fake_rf({})
    captured = {}

    async def joint_chat(dataset_id, query, **kwargs):
        captured["dataset_id"] = dataset_id
        return {"code": 0, "data": {"chunks": [{"content": "c", "similarity": 0.9, "dataset_id": dataset_id[0]}]}}

    monkeypatch.setattr(rf, "chat", joint_chat)
    result = _parse(await search_tools.handle_kf_search_knowledge({"query": "q"}, run_db))

    assert isinstance(captured["dataset_id"], list)  # 无过滤 = 联合调用一次
    assert result["filters_applied"] is None


@pytest.mark.asyncio
async def test_filters_zero_hit_everywhere_returns_empty_with_message(fake_rf, run_db):
    fake_rf({})
    result = _parse(await search_tools.handle_kf_search_knowledge({"query": "q", "filters": {"sector": "环境评价"}}, run_db))

    assert result["chunk_count"] == 0
    assert result["message"] == "过滤条件下无匹配文档"
    assert result["filters_applied"] == COND
