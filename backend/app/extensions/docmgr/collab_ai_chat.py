"""AI chat endpoint for collaborative editor.

Proxies LLM chat/completions requests through the Gateway so that the
configured default_model (from Settings → default LLM) is used instead
of requiring a separate API key on the frontend.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.extensions.settings.service import SystemConfigService
from app.extensions.database import get_session_factory
from deerflow.config.app_config import get_app_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/collab", tags=["collab-ai"])

# ── helpers ────────────────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(nbsp|amp|lt|gt|quot);")


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _find_api_key(model_cfg: dict[str, Any]) -> str:
    """Resolve the api_key from a model config, supporting $ENV_VAR syntax."""
    raw = model_cfg.get("api_key", "") or model_cfg.get("openai_api_key", "")
    if isinstance(raw, str) and raw.startswith("$"):
        env_val = os.getenv(raw[1:])
        if env_val:
            return env_val
    return raw or ""


def _find_base_url(model_cfg: dict[str, Any]) -> str:
    raw = model_cfg.get("base_url", "") or model_cfg.get("openai_api_base", "")
    return raw or ""


# ── request / response ─────────────────────────────────────────────────────


class AiChatRequest(BaseModel):
    messages: list[dict[str, Any]]
    toolDefinitions: dict[str, Any] | None = None


# ── core logic ─────────────────────────────────────────────────────────────


async def _load_default_model() -> str | None:
    """Resolve the default model name from the system-config database row."""
    sf = get_session_factory()
    if sf is None:
        return None
    async with sf() as db:
        data = await SystemConfigService.get_all(db)
    return (data or {}).get("default_model") or None


def _build_system_prompt(has_tools: bool) -> str:
    if has_tools:
        return (
            "You are an AI writing assistant embedded in a block-based document editor.\n"
            "You MUST use the applyDocumentOperations tool to modify the document.\n"
            "Rules:\n"
            "- When asked to modify/translate/polish/expand/condense text, call applyDocumentOperations with update operations.\n"
            "- The `id` field in each operation MUST exactly match the block id from <selected-text>.\n"
            "- The `block` field MUST be a valid HTML element (e.g. <p>text</p> or <h2>text</h2>).\n"
            "- Do NOT output any explanatory text. Call the tool directly.\n"
            "- Always respond in the same language as the user's input."
        )
    return (
        "你是一个嵌入在文档编辑器中的AI写作助手。\n"
        "当用户要求修改文本时，只输出修改后的文本，不要任何解释或前缀。\n"
        "当用户要求头脑风暴时，输出清晰的列表。\n"
        "始终使用与用户输入相同的语言回复。"
    )


def _to_chat_messages(raw: list[dict[str, Any]], has_tools: bool) -> list[dict[str, Any]]:
    system_content = _build_system_prompt(has_tools)
    result: list[dict[str, Any]] = [{"role": "system", "content": system_content}]

    for i, msg in enumerate(raw):
        role = str(msg.get("role", "user"))
        if role == "developer":
            role = "system"
        if role not in ("system", "user", "assistant"):
            role = "user"

        content = ""
        if isinstance(msg.get("content"), str):
            content = msg["content"]
        elif isinstance(msg.get("parts"), list):
            content = "\n".join(
                str(p.get("text", ""))
                for p in msg["parts"]
                if isinstance(p, dict) and p.get("type") == "text"
            )
        elif msg.get("content"):
            content = json.dumps(msg["content"])

        # Inject selected block info into the last user message
        if role == "user" and i == len(raw) - 1:
            meta = msg.get("metadata") or {}
            doc_state = meta.get("documentState") or {}
            blocks = doc_state.get("selectedBlocks") or []
            if isinstance(blocks, list) and len(blocks) > 0:
                block_infos: list[str] = []
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    html = str(b.get("block", ""))
                    text = _strip_html(html)
                    block_infos.append(f"Block ID: {b.get('id')}\nHTML: {html}\nText: {text}")
                if block_infos:
                    content += "\n\nThe following blocks are selected in the document. Use their exact block IDs in the applyDocumentOperations tool:\n<selected-text>\n" + "\n\n".join(block_infos) + "\n</selected-text>"

        result.append({"role": role, "content": content})

    return result


def _to_openai_tools(tool_defs: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    if not tool_defs or not isinstance(tool_defs, dict):
        return None
    functions: list[dict[str, Any]] = []
    for name, defn in tool_defs.items():
        if not isinstance(defn, dict):
            continue
        schema = defn.get("inputSchema")
        if schema:
            functions.append({"type": "function", "function": {"name": name, "parameters": schema}})
    return functions or None


# ── SSE streaming helpers ──────────────────────────────────────────────────

async def _stream_text(upstream: httpx.Response) -> str:
    """Consume the upstream SSE stream and yield AI SDK UI text chunks.

    Returns the first content chunk so callers can detect empty responses.
    """
    async for line in upstream.aiter_lines():
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            continue
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            continue
        delta = (parsed.get("choices") or [{}])[0].get("delta") or {}
        if delta.get("content"):
            yield delta["content"]


async def _stream_tool_calls(upstream: httpx.Response) -> tuple[str, str, str]:
    """Consume the upstream SSE stream and collect the first tool call.

    Returns (tool_call_id, tool_name, tool_args_json).
    """
    tc_id = ""
    tc_name = ""
    tc_args = ""
    async for line in upstream.aiter_lines():
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            continue
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            continue
        delta = (parsed.get("choices") or [{}])[0].get("delta") or {}
        for tc in delta.get("tool_calls") or []:
            if tc.get("id"):
                tc_id = tc["id"]
            if tc.get("function", {}).get("name"):
                tc_name = tc["function"]["name"]
            if tc.get("function", {}).get("arguments"):
                tc_args += tc["function"]["arguments"]
    return tc_id, tc_name, tc_args


# ── endpoint ───────────────────────────────────────────────────────────────


@router.post("/ai-chat")
async def collab_ai_chat(request: Request, body: AiChatRequest):
    """Handle AI chat requests for the collaborative editor.

    Uses the system's configured default_model from Settings → Basic Settings.
    """
    model_name = await _load_default_model()
    if not model_name:
        raise HTTPException(status_code=400, detail="No default model configured. Please set a default LLM in Settings → Basic Settings.")

    app_config = get_app_config()
    model_cfg = app_config.get_model_config(model_name)
    if model_cfg is None:
        raise HTTPException(status_code=400, detail=f"Model '{model_name}' not found in config.yaml")

    # Convert Pydantic model to dict to access extra fields (api_key, base_url, etc.)
    cfg_dict = model_cfg.model_dump()

    api_key = _find_api_key(cfg_dict)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"Model '{model_name}' has no API key configured. Check config.yaml and environment variables.")

    base_url = _find_base_url(cfg_dict)
    if not base_url:
        # Some providers (e.g. langchain_deepseek) hardcode the base URL
        # in the SDK and omit it from config.yaml. Provide well-known defaults.
        provider = (cfg_dict.get("use") or "").lower()
        if "deepseek" in provider:
            base_url = "https://api.deepseek.com/v1"
        elif "zhipu" in provider or "glm" in provider:
            base_url = "https://open.bigmodel.cn/api/paas/v4"
        elif "siliconflow" in provider:
            base_url = "https://api.siliconflow.cn/v1"
        else:
            raise HTTPException(status_code=400, detail=f"Model '{model_name}' has no base_url configured and no default is known for provider: {cfg_dict.get('use', 'unknown')}")
    llm_model = cfg_dict.get("model", model_name)

    # Build the request to the LLM provider
    tools = _to_openai_tools(body.toolDefinitions)
    has_tools = tools is not None
    chat_messages = _to_chat_messages(body.messages, has_tools)

    llm_body: dict[str, Any] = {
        "model": llm_model,
        "messages": chat_messages,
        "stream": True,
    }
    if has_tools:
        llm_body["tools"] = tools
        llm_body["tool_choice"] = "auto"

    url = f"{base_url.rstrip('/')}/chat/completions"

    async def event_generator():
        text_id = f"txt-{id(request)}"
        emitted_ids: set[str] = set()

        def _sse(data: dict[str, Any]) -> str:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                async with client.stream(
                    "POST",
                    url,
                    json=llm_body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                ) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        logger.error("[collab-ai-chat] LLM error %s: %s", resp.status_code, error_text[:500])
                        yield _sse({"type": "start"})
                        yield _sse({"type": "finish"})
                        return

                    yield _sse({"type": "start"})

                    buffer = ""
                    tc_id = ""
                    tc_name = ""
                    tc_args = ""
                    text_yielded = False

                    async for chunk in resp.aiter_bytes():
                        buffer += chunk.decode("utf-8", errors="replace")
                        lines = buffer.split("\n")
                        buffer = lines.pop() or ""

                        for line in lines:
                            trimmed = line.strip()
                            if not trimmed or not trimmed.startswith("data: "):
                                continue
                            data = trimmed[6:]
                            if data == "[DONE]":
                                continue
                            try:
                                parsed = json.loads(data)
                            except json.JSONDecodeError:
                                continue

                            delta = (parsed.get("choices") or [{}])[0].get("delta") or {}

                            # Text content
                            if delta.get("content") and delta["content"] not in emitted_ids:
                                content = delta["content"]
                                if not text_yielded:
                                    yield _sse({"type": "text-start", "id": text_id})
                                    text_yielded = True
                                yield _sse({"type": "text-delta", "id": text_id, "delta": content})
                                emitted_ids.add(content)

                            # Tool calls
                            for tc in delta.get("tool_calls") or []:
                                if tc.get("id"):
                                    tc_id = tc["id"]
                                if tc.get("function", {}).get("name"):
                                    tc_name = tc["function"]["name"]
                                if tc.get("function", {}).get("arguments"):
                                    tc_args += tc["function"]["arguments"]

                    if text_yielded:
                        yield _sse({"type": "text-end", "id": text_id})

                    # Emit tool call
                    if tc_name and tc_args:
                        try:
                            parsed_args = json.loads(tc_args)
                        except json.JSONDecodeError:
                            parsed_args = {}

                        cid = tc_id or f"call_{text_id}"
                        yield _sse({"type": "tool-input-start", "toolCallId": cid, "toolName": tc_name})
                        yield _sse({"type": "tool-input-available", "toolCallId": cid, "toolName": tc_name, "input": parsed_args})

                    yield _sse({"type": "finish"})

        except Exception:
            logger.exception("[collab-ai-chat] stream error")
            yield _sse({"type": "start"})
            yield _sse({"type": "finish"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
