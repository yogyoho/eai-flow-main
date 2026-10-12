"""LLM translation glue (EAI-CUSTOM, T4).

模型经平台 config.yaml models 段声明（构件 2：换模型=改配置不改代码）——
``EAI_TRANSLATION_MODEL`` env 指定 models 列表中的名字，缺省取第一个。
输出协议=JSON（块 id、译文、不确定标记、低置信片段列表）——构件 2（用户要点）。
同步 invoke 走 asyncio.to_thread（D16：不许进事件循环）。
"""

import asyncio
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class TranslateProtocolError(Exception):
    """LLM 输出不符合 JSON 协议（重生成；重试尽 → exceeded 人工队列）。"""


def resolve_model_name() -> str | None:
    """EAI_TRANSLATION_MODEL env 指定 config.yaml models[] 中的名字；未设→None（工厂默认第一个）。"""
    return os.environ.get("EAI_TRANSLATION_MODEL") or None


def build_messages(block_id: str, text: str, source_lang: str, glossary_prompt: str) -> list[dict]:
    lang_name = {"en": "英语", "fr": "法语"}.get(source_lang, "原文语言")
    system = (
        "你是矿业/财务/工程领域的专业文档译者。把给定文本块忠实翻译为简体中文。\n"
        "硬规则：\n"
        "1) 文中 ⟦#N⟧ 形式的占位符是数字令牌，必须原样保留，不得增删改位。\n"
        "2) 不得添加解释、注释或原文没有的内容（忠实度优先）。\n"
        "3) 只输出一个 JSON 对象，不要输出任何其他文字：\n"
        '   {"block_id": "<原样返回>", "translation": "<译文>", "uncertain": <bool>, "low_confidence_spans": ["<不确定的原文片段>", ...]}\n'
    )
    if glossary_prompt:
        system += f"4) {glossary_prompt}\n"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"block_id={block_id}\n源语言={lang_name}\n文本：\n{text}"},
    ]


def parse_translation_response(raw: str, block_id: str) -> dict:
    """容错解析 LLM JSON 输出；协议不符抛 TranslateProtocolError。"""
    text = raw.strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise TranslateProtocolError(f"response is not JSON: {e}") from e
    if not isinstance(data, dict) or "translation" not in data:
        raise TranslateProtocolError("response JSON missing 'translation' field")
    return {
        "block_id": data.get("block_id", block_id),
        "translation": str(data.get("translation", "")),
        "uncertain": bool(data.get("uncertain", False)),
        "low_confidence_spans": list(data.get("low_confidence_spans") or []),
    }


class BlockTranslator:
    """单块翻译器：占位符替换 → LLM → 回注（数值结构性保护，R2-7/R1-10）。"""

    def __init__(self, model=None, glossary_prompt: str = ""):
        self._model = model
        self._glossary_prompt = glossary_prompt

    def _get_model(self):
        if self._model is None:
            from deerflow.models.factory import create_chat_model

            name = resolve_model_name()
            self._model = create_chat_model(name) if name else create_chat_model(
                __import__("deerflow.config", fromlist=["get_app_config"]).get_app_config().models[0].name
            )
        return self._model

    async def translate_block(self, block_id: str, text: str, source_lang: str) -> dict:
        """返回 {translation, uncertain, low_confidence_spans}。同步 LLM 调用走 to_thread。"""
        messages = build_messages(block_id, text, source_lang, self._glossary_prompt)
        model = self._get_model()
        raw = await asyncio.to_thread(_invoke_sync, model, messages)
        return parse_translation_response(raw, block_id)


def _invoke_sync(model, messages: list[dict]) -> str:
    """LangChain Runnable 同步调用（worker 的 to_thread 边界内执行）。"""
    result = model.invoke(messages)
    content = result.content
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)
