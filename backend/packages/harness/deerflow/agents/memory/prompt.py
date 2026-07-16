"""Prompt templates for memory update and injection."""

from __future__ import annotations

import html
import logging
import math
import re
from typing import Any

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

logger = logging.getLogger(__name__)

# Module-level tiktoken encoding cache. Populated lazily on first use;
# subsequent calls are a dict lookup (no network I/O). Pre-warming at startup
# via warm_tiktoken_cache() avoids blocking a request on the (potentially slow)
# first get_encoding call — see upstream #3411 / #3402.
_tiktoken_encoding_cache: dict[str, tiktoken.Encoding] = {}


def _get_tiktoken_encoding(encoding_name: str = "cl100k_base") -> tiktoken.Encoding | None:
    """Return a cached tiktoken encoding, or None on failure / unavailability.

    On the first call for a given encoding_name, tiktoken may download the BPE
    data from openaipublic.blob.core.windows.net. In network-restricted
    environments this can block for tens of minutes before the OS TCP timeout.
    Callers should run it off the event loop (e.g. via asyncio.to_thread).
    """
    if not TIKTOKEN_AVAILABLE:
        return None

    cached = _tiktoken_encoding_cache.get(encoding_name)
    if cached is not None:
        return cached

    try:
        encoding = tiktoken.get_encoding(encoding_name)
        _tiktoken_encoding_cache[encoding_name] = encoding
        return encoding
    except Exception:
        logger.warning("Failed to load tiktoken encoding %r; falling back to char-based estimation", encoding_name, exc_info=True)
        return None


def warm_tiktoken_cache() -> bool:
    """Pre-warm the tiktoken encoding cache.

    Call at startup (off the event loop) so the first request never blocks on
    the BPE download. Returns True if the encoding loaded (or was cached).
    """
    return _get_tiktoken_encoding("cl100k_base") is not None

