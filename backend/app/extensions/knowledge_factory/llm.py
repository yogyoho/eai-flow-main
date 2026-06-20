"""LLM client wrapper for knowledge factory extraction.

All LLM calls in the extraction pipeline go through this module.
Uses the project's existing `create_chat_model` factory.
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from packages.harness.deerflow.models.factory import create_chat_model

logger = logging.getLogger(__name__)

# Prompt for inferring chapter structure from a document
_SCHEMA_INFERENCE_SYSTEM_PROMPT = """你是一个专业的文档结构分析专家。

任务：从给定的样例文档中，推理出该类文档的标准章节结构。

要求：
1. 分析文档的章节标题，识别层级结构（一级章节、二级章节等）
2. 归纳章节的共性规律，提取标准章节模板
3. 每个章节给出：
   - id: 唯一标识（如 sec_01, sec_01_01）
   - title: 章节标题
   - level: 层级（1=一级, 2=二级, ...）
   - required: 是否必需
   - purpose: 章节目的/作用（50字以内）
4. 输出一棵树形结构，代表该类文档的标准模板
5. 章节层级不超过 {max_depth} 级（level 值不超过 {max_depth}）

注意：
- 不同类型的报告（环评、可研、水保、安全评价等）章节结构完全不同
- 要基于实际文档内容推断，不要猜测
- 如果文档章节不完整，可以合理补充常见章节"""

_SCHEMA_INFERENCE_USER_PROMPT_TEMPLATE = """## 文档信息
文档名称: {doc_name}
文档内容（前 {max_chars} 字）:

{doc_content}

---

请分析上述文档的章节结构，输出一份标准章节模板（JSON格式）：
```json
{{
  "sections": [
    {{
      "id": "sec_01",
      "title": "章节标题",
      "level": 1,
      "required": true,
      "purpose": "章节目的",
      "children": [
        {{
          "id": "sec_01_01",
          "title": "子章节标题",
          "level": 2,
          "required": true,
          "purpose": "子章节目的"
        }}
      ]
    }}
  ]
}}
```"""


# Prompt for extracting metadata from a section
_METADATA_EXTRACTION_SYSTEM_PROMPT = """你是一个专业的文档抽取专家。

任务：为一篇报告模板的某个章节，生成详细的内容契约（Content Contract）。

内容契约定义：
- key_elements: 章节必须包含的关键要素列表
- structure_type: 内容结构类型
  - narrative_text: 叙述性文本
  - table: 表格形式
  - formula: 公式/计算
  - diagram: 图表
  - mixed: 混合形式
- style_rules: 写作风格规范（如：使用被动语态、引用法规等）
- min_word_count: 最小字数要求
- forbidden_phrases: 禁止出现的表述

同时输出：
- compliance_rules: 涉及的法规/标准引用列表
- rag_sources: 推荐的知识库检索来源（从可用知识库列表中选择）
- generation_hint: 生成时的提示
- example_snippet: 该章节的典型文本片段（从原文提取）
- completeness_score: 该章节的完整度评分（0-100）

如果章节内容不足以提取某个字段，用 null 表示。"""


_METADATA_EXTRACTION_USER_PROMPT_TEMPLATE = """## 章节信息
章节ID: {section_id}
章节标题: {section_title}
层级: {level}
目的: {purpose}

## 原文档内容
以下是从样例报告中提取的该章节内容：

{section_content}
{available_kbs_section}
---

请为该章节生成完整的内容契约（JSON格式）：
```json
{{
  "content_contract": {{
    "key_elements": ["要素1", "要素2"],
    "structure_type": "narrative_text|table|formula|diagram|mixed",
    "style_rules": "写作风格规范",
    "min_word_count": 200,
    "forbidden_phrases": ["禁止表述1", "禁止表述2"]
  }},
  "compliance_rules": ["法规引用1", "法规引用2"],
  "rag_sources": [{{"kb_name": "知识库名称", "relevance_note": "为什么该知识库与此章节相关"}}],
  "generation_hint": "生成提示",
  "example_snippet": "典型文本片段（100-200字）...",
  "completeness_score": 85
}}
```"""


# Prompt for merging sections from multiple documents
_MERGE_SECTIONS_SYSTEM_PROMPT = """你是一个专业的报告模板融合专家。

