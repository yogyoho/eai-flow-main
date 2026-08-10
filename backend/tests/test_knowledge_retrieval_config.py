"""Tests for KnowledgeBase retrieval_config serialization & fallback (KB detail-tabs P1)."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.extensions.schemas import RETRIEVAL_CONFIG_DEFAULTS
from app.extensions.knowledge.service import KnowledgeBaseService


def _kb(**overrides):
    """Build a mock kb object carrying every attribute to_response reads.

    Defaults mirror RAGFlow/DB defaults; tests override retrieval_config as needed.
    The attribute set matches KnowledgeBaseService.to_response exactly (sync).
    Real UUID/datetime values are used so KnowledgeBaseResponse validation passes.
    """
    base = dict(
        id=uuid.uuid4(),
        name="Test KB",
        description="d",
        ragflow_dataset_id="ds-1",
        owner_id=uuid.uuid4(),
        owner=SimpleNamespace(username="owner"),
        access_type="private",
        kb_type="ragflow",
        allowed_depts=[],
        embedding_model="bge-large-zh",
        chunk_method="naive",
        parser_config={},
        retrieval_config=None,
        language="Chinese",
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    kb = MagicMock()
    for k, v in base.items():
        setattr(kb, k, v)
    return kb


def test_to_response_merges_defaults_when_unset():
    """retrieval_config unset (None) -> response carries full defaults."""
    resp = KnowledgeBaseService.to_response(_kb(retrieval_config=None))
    assert resp.retrieval_config == RETRIEVAL_CONFIG_DEFAULTS


def test_to_response_stored_overrides_defaults():
    """Stored partial config -> stored keys win, unset keys fall back to defaults."""
    resp = KnowledgeBaseService.to_response(_kb(retrieval_config={"top_k": 10}))
    assert resp.retrieval_config == {
        "top_k": 10,
        "similarity_threshold": RETRIEVAL_CONFIG_DEFAULTS["similarity_threshold"],
        "vector_similarity_weight": RETRIEVAL_CONFIG_DEFAULTS["vector_similarity_weight"],
    }


def test_resolve_chat_params_request_wins_over_kb_config():
    """请求显式传参 → 全部用请求值，KB 配置被忽略。"""
    params = KnowledgeBaseService.resolve_chat_params(
        8, 0.5, 0.7, {"top_k": 10, "similarity_threshold": 0.9, "vector_similarity_weight": 0.1}
    )
    assert params == {"top_k": 8, "similarity_threshold": 0.5, "vector_similarity_weight": 0.7}


def test_resolve_chat_params_partial_request_falls_back_per_field():
    """请求只传 top_k → top_k 用请求值；threshold/weight 逐字段回退到 KB 配置。"""
    params = KnowledgeBaseService.resolve_chat_params(
        8, None, None, {"top_k": 10, "similarity_threshold": 0.4, "vector_similarity_weight": 0.6}
    )
    assert params == {"top_k": 8, "similarity_threshold": 0.4, "vector_similarity_weight": 0.6}


def test_resolve_chat_params_all_unset_drops_to_empty():
    """请求和 KB 配置都没给 → 返回空 dict → RAGFlow 用数据集默认（None 永不传给 RAGFlow）。"""
    assert KnowledgeBaseService.resolve_chat_params(None, None, None, None) == {}
    # KB 有部分、请求全 None：KB 给的留下，KB 没给的丢弃
    assert KnowledgeBaseService.resolve_chat_params(None, None, None, {"top_k": 10}) == {"top_k": 10}
