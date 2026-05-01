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
- rag_sources: 推荐的知识库检索来源
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
  "rag_sources": ["知识库来源1", "知识库来源2"],
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
        """Lazy-load the chat model."""
        if self._model is None:
            self._model = create_chat_model(name=self._model_name, thinking_enabled=False)
        return self._model

    def _invoke(self, messages: list, **kwargs) -> str:
        """Invoke the LLM and return the text content."""
        response = self.model.invoke(messages, **kwargs)
        if hasattr(response, "content"):
            return response.content
        return str(response)

    # ---- Schema Inference ----

    def infer_schema(self, doc_name: str, doc_content: str) -> dict:
        """Infer chapter structure from a single document.

        Args:
            doc_name: Name of the document.
            doc_content: Document text content.

        Returns:
            Dict with "sections" key containing the inferred chapter tree.
        """
        # Truncate content to avoid token limits
        content = doc_content[: self._max_content_chars]

        system = SystemMessage(content=_SCHEMA_INFERENCE_SYSTEM_PROMPT)
        user = HumanMessage(
            content=_SCHEMA_INFERENCE_USER_PROMPT_TEMPLATE.format(
                doc_name=doc_name,
                max_chars=self._max_content_chars,
                doc_content=content,
            )
        )

        try:
            raw = self._invoke([system, user])
            logger.info(f"[infer_schema] LLM raw response for '{doc_name}': {raw[:500]}...")

            # 尝试解析为 JSON
            result = self._extract_json(raw)

            # 处理 LLM 返回列表而非字典的情况
            if isinstance(result, list):
                logger.info("[infer_schema] LLM returned a list, wrapping in dict with 'sections' key")
                return {"sections": result}

            # 正常情况：返回字典
            logger.info(f"[infer_schema] Parsed sections count: {len(result.get('sections', []))}")
            return result
        except Exception as e:
            logger.error(f"[infer_schema] Schema inference failed for '{doc_name}': {e}")
            logger.exception("Full exception details:")
            return {"sections": []}

    # ---- Metadata Extraction ----

    def extract_metadata(
        self,
        section_id: str,
        section_title: str,
        level: int,
        purpose: str | None,
        section_content: str,
    ) -> dict:
        """Extract content contract for a single section.

        Args:
            section_id: Section identifier.
            section_title: Section title.
            level: Section level (1, 2, ...).
            purpose: Section purpose/description.
            section_content: Raw text content of this section.

        Returns:
            Dict with content_contract, compliance_rules, etc.
        """
        content = section_content[: self._max_content_chars]

        system = SystemMessage(content=_METADATA_EXTRACTION_SYSTEM_PROMPT)
        user = HumanMessage(
            content=_METADATA_EXTRACTION_USER_PROMPT_TEMPLATE.format(
                section_id=section_id,
                section_title=section_title,
                level=level,
                purpose=purpose or "未知",
                section_content=content,
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

    # ---- Section Merging ----

    def merge_sections(
        self,
        domain: str,
        report_sections_list: list[dict],
    ) -> dict:
        """Merge sections from multiple reports into a canonical template.

        Args:
            domain: The domain/industry identifier.
            report_sections_list: List of dicts, each containing
                "doc_name" and "sections" keys.

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
        user = HumanMessage(
            content=_MERGE_SECTIONS_USER_PROMPT_TEMPLATE.format(
                n_docs=len(report_sections_list),
                domain=domain,
                report_sections="\n\n".join(reports_text),
            )
        )

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

        Tries:
        1. Inline code block ```json ... ```
        2. Bare JSON object
        """
        text = raw.strip()

        # Try code block first
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.rfind("```")
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.rfind("```")
            text = text[start:end].strip()

        result = json.loads(text)

        if key:
            return result.get(key, {})
        return result

    def close(self):
        """Close the LLM client (no-op for LangChain)."""
        pass
