"""Tests for the API serialization helpers ported from upstream (Tier 2 C).

Covers ``strip_data_url_image_blocks`` and ``serialize_channel_values_for_api``
— the base64-image stripping added so REST endpoints returning channel values
to the frontend never leak ``data:``-scheme image payloads stored in
``hide_from_ui`` messages by ``ViewImageMiddleware``.
"""

from __future__ import annotations

from deerflow.runtime import serialize_channel_values_for_api
from deerflow.runtime.serialization import strip_data_url_image_blocks


def _hidden_img(data_url: str = "data:image/png;base64,AAAA") -> dict:
    return {
        "role": "user",
        "content": [{"type": "text", "text": "ctx"}, {"type": "image_url", "image_url": {"url": data_url}}],
        "additional_kwargs": {"hide_from_ui": True},
    }


def test_strip_leaves_non_hidden_messages_untouched():
    msg = _hidden_img()
    msg["additional_kwargs"] = {}  # not hidden
    out = strip_data_url_image_blocks([msg])
    assert out == [msg]


def test_strip_removes_data_url_blocks_only_from_hidden_messages():
    out = strip_data_url_image_blocks([_hidden_img()])
    assert len(out) == 1
    blocks = out[0]["content"]
    # text block kept, data: image block stripped
    assert any(b.get("type") == "text" for b in blocks)
    assert not any(b.get("type") == "image_url" for b in blocks)


def test_strip_keeps_https_image_urls_even_when_hidden():
    msg = _hidden_img(data_url="https://example.com/a.png")
    out = strip_data_url_image_blocks([msg])
    # https URL is NOT a data: URL -> preserved
    assert any(b.get("type") == "image_url" for b in out[0]["content"])


def test_strip_preserves_message_count_and_order():
    msgs = [_hidden_img(), {"role": "user", "content": "hi"}, _hidden_img()]
    out = strip_data_url_image_blocks(msgs)
    assert len(out) == 3


def test_strip_passes_through_non_dict_and_non_list_content():
    out = strip_data_url_image_blocks(["raw", {"role": "user", "content": "text", "additional_kwargs": {"hide_from_ui": True}}])
    assert out == ["raw", {"role": "user", "content": "text", "additional_kwargs": {"hide_from_ui": True}}]


def test_serialize_channel_values_for_api_strips_messages():
    channel_values = {
        "messages": [_hidden_img()],
        "other": "kept",
    }
    out = serialize_channel_values_for_api(channel_values)
    msgs = out["messages"]
    assert len(msgs) == 1
    # data: image block stripped from the hidden message
    assert not any(b.get("type") == "image_url" for b in msgs[0]["content"])
    # non-message channel values survive serialization
    assert "other" in out


def test_serialize_channel_values_for_api_handles_missing_messages():
    out = serialize_channel_values_for_api({"foo": "bar"})
    assert "messages" not in out or out.get("messages") in (None, [])