任务：将多份同类报告的章节结构融合为一份标准模板。

融合原则：
1. 合并相似章节：不同报告的相同/相似章节合并
2. 去重：删除重复的章节
3. 补充：保留所有报告中出现过的必要章节
4. 排序：按逻辑顺序排列章节
5. 评分：根据章节内容的完整程度评分（融合来源越多越完整）

注意：
- 同一领域的报告可能有细微差异（如环评报告书 vs 环评报告表）
- 要综合多份报告的章节，取最大并集
- 章节ID需要全局唯一"""


_MERGE_SECTIONS_USER_PROMPT_TEMPLATE = """## 任务信息
融合 {n_docs} 份样例报告，生成标准模板

## 领域
{domain}

## 各报告章节结构

{report_sections}

---

请将上述章节结构融合为一份标准模板（JSON格式）：
```json
{{
  "sections": [
    {{
      "id": "sec_01",
      "title": "章节标题",
      "level": 1,
      "required": true,
      "purpose": "章节目的",
      "completeness_score": 85,
      "children": []
    }}
  ],
  "cross_section_rules": [
    {{
      "rule_id": "rule_01",
      "description": "规则描述",
      "source_sections": ["sec_01"],
      "target_sections": ["sec_02"],
      "validation_type": "data_consistency",
      "fields": ["字段1", "字段2"]
    }}
  ],
  "completeness_score": 82
}}
```"""


class ExtractionLLMClient:
    """LLM client for extraction pipeline.

    Wraps `create_chat_model` from the project and provides
    task-specific methods for schema inference, metadata extraction,
    and section merging.
    """

    def __init__(self, model_name: str | None = None, max_content_chars: int = 5000):
        """
        Args:
            model_name: Override the model name. Defaults to config's first model.
            max_content_chars: Max characters to send per document chunk.
        """
        self._model_name = model_name
        self._max_content_chars = max_content_chars
        self._model = None  # Lazy init

    @property
    def model(self):
        """Lazy-load the chat model.

        Model resolution order:
        1. Explicit model_name passed to __init__
        2. DEFAULT_MODEL environment variable (from system basic settings)
        3. config.yaml first model (via create_chat_model default)
        """
        if self._model is None:
            import os

            effective_name = self._model_name or os.getenv("DEFAULT_MODEL") or None
            self._model = create_chat_model(name=effective_name, thinking_enabled=False)
        return self._model

    def _invoke(self, messages: list, **kwargs) -> str:
        """Invoke the LLM and return the text content."""
        response = self.model.invoke(messages, **kwargs)
        if hasattr(response, "content"):
            return response.content
        return str(response)

    # ---- Schema Inference ----

    def infer_schema(self, doc_name: str, doc_content: str, max_depth: int = 3, reference_chapters: dict | None = None) -> dict:
        """Infer chapter structure from a single document.

        Args:
            doc_name: Name of the document.
            doc_content: Document text content.
            max_depth: Maximum chapter nesting depth (1-6, default 3).
            reference_chapters: Optional pre-defined chapter structure from
                the domain's standard_chapters field, used as guidance.

        Returns:
            Dict with "sections" key containing the inferred chapter tree.
        """
        # Truncate content to avoid token limits
        content = doc_content[: self._max_content_chars]

        system = SystemMessage(content=_SCHEMA_INFERENCE_SYSTEM_PROMPT.format(max_depth=max_depth))

        # Build user message with optional reference chapters
        user_parts = [
            _SCHEMA_INFERENCE_USER_PROMPT_TEMPLATE.format(
                doc_name=doc_name,
                max_chars=self._max_content_chars,
                doc_content=content,
            )
        ]

        if reference_chapters:
            ref_sections = reference_chapters.get("sections", [])
            if ref_sections:
                ref_json = json.dumps(ref_sections, ensure_ascii=False, indent=2)
                user_parts.append(
                    f"\n## 参考章节结构（来自标准大纲模板）\n"
                    f"请参考以下标准章节结构来推断文档的章节，尽可能与标准结构对齐：\n\n{ref_json}\n"
                )

        user = HumanMessage(content="\n".join(user_parts))

        raw = ""
        try:
            raw = self._invoke([system, user])
            logger.info(f"[infer_schema] LLM raw response for '{doc_name}' ({len(raw)} chars): {raw[:300]}...")

            # 尝试解析为 JSON
            result = self._extract_json(raw)

            # 处理 LLM 返回列表而非字典的情况
            if isinstance(result, list):
                logger.info("[infer_schema] LLM returned a list, wrapping in dict with 'sections' key")
                return {"sections": result}

            # 正常情况：返回字典
            sections = result.get("sections", [])
            if not sections:
                logger.warning(
                    f"[infer_schema] LLM returned empty sections for '{doc_name}'. "
                    f"Raw response (first 500 chars): {raw[:500]}"
                )
            logger.info(f"[infer_schema] Parsed sections count: {len(sections)}")
            return result
        except Exception as e:
            logger.error(
                f"[infer_schema] Schema inference failed for '{doc_name}': {e}. "
                f"Raw response: {raw[:500] if raw else 'LLM invoke failed'}"
            )
            logger.exception("Full traceback:")
            raise RuntimeError(f"章节结构推断失败: {e}") from e

    # ---- Metadata Extraction ----

    def extract_metadata(
        self,
        section_id: str,
        section_title: str,
        level: int,
        purpose: str | None,
        section_content: str,
        available_kbs: list[dict] | None = None,
    ) -> dict:
        """Extract content contract for a single section.

        Args:
            section_id: Section identifier.
            section_title: Section title.
            level: Section level (1, 2, ...).
            purpose: Section purpose/description.
            section_content: Raw text content of this section.
            available_kbs: Optional list of dicts with kb_id, kb_name, description.

        Returns:
            Dict with content_contract, compliance_rules, etc.
        """
        content = section_content[: self._max_content_chars]

        # Build the available KB section for the prompt
        if available_kbs:
            kb_lines = []
            for kb in available_kbs:
                desc = f" ({kb['description']})" if kb.get("description") else ""
                kb_lines.append(f"  - {kb['kb_name']}{desc}")
            available_kbs_section = (
                "\n## 可用知识库列表\n以下知识库可用于该章节的参考检索，请从中选择相关的：\n"
                + "\n".join(kb_lines)
            )
        else:
            available_kbs_section = ""

        system = SystemMessage(content=_METADATA_EXTRACTION_SYSTEM_PROMPT)
        user = HumanMessage(
            content=_METADATA_EXTRACTION_USER_PROMPT_TEMPLATE.format(
                section_id=section_id,
                section_title=section_title,
                level=level,
                purpose=purpose or "未知",
                section_content=content,
                available_kbs_section=available_kbs_section,
            )
        )

        try:
            raw = self._invoke([system, user])
            return self._extract_json(raw)
        except Exception as e:
            logger.warning(f"Metadata extraction failed for {section_id}: {e}")
            return {
                "content_contract": {
                    "key_elements": [],
                    "structure_type": "narrative_text",
                    "style_rules": None,
                    "min_word_count": None,
                    "forbidden_phrases": [],
                },
                "compliance_rules": [],
                "rag_sources": [],
                "generation_hint": None,
                "example_snippet": content[:200] if content else None,
                "completeness_score": 50,
            }

    # ---- Compliance Rule Extraction ----

    _RULE_EXTRACTION_SYSTEM_PROMPT = """你是一个合规规则提取专家。