# Prompt template for updating memory based on conversation
MEMORY_UPDATE_PROMPT = """你是一个记忆管理系统。你的任务是分析对话并更新用户的记忆档案。

当前记忆状态:
<current_memory>
{current_memory}
</current_memory>

要处理的新对话:
<conversation>
{conversation}
</conversation>

指令:
1. 分析对话中关于用户的重要信息
2. 提取相关事实、偏好和上下文，包含具体细节（数字、名称、技术）
3. 按照下面的详细长度指南更新记忆各节

提取事实前，对对话进行结构化反思:
1. 错误/重试检测: Agent 是否遇到错误、需要重试、或产生了错误结果？
   如果是，将根因和正确方法记录为高置信度事实，类别为 "correction"。
2. 用户纠正检测: 用户是否纠正了 Agent 的方向、理解或输出？
   如果是，将正确的解释或方法记录为高置信度事实，类别为 "correction"。
   仅在类别为 "correction" 且错误在对话中明确时，才在 "sourceError" 中包含出错内容。
	3. 项目约束发现: 对话中是否发现了项目特定的约束条件？
	   如果是，将其记录为事实，选择最合适的类别和置信度。

	{correction_hint}

	记忆各节指南:

	**用户上下文** (当前状态 - 简洁摘要):
	- workContext: 职业角色、公司、关键项目、主要技术 (2-3句话)
	  例如: 核心贡献者，项目名称含指标 (16k+ stars)，技术栈
	- personalContext: 语言能力、沟通偏好、关键兴趣 (1-2句话)
	  例如: 双语能力、具体兴趣领域、专业领域
	- topOfMind: 用户近期关注的多个优先事项和焦点 (3-5句话，详细段落)
	  例如: 主要项目工作、并行的技术调研、持续学习/追踪
	  包含: 活跃的实现工作、故障排查、市场/研究兴趣
	  注意: 这里捕捉多个并发的关注主题，不是一个任务

	**历史** (时间上下文 - 丰富段落):
	- recentMonths: 近期活动的详细摘要 (4-6句话或1-2段)
	  时间范围: 最近1-3个月的交互
	  包含: 探索过的技术、做过的项目、解决的问题、表现出的兴趣
	- earlierContext: 重要的历史模式 (3-5句话或1段)
	  时间范围: 3-12个月前
	  包含: 过去的项目、学习历程、已建立的模式
	- longTermBackground: 持久背景和基础上下文 (2-4句话)
	  时间范围: 整体/基础信息
	  包含: 核心专长、长期兴趣、基本工作风格

	**事实提取**:
	- 提取具体、可量化的细节 (如 "16k+ GitHub stars", "200+ 数据集")
	- 包含专有名词 (公司名、项目名、技术名)
	- 保留技术术语和版本号
	- 类别:
	  * preference: 用户偏好/不喜欢的工具、风格、方法
	  * knowledge: 特定专长、掌握的技术、领域知识
	  * context: 背景事实 (职位、项目、地点、语言)
	  * behavior: 工作模式、沟通习惯、问题解决方法
	  * goal: 明确的目标、学习方向、项目愿景
	  * correction: 明确的 Agent 错误或用户纠正，包含正确方法
	- 置信度:
	  * 0.9-1.0: 明确陈述的事实 ("我做X", "我的角色是Y")
	  * 0.7-0.8: 从行动/讨论中强烈暗示
	  * 0.5-0.6: 推断出的模式 (谨慎使用，仅用于清晰模式)

	**内容归属**:
	- workContext: 当前工作、活跃项目、主要技术栈
	- personalContext: 语言、性格、工作之外的兴趣
	- topOfMind: 用户近期关心的多个优先事项和焦点 (更新最频繁)
	  应捕捉3-5个并发主题: 主要工作、侧面探索、学习/追踪兴趣
	- recentMonths: 近期技术探索和工作的详细记录
	- earlierContext: 稍旧的交互中仍相关的模式
	- longTermBackground: 关于用户不变的基础事实

	**多语言内容**:
	- 保留专有名词和公司名的原始语言
	- 技术术语保持原样 (DeepSeek, LangGraph 等)
	- 在 personalContext 中注明语言能力

	输出格式 (JSON):
	{{
	  "user": {{
	    "workContext": {{ "summary": "...", "shouldUpdate": true/false }},
	    "personalContext": {{ "summary": "...", "shouldUpdate": true/false }},
	    "topOfMind": {{ "summary": "...", "shouldUpdate": true/false }}
	  }},
	  "history": {{
	    "recentMonths": {{ "summary": "...", "shouldUpdate": true/false }},
	    "earlierContext": {{ "summary": "...", "shouldUpdate": true/false }},
	    "longTermBackground": {{ "summary": "...", "shouldUpdate": true/false }}
	  }},
	  "newFacts": [
	    {{ "content": "...", "category": "preference|knowledge|context|behavior|goal|correction", "confidence": 0.0-1.0, "expected_valid_days": 90 }}
	  ],
	  "factsToRemove": ["fact_id_1", "fact_id_2"],
	  "staleFactsToRemove": [{{ "id": "fact_id", "reason": "brief explanation" }}],
	  "staleFactsToExtend": [{{ "id": "fact_id", "extend_by_days": 365, "reason": "brief explanation" }}]
	}}

	重要规则:
	- 仅在有有意义的新信息时设置 shouldUpdate=true
	- 遵循长度指南: workContext/personalContext 简洁 (1-3句)，topOfMind 和历史各节详细 (段落)
	- 在事实中包含具体指标、版本号和专有名词
	- 仅添加明确陈述 (0.9+) 或强烈暗示 (0.7+) 的事实
	- 明确 Agent 错误或用户纠正使用类别 "correction"；纠正明确时置信度 >= 0.95
	- 仅在纠正事实中先前错误或错误方法明确陈述时包含 "sourceError"；否则省略
	- 删除与新信息矛盾的事实
	- 更新 topOfMind 时，整合新焦点同时移除已完成/放弃的
	  保持3-5个仍然活跃和相关的并发焦点主题
	- 对于历史各节，按时间顺序将新信息整合到适当的时间段
	- 保持技术准确性——保留技术、公司、项目的确切名称
	- 聚焦对未来交互和个性化有用的信息
	- 重要: 不要在记忆中记录文件上传事件。上传的文件是会话特定的临时文件——
	  在后续会话中无法访问。记录上传事件会导致后续对话混乱。

{staleness_review_section}

	只返回有效的 JSON，不要解释或 markdown。"""


