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
