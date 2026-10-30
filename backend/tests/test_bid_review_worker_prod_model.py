"""生产模型接线单测(worker._resolve_model_name/_default_model_fn/_default_extract_fn/_parse_json_object)。

接线前显式缺口(ModelNotConfigured/ExtractNotConfigured)的退化行为同锁——防接线回退静默假交付。
模型选择沿 translation worker 先例:EAI_BID_REVIEW_MODEL > config.yaml 首项。
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.extensions.bid_review import worker
from app.extensions.bid_review.engine.extract import ExtractNotConfigured


@pytest.fixture
def config_models(monkeypatch):
    """monkeypatch deerflow.config.get_app_config(worker 侧 call-time import);
    _set(*names) 重设可用模型清单,_set() = 空配置。"""
    monkeypatch.delenv("EAI_BID_REVIEW_MODEL", raising=False)

    def _set(*names):
        cfg = SimpleNamespace(models=[SimpleNamespace(name=n) for n in names])
        monkeypatch.setattr("deerflow.config.get_app_config", lambda: cfg)

    _set("m-first", "m-second")
    return _set


# ── _resolve_model_name ───────────────────────────────────────────────


def test_resolve_env_valid_wins(config_models, monkeypatch):
    monkeypatch.setenv("EAI_BID_REVIEW_MODEL", "m-second")
    assert worker._resolve_model_name() == "m-second"


def test_resolve_env_invalid_falls_to_first(config_models, monkeypatch):
    monkeypatch.setenv("EAI_BID_REVIEW_MODEL", "not-exist")
    assert worker._resolve_model_name() == "m-first"


def test_resolve_no_env_first(config_models):
    assert worker._resolve_model_name() == "m-first"


def test_resolve_no_models_none(config_models):
    config_models()
    assert worker._resolve_model_name() is None


# ── _default_model_fn(sem/hyb 裁决)───────────────────────────────────


def test_model_fn_wires_create_chat_model_and_awaits(config_models, monkeypatch):
    seen = {}

    class _Model:
        async def ainvoke(self, messages):
            seen["messages"] = messages
            return SimpleNamespace(content="ok")

    monkeypatch.setattr("deerflow.models.factory.create_chat_model", lambda name: (seen.setdefault("name", name), _Model())[1])
    fn = worker._default_model_fn()
    resp = asyncio.run(fn([{"role": "user", "content": "hi"}]))
    assert seen["name"] == "m-first" and seen["messages"][0]["content"] == "hi" and resp.content == "ok"


def test_model_fn_no_models_raises_not_configured(config_models):
    config_models()
    fn = worker._default_model_fn()
    with pytest.raises(worker.ModelNotConfigured):
        fn([{"role": "user", "content": "hi"}])


# ── _parse_json_object ────────────────────────────────────────────────


def test_parse_plain_and_fenced():
    assert worker._parse_json_object('{"a": 1}') == {"a": 1}
    assert worker._parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert worker._parse_json_object('前置杂文 {"a": {"b": 2}} 后置杂文') == {"a": {"b": 2}}


def test_parse_rejects_non_object_and_missing():
    with pytest.raises(ValueError):
        worker._parse_json_object("[1, 2]")
    with pytest.raises(ValueError):
        worker._parse_json_object("完全没有大括号")


# ── _default_extract_fn(基准提取)─────────────────────────────────────


def _fake_llm(contents):
    calls = {"n": 0}

    class _Model:
        def invoke(self, messages):
            calls["n"] += 1
            calls["prompt_has_path"] = "bid.total_price" in messages[0]["content"]
            return SimpleNamespace(content=contents[min(calls["n"], len(contents)) - 1])

    return _Model(), calls


def test_extract_fn_parses_fenced_json(config_models, monkeypatch):
    model, calls = _fake_llm(['```json\n{"bid.total_price": 990000.0}\n```'])
    monkeypatch.setattr("deerflow.models.factory.create_chat_model", lambda name: model)
    fn = worker._default_extract_fn()
    out = fn([{"doc_id": "d1", "text": "报价 99 万"}], ["bid.total_price"])
    # EAI-CUSTOM 2026-10-30 抽取 v2:_fn 返回 {"fields","provenance"} 新契约(分片 merge 产物)
    # EAI-CUSTOM 2026-10-31 二期:增 candidates/confidence 两键(模型未回 → 空映射)
    assert out == {"fields": {"bid.total_price": 990000.0}, "provenance": {}, "candidates": {}, "confidence": {}} and calls["n"] == 1 and calls["prompt_has_path"]


def test_extract_fn_retries_once_on_garbage(config_models, monkeypatch):
    model, calls = _fake_llm(["模型拒绝了指令性文字", '{"bid.total_price": 1}'])
    monkeypatch.setattr("deerflow.models.factory.create_chat_model", lambda name: model)
    fn = worker._default_extract_fn()
    assert fn([], ["bid.total_price"]) == {"fields": {"bid.total_price": 1}, "provenance": {}, "candidates": {}, "confidence": {}} and calls["n"] == 2


def test_extract_fn_double_garbage_raises(config_models, monkeypatch):
    model, calls = _fake_llm(["垃圾一", "垃圾二"])
    monkeypatch.setattr("deerflow.models.factory.create_chat_model", lambda name: model)
    fn = worker._default_extract_fn()
    with pytest.raises(RuntimeError, match="两试未获有效 JSON"):
        fn([], ["bid.total_price"])
    assert calls["n"] == 2  # 两试即止,不无限重试(infra 链管外层重投)


def test_extract_fn_no_models_raises_not_configured(config_models):
    config_models()
    fn = worker._default_extract_fn()
    with pytest.raises(ExtractNotConfigured):
        fn([], ["bid.total_price"])
