"""Translator LLM invocation contract: JSON mode + fallback."""

from types import SimpleNamespace

from app.extensions.translation.translator import _invoke_sync

_JSON = '{"block_id": "b1", "translation": "译文", "uncertain": false, "low_confidence_spans": []}'


class _JsonModel:
    def __init__(self) -> None:
        self.bound: dict | None = None
        self.calls = 0

    def bind(self, **kwargs):
        self.bound = kwargs
        return self

    def invoke(self, messages):
        self.calls += 1
        return SimpleNamespace(content=_JSON)


def test_invoke_requests_json_mode() -> None:
    model = _JsonModel()
    raw = _invoke_sync(model, [{"role": "user", "content": "x"}])
    assert model.bound == {"response_format": {"type": "json_object"}}
    assert model.calls == 1
    assert raw == _JSON


class _UnsupportedJsonModel:
    def __init__(self) -> None:
        self.calls = 0

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            raise ValueError("unsupported parameter: response_format")
        return SimpleNamespace(content=_JSON)


def test_invoke_falls_back_when_json_mode_unsupported() -> None:
    model = _UnsupportedJsonModel()
    raw = _invoke_sync(model, [])
    assert model.calls == 2
    assert raw == _JSON
