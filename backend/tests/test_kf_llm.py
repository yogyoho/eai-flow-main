"""Regression test for bug-1243: KF extraction LLM client must bind a higher
output cap than the chat default (8192), else long template-tree JSON gets
truncated (finish_reason=length, no closing fence) and infer_schema falls back
to placeholder purposes."""

from app.extensions.knowledge_factory.llm import ExtractionLLMClient


class _FakeBound:
    """Stands in for the RunnableBinding returned by .bind(max_tokens=...)."""

    def __init__(self, inner, kwargs):
        self.inner = inner
        self.kwargs = kwargs


def test_model_binds_output_cap(monkeypatch):
    created = {}

    def _fake_create_chat_model(name=None, thinking_enabled=False):
        created["name"] = name

        class _Inner:
            def bind(self, **kwargs):
                return _FakeBound(self, kwargs)

        return _Inner()

    monkeypatch.setattr("app.extensions.knowledge_factory.llm.create_chat_model", _fake_create_chat_model)

    client = ExtractionLLMClient(model_name="any-model")
    bound = client.model
    assert isinstance(bound, _FakeBound)
    # 8192 (chat default) truncates a 159-section tree JSON mid-output —
    # the client must override it (see llm.py model property, bug-1243).
    assert bound.kwargs.get("max_tokens", 0) > 8192
    assert created["name"] == "any-model"
