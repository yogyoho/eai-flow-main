"""Regression tests for the gateway collab AI chat endpoint (bug-3099).

`POST /api/collab/ai-chat` (app/extensions/docmgr/collab_ai_chat.py) proxies the
BlockNote editor AI toolbar traffic to the LLM configured in Settings → Basic
Settings (`default_model`). These tests lock the SSE translation contract with
fake upstreams — no real LLM and no DB access.
"""

import json
from types import SimpleNamespace

import pytest

from app.extensions.docmgr import collab_ai_chat as mod
from app.extensions.docmgr.collab_ai_chat import AiChatRequest, collab_ai_chat


def _sse_bytes(deltas: list[str]) -> bytes:
    """Encode OpenAI-style content deltas as upstream SSE frames + [DONE]."""
    frames = [
        "data: " + json.dumps({"choices": [{"delta": {"content": d}}]}) + "\n\n"
        for d in deltas
    ]
    frames.append("data: [DONE]\n\n")
    return "".join(frames).encode("utf-8")


class _FakeStreamResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self.status_code = 200
        self._chunks = chunks

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeStreamCtx:
    def __init__(self, resp: _FakeStreamResponse) -> None:
        self._resp = resp

    async def __aenter__(self) -> _FakeStreamResponse:
        return self._resp

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeAsyncClient:
    def __init__(self, resp: _FakeStreamResponse) -> None:
        self._resp = resp

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def stream(self, *args, **kwargs) -> _FakeStreamCtx:
        return _FakeStreamCtx(self._resp)


def _install_fakes(monkeypatch: pytest.MonkeyPatch, deltas: list[str]) -> None:
    async def fake_load_default_model():
        return "test-model"

    fake_cfg = SimpleNamespace(
        model_dump=lambda: {
            "use": "langchain_openai:ChatOpenAI",
            "model": "test-llm",
            "api_key": "sk-test",
            "base_url": "http://llm.test/v1",
        }
    )
    fake_app_config = SimpleNamespace(get_model_config=lambda name: fake_cfg)

    full = _sse_bytes(deltas)
    upstream = _FakeStreamResponse([full[:20], full[20:]])  # split mid-frame: exercises buffering

    monkeypatch.setattr(mod, "_load_default_model", fake_load_default_model)
    monkeypatch.setattr(mod, "get_app_config", lambda: fake_app_config)
    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient(upstream))


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: ") and line.strip() != "data: [DONE]":
            events.append(json.loads(line[6:]))
    return events


async def _collect(resp) -> str:
    text = ""
    async for chunk in resp.body_iterator:
        text += chunk
    return text


@pytest.mark.asyncio
async def test_repeated_identical_deltas_are_not_dropped(monkeypatch: pytest.MonkeyPatch):
    """bug-3099: the emitted_ids dedup dropped every repeated identical delta
    string (e.g. the token "。" streamed twice), silently corrupting the text.
    """
    deltas = ["你好", "你好", "你好"]
    _install_fakes(monkeypatch, deltas)

    resp = await collab_ai_chat(
        SimpleNamespace(),  # request is only used for id() in the endpoint
        AiChatRequest(messages=[{"role": "user", "content": "润色这段文字"}]),
    )
    events = _parse_sse(await _collect(resp))

    text_deltas = [e["delta"] for e in events if e.get("type") == "text-delta"]
    assert text_deltas == deltas


@pytest.mark.asyncio
async def test_stream_contract_start_and_finish_emitted(monkeypatch: pytest.MonkeyPatch):
    """The AI SDK UI message stream envelope: start … text-start/delta/end … finish."""
    _install_fakes(monkeypatch, ["润", "色"])

    resp = await collab_ai_chat(
        SimpleNamespace(),
        AiChatRequest(messages=[{"role": "user", "content": "润色"}]),
    )
    events = _parse_sse(await _collect(resp))

    types = [e.get("type") for e in events]
    assert types[0] == "start"
    assert types[-1] == "finish"
    assert "text-start" in types
    assert "text-end" in types
    text_id = next(e["id"] for e in events if e.get("type") == "text-start")
    assert all(e["id"] == text_id for e in events if e.get("type") == "text-delta")


@pytest.mark.asyncio
async def test_tool_call_streamed_as_tool_input_available(monkeypatch: pytest.MonkeyPatch):
    """Tool flow (润色 via applyDocumentOperations): tool frames must carry the
    parsed arguments even when text deltas are absent."""
    frame = (
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "applyDocumentOperations",
                                        "arguments": '{"operations":[{"id":"b1"}]}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )
        + "\n\ndata: [DONE]\n\n"
    ).encode("utf-8")

    async def fake_load_default_model():
        return "test-model"

    fake_cfg = SimpleNamespace(
        model_dump=lambda: {
            "use": "langchain_openai:ChatOpenAI",
            "model": "test-llm",
            "api_key": "sk-test",
            "base_url": "http://llm.test/v1",
        }
    )
    monkeypatch.setattr(mod, "_load_default_model", fake_load_default_model)
    monkeypatch.setattr(
        mod, "get_app_config", lambda: SimpleNamespace(get_model_config=lambda name: fake_cfg)
    )
    monkeypatch.setattr(
        mod.httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient(_FakeStreamResponse([frame]))
    )

    resp = await collab_ai_chat(
        SimpleNamespace(),
        AiChatRequest(
            messages=[{"role": "user", "content": "润色"}],
            toolDefinitions={
                "applyDocumentOperations": {"inputSchema": {"type": "object", "properties": {}}}
            },
        ),
    )
    events = _parse_sse(await _collect(resp))

    tool_events = [e for e in events if str(e.get("type", "")).startswith("tool-input")]
    assert [e["type"] for e in tool_events] == ["tool-input-start", "tool-input-available"]
    assert tool_events[0]["toolName"] == "applyDocumentOperations"
    assert tool_events[1]["input"] == {"operations": [{"id": "b1"}]}


def test_system_prompt_documents_suffixed_block_ids():
    """BlockNote's client validates operations in idsSuffixed mode: operation ids
    must carry a trailing `$` or applying the edit fails with
    "Invalid operation. id must end with $". The prompt must teach this."""
    from app.extensions.docmgr.collab_ai_chat import _build_system_prompt

    assert "trailing `$`" in _build_system_prompt(True)