任务：从法规/标准文档中识别可验证的合规要求，并提取为结构化的校验规则。

要求：
1. 仔细阅读文档，识别所有可量化的、可自动校验的合规要求
2. 每条规则必须包含：
   - rule_id: 唯一标识，格式 R_EXT_NNN（N为数字）
   - name: 规则名称，简洁明了
   - type: 规则类型，取值范围: data_validation, text_pattern, field_presence, cross_reference, value_range, keyword_check
   - severity: 严重级别，取值范围: critical, warning, info
   - description: 规则描述（50-150字）
   - error_message: 不合规时的错误提示（简洁，20-50字）
   - auto_fix_suggestion: 自动修复建议（可选）
3. 尽可能提取 validation_config，包含可校验的字段和条件
4. 过滤掉无法自动校验的纯管理性要求
5. 只提取明确的、可验证的要求，不要推测或创造规则"""

    _RULE_EXTRACTION_USER_PROMPT_TEMPLATE = """## 文档信息
文档名称: {doc_name}
行业: {industry}
报告类型: {report_types}

## 文档内容（前 {max_chars} 字）:

{doc_content}

---

请从上述文档中提取所有可自动校验的合规规则（JSON格式）：
```json
{{
  "rules": [
    {{
      "rule_id": "R_EXT_001",
      "name": "规则名称",
      "type": "data_validation",
      "severity": "critical",
      "description": "规则描述",
      "industry": "行业代码",
      "report_types": ["报告类型1"],
      "source_sections": ["来源章节"],
      "validation_config": {{
        "fields": ["字段1"],
        "comparisonType": "exists|equals|contains|range",
        "expectedValue": "期望值",
        "description": "校验说明"
      }},
      "error_message": "错误提示",
      "auto_fix_suggestion": "修复建议（可选）"
    }}
  ]
}}
```"""

    def extract_compliance_rules(
        self,
        doc_name: str,
        doc_content: str,
        industry: str = "",
        report_types: list[str] | None = None,
    ) -> list[dict]:
        """Extract compliance rules from a regulation/standard document.

        Args:
            doc_name: Name of the document.
            doc_content: Document text content.
            industry: Industry code (e.g. "environmental").
            report_types: List of applicable report types.

        Returns:
            List of rule dicts matching ComplianceRuleCreate schema.
        """
        content = doc_content[: 15000]
        system = SystemMessage(content=self._RULE_EXTRACTION_SYSTEM_PROMPT)
        user = HumanMessage(
            content=self._RULE_EXTRACTION_USER_PROMPT_TEMPLATE.format(
                doc_name=doc_name,
                industry=industry or "未指定",
                report_types=", ".join(report_types) if report_types else "未指定",
                max_chars=15000,
                doc_content=content,
            )
        )

        try:
            raw = self._invoke([system, user])
            result = self._extract_json(raw)
            rules = result.get("rules", [])
            if isinstance(rules, list):
                return rules
            logger.warning(f"[extract_compliance_rules] Expected 'rules' list, got {type(rules)}")
            return []
        except Exception as e:
            logger.error(f"[extract_compliance_rules] Failed: {e}")
            raise RuntimeError(f"合规规则提取失败: {e}") from e

    # ---- Section Merging ----

    def merge_sections(
        self,
        domain: str,
        report_sections_list: list[dict],
        reference_chapters: dict | None = None,
    ) -> dict:
        """Merge sections from multiple reports into a canonical template.

        Args:
            domain: The domain/industry identifier.
            report_sections_list: List of dicts, each containing
                "doc_name" and "sections" keys.
            reference_chapters: Optional pre-defined chapter structure from
                the domain's standard_chapters field, used as merge guidance.

        Returns:
            Dict with "sections", "cross_section_rules", "completeness_score".
        """
        # Format sections for each report
        reports_text = []
        for i, report in enumerate(report_sections_list, 1):
            doc_name = report.get("doc_name", f"报告{i}")
            sections = report.get("sections", [])
            reports_text.append(f"### 报告{i}: {doc_name}\n" + json.dumps(sections, ensure_ascii=False, indent=2))

        system = SystemMessage(content=_MERGE_SECTIONS_SYSTEM_PROMPT)

        # Build user message with optional reference chapters
        user_parts = [
            _MERGE_SECTIONS_USER_PROMPT_TEMPLATE.format(
                n_docs=len(report_sections_list),
                domain=domain,
                report_sections="\n\n".join(reports_text),
            )
        ]

        if reference_chapters:
            ref_sections = reference_chapters.get("sections", [])
            if ref_sections:
                ref_json = json.dumps(ref_sections, ensure_ascii=False, indent=2)
                user_parts.append(
                    f"\n## 参考章节结构（来自标准大纲模板）\n"
                    f"请优先与以下标准章节结构对齐，确保融合结果覆盖标准大纲中的所有章节：\n\n{ref_json}\n"
                )

        user = HumanMessage(content="\n".join(user_parts))

        try:
            raw = self._invoke([system, user])
            return self._extract_json(raw)
        except Exception as e:
            logger.warning(f"Section merge failed: {e}, falling back to first report")
            if report_sections_list:
                first = report_sections_list[0].get("sections", [])
                return {"sections": first, "cross_section_rules": [], "completeness_score": 60}
            return {"sections": [], "cross_section_rules": [], "completeness_score": 0}

    # ---- Utility ----

    @staticmethod
    def _extract_json(raw: str, key: str | None = None) -> dict:
        """Extract JSON from LLM response.

        Tries multiple strategies (ordered by reliability):
        1. ```json ... ``` code block
        2. ``` ... ``` code block
        3. Direct json.loads on full text
        4. Bracket matching for outermost balanced { ... }
        5. Bracket matching for outermost balanced [ ... ]
        6. Remove <｜end▁of▁thinking｜>/thinking wrapper tags, then retry strategy 4
        """
        text = raw.strip()

        # Strategy 1: Extract from ```json ... ``` code block.
        if "```json" in text:
            start = text.find("```json") + 7
            rest = text[start:]
            end_inner = rest.find("```")
            if end_inner > 0:
                text = rest[:end_inner].strip()
        elif "```" in text:
            start = text.find("```") + 3
            rest = text[start:]
            end_inner = rest.find("```")
            if end_inner > 0:
                text = rest[:end_inner].strip()

        # Strategy 2: Try direct json.loads
        try:
            result = json.loads(text)
            if key:
                return result.get(key, {})
            return result
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 3: Find the first balanced { ... } via bracket counting
        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(text)):
                ch = text[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            result = json.loads(text[brace_start : i + 1])
                            if key:
                                return result.get(key, {})
                            return result
                        except (json.JSONDecodeError, ValueError):
                            break
                        break

        # Strategy 4: Fallback — try to find a JSON array [...]
        bracket_start = text.find("[")
        if bracket_start >= 0:
            depth = 0
            in_string = False
            escape = False
            for i in range(bracket_start, len(text)):
                ch = text[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch in "{[(":
                    depth += 1
                elif ch in "}])":
                    depth -= 1
                    if depth < 0:
                        try:
                            result = json.loads(text[bracket_start : i + 1])
                            if isinstance(result, list):
                                if key:
                                    return result.get(key, {})
                                return result
                        except (json.JSONDecodeError, ValueError):
                            break
                        break

        # Strategy 5: Strip common LLM wrapper patterns (e.g. 思考/回答 tags)
        # Some Chinese reasoning models wrap output in  思考.../思考 or similar tags
        import re as _re
        cleaned = _re.sub(r"<[^>]+>", "", raw)
        cleaned = _re.sub(r"【[^】]+】", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned != raw:
            brace_start = cleaned.find("{")
            if brace_start >= 0:
                depth = 0
                for i in range(brace_start, len(cleaned)):
                    ch = cleaned[i]
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                result = json.loads(cleaned[brace_start : i + 1])
                                if key:
                                    return result.get(key, {})
                                return result
                            except (json.JSONDecodeError, ValueError):
                                break

        raise ValueError(
            f"Could not extract JSON from LLM response. "
            f"First 500 chars: {raw[:500]}"
        )

    def close(self):
        """Close the LLM client (no-op for LangChain)."""
        pass
