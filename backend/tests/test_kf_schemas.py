"""Unit tests for knowledge_factory Pydantic schemas.

Focus: ExtractionTaskCreate cross-field validation — at least one of
source_report_ids / uploaded_file_ids must be provided. Runs without
external services.
"""

import pytest
from pydantic import ValidationError

from app.extensions.knowledge_factory.schemas import ExtractionTaskCreate

# Stable fixture UUIDs (valid UUID4 format)
_DOC_ID = "00000000-0000-4000-8000-000000000001"
_FILE_ID = "00000000-0000-4000-8000-000000000002"


def _base(**overrides):
    payload = {
        "name": "模板抽取-2026-06-28-0000",
        "target_template_name": "煤炭_掘进作业规程_模板",
    }
    payload.update(overrides)
    return payload


def test_uploaded_file_ids_only_is_accepted():
    """B 模式（纯直接上传）：source_report_ids 为空、uploaded_file_ids 非空 → 合法。

    回归 bug-404：原 @field_validator('source_report_ids') 在校验该字段时，
    声明在其后的 uploaded_file_ids 尚未校验、不在 info.data，导致纯上传被误判
    为"两者皆空"而抛 '请提供 source_report_ids ... 或 uploaded_file_ids'。
    必须用 model_validator(after) 才能同时看到两个字段。
    """
    task = ExtractionTaskCreate(**_base(source_report_ids=[], uploaded_file_ids=[_FILE_ID]))
    assert task.uploaded_file_ids == [pytest.importorskip("uuid").UUID(_FILE_ID)]
    assert task.source_report_ids == []


def test_source_report_ids_only_is_accepted():
    """A 模式（知识库样例）：source_report_ids 非空、uploaded_file_ids 空 → 合法。"""
    task = ExtractionTaskCreate(**_base(source_report_ids=[_DOC_ID], uploaded_file_ids=[]))
    assert task.source_report_ids


def test_both_empty_is_rejected():
    """两者皆空 → 必须拒绝。"""
    with pytest.raises(ValidationError) as exc:
        ExtractionTaskCreate(**_base(source_report_ids=[], uploaded_file_ids=[]))
    assert "请提供 source_report_ids" in str(exc.value)


def test_both_provided_is_accepted():
    """两者都给 → 合法。"""
    task = ExtractionTaskCreate(
        **_base(source_report_ids=[_DOC_ID], uploaded_file_ids=[_FILE_ID])
    )
    assert task.source_report_ids and task.uploaded_file_ids
