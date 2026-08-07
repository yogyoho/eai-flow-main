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


# ── _LenientMeta list-field str coercion (bug-1122) ──

def test_formula_input_vars_str_coerced_to_list():
    """LLM 把 FormulaReference.input_vars 输出成单个 str 时，应包成 [str] 而非 500。

    回归 bug-1122：给排水计算书模板的 formula_references[].input_vars 是
    'Qe-蒸发水量(m³/h)...进、出水温差(℃)'（str），Pydantic 验证 list 失败
    → GET /api/kf/templates/{id} 500。_LenientMeta._scrub_llm_output 缺少
    list 字段的 str 转换。
    """
    from app.extensions.knowledge_factory.schemas import FormulaReference

    fr = FormulaReference(
        formula_id="F01",
        name="冷却塔补充水量",
        input_vars="Qe-蒸发水量(m³/h)...进、出水温差(℃)",  # LLM 输出 str
    )
    assert fr.input_vars == ["Qe-蒸发水量(m³/h)...进、出水温差(℃)"]


def test_formula_input_vars_list_dict_still_ok():
    """list[dict] / list[str] 正常输出不受影响。"""
    from app.extensions.knowledge_factory.schemas import FormulaReference

    fr1 = FormulaReference(formula_id="F1", input_vars=["Qe", "Qw"])
    assert fr1.input_vars == ["Qe", "Qw"]
    fr2 = FormulaReference(
        formula_id="F2", input_vars=[{"name": "Qe", "unit": "m³/h"}]
    )
    assert fr2.input_vars[0]["name"] == "Qe"
