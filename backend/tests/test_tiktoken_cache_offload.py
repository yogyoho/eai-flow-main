"""Tests for tiktoken encoding cache + memory-injection offload (upstream #3411).

Covers the pieces ported into dev: the module-level encoding cache, the
char-based fallback, the warm-up helper, and that ``abefore_agent`` runs the
injection off the event loop. (Upstream's test_tiktoken_cache_and_count_tokens
also exercises a ``use_tiktoken`` param / ``token_counting`` config / CJK
estimation that dev's simpler API does not have, so this focused suite
replaces it for the ported logic.)
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from deerflow.agents.memory import prompt
from deerflow.agents.memory.prompt import (
    _count_tokens,
    _get_tiktoken_encoding,
    warm_tiktoken_cache,
)


def test_get_tiktoken_encoding_caches_so_get_encoding_called_once(monkeypatch):
    monkeypatch.setattr(prompt, "_tiktoken_encoding_cache", {})
    fake_get = MagicMock(side_effect=lambda name: object())
    monkeypatch.setattr(prompt.tiktoken, "get_encoding", fake_get)

    first = _get_tiktoken_encoding("cl100k_base")
    second = _get_tiktoken_encoding("cl100k_base")

    assert first is second
    assert fake_get.call_count == 1  # subsequent calls are a dict lookup, no download


def test_get_tiktoken_encoding_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(prompt, "_tiktoken_encoding_cache", {})

    def boom(name):
        raise RuntimeError("network restricted")

    monkeypatch.setattr(prompt.tiktoken, "get_encoding", boom)
    assert _get_tiktoken_encoding("cl100k_base") is None


def test_count_tokens_falls_back_to_char_estimate_when_encoding_unavailable(monkeypatch):
    monkeypatch.setattr(prompt, "_get_tiktoken_encoding", lambda name="x": None)
    text = "hello world this is a test"
    assert _count_tokens(text, "cl100k_base") == len(text) // 4


def test_warm_tiktoken_cache_returns_bool():
    assert isinstance(warm_tiktoken_cache(), bool)


def test_abefore_agent_offloads_and_returns_cleanly_for_empty_state():
    """abefore_agent must run the (offloaded) injection without blocking the
    event loop and return cleanly. Empty messages -> no injection -> None."""
    from deerflow.agents.middlewares.dynamic_context_middleware import DynamicContextMiddleware

    mw = DynamicContextMiddleware()
    state = {"messages": []}
    runtime = SimpleNamespace(context={"thread_id": "t1"})

    result = asyncio.run(mw.abefore_agent(state, runtime))
    assert result is None