# Staleness review section injected into MEMORY_UPDATE_PROMPT when triggered (upstream #3860).
# Surfaces aged facts so the LLM semantically judges each, rather than relying on passive
# contradiction from the current conversation.
STALENESS_REVIEW_PROMPT = """## Staleness Review

The following facts have reached their individual review window and may no longer
accurately reflect the user's current situation. Each entry shows a ``valid:Nd``
annotation - the number of days this fact was expected to remain valid before
re-evaluation. Use it to calibrate conservatism: a ``valid:30d`` fact was
considered volatile at creation; a ``valid:365d`` fact was considered stable.

<stale_facts>
{stale_facts}
</stale_facts>

For each fact, decide KEEP, REMOVE, or EXTEND:
- KEEP: Still likely valid - even if not mentioned in this conversation.
  Stable attributes (native language, core expertise, personality traits) often
  remain true indefinitely.
- REMOVE: Outdated, contradicted by recent context, or no longer relevant.
  Examples: tech-stack migrations, job changes, relocated offices, abandoned projects.
- EXTEND: Keep but recalibrate the review window (see below).

Add REMOVE decisions to "staleFactsToRemove" in your output JSON.
Each entry must be {{"id": "fact_id", "reason": "brief explanation"}}.
The reason should cite what signal in the conversation (or absence thereof)
supports the removal.

Optionally, for facts you KEEP and wish to recalibrate, add them to
"staleFactsToExtend" with the number of days from now before the next review:
{{"id": "fact_id", "extend_by_days": 365, "reason": "brief explanation"}}
Use this when the current window seems miscalibrated - e.g. a core skill marked
``valid:30d`` that is clearly stable. Omit facts whose current window already
seems appropriate. Values above the server ceiling are silently reduced.

Be conservative - when in doubt, KEEP. Removing a valid fact is worse than
keeping a slightly stale one, because the next review cycle will re-evaluate it."""


# Prompt template for extracting facts from a single message
FACT_EXTRACTION_PROMPT = """从这条消息中提取关于用户的事实信息。

消息:
{message}

按以下JSON格式提取事实:
{{
  "facts": [
    {{ "content": "...", "category": "preference|knowledge|context|behavior|goal|correction", "confidence": 0.0-1.0 }}
  ]
}}

类别:
- preference: 用户偏好 (喜欢/不喜欢、风格、工具)
- knowledge: 用户的专长或知识领域
- context: 背景上下文 (地点、工作、项目)
- behavior: 行为模式
- goal: 用户的目标
- correction: 明确的纠正或应避免重复的错误

规则:
- 只提取清晰、具体的事实
- 置信度反映确定性 (明确陈述 = 0.9+, 暗示 = 0.6-0.8)
- 跳过模糊或临时信息

只返回有效的JSON。"""


def _count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens in text using tiktoken.

    Args:
        text: The text to count tokens for.
        encoding_name: The encoding to use (default: cl100k_base for GPT-4/3.5).

    Returns:
        The number of tokens in the text.
    """
    encoding = _get_tiktoken_encoding(encoding_name)
    if encoding is None:
        # tiktoken unavailable, or the encoding failed to load.
        return len(text) // 4

    try:
        return len(encoding.encode(text))
    except Exception:
        # Fallback to character-based estimation on error
        return len(text) // 4


def _coerce_confidence(value: Any, default: float = 0.0) -> float:
    """Coerce a confidence-like value to a bounded float in [0, 1].

    Non-finite values (NaN, inf, -inf) are treated as invalid and fall back
    to the default before clamping, preventing them from dominating ranking.
    The ``default`` parameter is assumed to be a finite value.
    """
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return max(0.0, min(1.0, default))
    if not math.isfinite(confidence):
        return max(0.0, min(1.0, default))
    return max(0.0, min(1.0, confidence))


def format_memory_for_injection(memory_data: dict[str, Any], max_tokens: int = 2000) -> str:
    """Format memory data for injection into system prompt.

    Args:
        memory_data: The memory data dictionary.
        max_tokens: Maximum tokens to use (counted via tiktoken for accuracy).

    Returns:
        Formatted memory string for system prompt injection.
    """
    if not memory_data:
        return ""

    sections = []

    # Format user context
    user_data = memory_data.get("user", {})
    if user_data:
        user_sections = []

        work_ctx = user_data.get("workContext", {})
        if work_ctx.get("summary"):
            user_sections.append(f"工作: {work_ctx['summary']}")

        personal_ctx = user_data.get("personalContext", {})
        if personal_ctx.get("summary"):
            user_sections.append(f"个人: {personal_ctx['summary']}")

        top_of_mind = user_data.get("topOfMind", {})
        if top_of_mind.get("summary"):
            user_sections.append(f"当前焦点: {top_of_mind['summary']}")

        if user_sections:
            sections.append("用户上下文:\n" + "\n".join(f"- {s}" for s in user_sections))

    # Format history
    history_data = memory_data.get("history", {})
    if history_data:
        history_sections = []

        recent = history_data.get("recentMonths", {})
        if recent.get("summary"):
            history_sections.append(f"近期: {recent['summary']}")

        earlier = history_data.get("earlierContext", {})
        if earlier.get("summary"):
            history_sections.append(f"早期: {earlier['summary']}")

        background = history_data.get("longTermBackground", {})
        if background.get("summary"):
            history_sections.append(f"背景: {background['summary']}")

        if history_sections:
            sections.append("历史记录:\n" + "\n".join(f"- {s}" for s in history_sections))

    # Format facts (sorted by confidence; include as many as token budget allows)
    facts_data = memory_data.get("facts", [])
    if isinstance(facts_data, list) and facts_data:
        ranked_facts = sorted(
            (f for f in facts_data if isinstance(f, dict) and isinstance(f.get("content"), str) and f.get("content").strip()),
            key=lambda fact: _coerce_confidence(fact.get("confidence"), default=0.0),
            reverse=True,
        )

        # Compute token count for existing sections once, then account
        # incrementally for each fact line to avoid full-string re-tokenization.
        base_text = "\n\n".join(sections)
        base_tokens = _count_tokens(base_text) if base_text else 0
        # Account for the separator between existing sections and the facts section.
        facts_header = "Facts:\n"
        separator_tokens = _count_tokens("\n\n" + facts_header) if base_text else _count_tokens(facts_header)
        running_tokens = base_tokens + separator_tokens

        fact_lines: list[str] = []
        for fact in ranked_facts:
            content_value = fact.get("content")
            if not isinstance(content_value, str):
                continue
            content = content_value.strip()
            if not content:
                continue
            category = str(fact.get("category", "context")).strip() or "context"
            confidence = _coerce_confidence(fact.get("confidence"), default=0.0)
            source_error = fact.get("sourceError")
            if category == "correction" and isinstance(source_error, str) and source_error.strip():
                line = f"- [{category} | {confidence:.2f}] {content} (avoid: {source_error.strip()})"
            else:
                line = f"- [{category} | {confidence:.2f}] {content}"

            # Each additional line is preceded by a newline (except the first).
            line_text = ("\n" + line) if fact_lines else line
            line_tokens = _count_tokens(line_text)

            if running_tokens + line_tokens <= max_tokens:
                fact_lines.append(line)
                running_tokens += line_tokens
            else:
                break

        if fact_lines:
            sections.append("Facts:\n" + "\n".join(fact_lines))

    if not sections:
        return ""

    result = "\n\n".join(sections)

    # Use accurate token counting with tiktoken
    token_count = _count_tokens(result)
    if token_count > max_tokens:
        # Truncate to fit within token limit
        # Estimate characters to remove based on token ratio
        char_per_token = len(result) / token_count
        target_chars = int(max_tokens * char_per_token * 0.95)  # 95% to leave margin
        result = result[:target_chars] + "\n..."

    return result


def format_conversation_for_update(messages: list[Any]) -> str:
    """Format conversation messages for memory update prompt.

    Args:
        messages: List of conversation messages.

    Returns:
        Formatted conversation string.
    """
    lines = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", str(msg))

        # Handle content that might be a list (multimodal)
        if isinstance(content, list):
            text_parts = []
            for p in content:
                if isinstance(p, str):
                    text_parts.append(p)
                elif isinstance(p, dict):
                    text_val = p.get("text")
                    if isinstance(text_val, str):
                        text_parts.append(text_val)
            content = " ".join(text_parts) if text_parts else str(content)

        # Strip uploaded_files tags from human messages to avoid persisting
        # ephemeral file path info into long-term memory.  Skip the turn entirely
        # when nothing remains after stripping (upload-only message).
        if role == "human":
            content = re.sub(r"<uploaded_files>[\s\S]*?</uploaded_files>\n*", "", str(content)).strip()
            if not content:
                continue

        # Truncate very long messages
        if len(str(content)) > 1000:
            content = str(content)[:1000] + "..."

        # Escape < > & before embedding into the <conversation> block of MEMORY_UPDATE_PROMPT.
        # This raw user turn is the most attacker-influenced input in the prompt, so an
        # unescaped value like "</conversation><current_memory>..." would close the block and
        # forge a <current_memory> authority section for the extraction LLM (upstream #4162).
        # Escape after truncation so a trailing "..." cannot split an entity; quote=False
        # because content lands in element-text position (never an attribute value).
        content = html.escape(str(content), quote=False)

        if role == "human":
            lines.append(f"User: {content}")
        elif role == "ai":
            lines.append(f"Assistant: {content}")

    return "\n\n".join(lines)
