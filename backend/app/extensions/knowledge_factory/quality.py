"""AI-powered quality assessment for templates.

Uses LLM to evaluate templates across multiple dimensions:
- Completeness: Chapter coverage
- Accuracy: RAG matching quality
- Consistency: Cross-section references
- Compliance: Rule compliance rate
- Freshness: Example update frequency
"""

import json
import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from packages.harness.deerflow.models.factory import create_chat_model

logger = logging.getLogger(__name__)


_QUALITY_ASSESSMENT_SYSTEM_PROMPT = """你是一个专业的报告质量评估专家。

任务：对给定的报告模板进行多维度质量评估。

评估维度：
1. completeness（完整性）：章节覆盖率、必填章节是否完整
2. accuracy（准确性）：元数据描述是否准确，内容契约是否清晰
3. consistency（一致性）：交叉引用是否合理、层级结构是否一致
4. compliance（合规性）：合规规则是否完整、法规引用是否正确
5. freshness（时效性）：示例片段是否充分、生成提示是否有用

评估要求：
- 每个维度给出 0-100 的评分
- strengths：该维度的亮点和优点（正面发现）
- issues：该维度存在的实际问题和不足（必须是真正的缺陷，如缺失、错误、不一致等）。如果没有问题则返回空数组 []
- 给出总体评分和建议
- 只返回 JSON，不要有其他内容"""


_QUALITY_ASSESSMENT_USER_PROMPT_TEMPLATE = """## 模板信息
模板名称: {template_name}
领域: {domain}
版本: {version}
状态: {status}

## 章节结构
{chapter_tree}

## 内容契约摘要
{content_contracts}

## 合规规则
{compliance_rules}

## RAG 数据源
{rag_sources}

## 生成提示和示例
{generation_hints}

---

请评估此模板的质量（JSON格式）：
```json
{{
  "overall_score": 85,
  "dimensions": {{
    "completeness": {{
      "score": 90,
      "strengths": ["章节覆盖率较高", "必填章节完整"],
      "issues": []
    }},
    "accuracy": {{
      "score": 85,
      "strengths": ["元数据描述基本准确"],
      "issues": ["部分章节的content_contract描述不够详细"]
    }},
    "consistency": {{
      "score": 95,
      "strengths": ["交叉引用合理", "层级结构一致"],
      "issues": []
    }},
    "compliance": {{
      "score": 80,
      "strengths": ["合规规则框架完整"],
      "issues": ["缺少部分法规引用"]
    }},
    "freshness": {{
      "score": 70,
      "strengths": ["生成提示覆盖了主要章节"],
      "issues": ["示例片段数量偏少"]
    }}
  }},
  "suggestions": ["建议补充sec_02的示例片段", "建议完善合规规则的法规引用"],
  "quality_grade": "良好"
}}
```"""


class QualityAssessmentClient:
    """LLM client for quality assessment."""

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = create_chat_model(name=self._model_name, thinking_enabled=False)
        return self._model

    def _invoke(self, messages: list) -> str:
        response = self.model.invoke(messages)
        if hasattr(response, "content"):
            return response.content
        return str(response)

    def assess(self, template_data: dict) -> dict:
        """Assess template quality."""
        template_name = template_data.get("name", "未命名模板")
        domain = template_data.get("domain", "unknown")
        version = template_data.get("version", "v1.0.0")
        status = template_data.get("status", "draft")

        sections = template_data.get("root_sections", [])
        chapter_tree = self._build_chapter_tree(sections)
        content_contracts = self._build_content_contracts(sections)

        rules = template_data.get("cross_section_rules", [])
        if rules:
            compliance_rules = "\n".join([f"- {r.get('description', r.get('rule', ''))}" for r in rules])
        else:
            compliance_rules = "无"

        rag_sources = self._collect_rag_sources(sections)
        generation_hints = self._build_generation_hints(sections)

        system = SystemMessage(content=_QUALITY_ASSESSMENT_SYSTEM_PROMPT)
        user = HumanMessage(
            content=_QUALITY_ASSESSMENT_USER_PROMPT_TEMPLATE.format(
                template_name=template_name,
                domain=domain,
                version=version,
                status=status,
                chapter_tree=chapter_tree,
                content_contracts=content_contracts,
                compliance_rules=compliance_rules,
                rag_sources=rag_sources,
                generation_hints=generation_hints,
            )
        )

        try:
            raw = self._invoke([system, user])
            return self._extract_json(raw)
        except Exception as e:
            logger.warning(f"Quality assessment failed: {e}")
            return self._get_fallback_assessment()

    def _build_chapter_tree(self, sections: list[dict], depth: int = 0) -> str:
        lines = []
        for sec in sections:
            indent = "  " * depth
            required_mark = "[必]" if sec.get("required", True) else "[可选]"
            lines.append(f"{indent}- {sec.get('title', '未命名')} {required_mark}")
            children = sec.get("children", [])
            if children:
                lines.append(self._build_chapter_tree(children, depth + 1))
        return "\n".join(lines)

    def _build_content_contracts(self, sections: list[dict]) -> str:
        contracts = []
        for sec in sections:
            title = sec.get("title", "未命名")
            contract = sec.get("content_contract", {})
            key_elements = contract.get("key_elements", [])
            structure_type = contract.get("structure_type", "narrative_text")
            style_rules = contract.get("style_rules", "")
            forbidden = contract.get("forbidden_phrases", [])

            summary = f"## {title}\n"
            summary += f"- 结构类型: {structure_type}\n"
            if key_elements:
                summary += f"- 关键要素: {', '.join(key_elements[:3])}"
                if len(key_elements) > 3:
                    summary += f" 等{len(key_elements)}项"
                summary += "\n"
            if style_rules:
                summary += f"- 风格规范: {style_rules[:50]}"
                if len(style_rules) > 50:
                    summary += "..."
                summary += "\n"
            if forbidden:
                summary += f"- 禁用短语: {', '.join(forbidden[:2])}"
                if len(forbidden) > 2:
                    summary += f" 等{len(forbidden)}项"
                summary += "\n"
            contracts.append(summary)

            children = sec.get("children", [])
            if children:
                contracts.append(self._build_content_contracts(children))

        return "\n".join(contracts) if contracts else "无"

    def _collect_rag_sources(self, sections: list[dict]) -> str:
        sources: list[str] = []
        self._collect_rag_sources_recursive(sections, sources)
        unique = sorted(set(sources))
        if unique:
            return "\n".join([f"- {s}" for s in unique])
        return "无"

    def _collect_rag_sources_recursive(self, sections: list[dict], sources: list[str]) -> None:
        for sec in sections:
            rag = sec.get("rag_sources", [])
            for item in rag:
                if isinstance(item, dict):
                    sources.append(item.get("kb_name", item.get("name", str(item))))
                elif isinstance(item, str):
                    sources.append(item)
            children = sec.get("children", [])
            if children:
                self._collect_rag_sources_recursive(children, sources)

    def _build_generation_hints(self, sections: list[dict]) -> str:
        hints = []
        self._build_generation_hints_recursive(sections, hints)
        return "\n".join(hints) if hints else "无"

    def _build_generation_hints_recursive(self, sections: list[dict], hints: list) -> None:
        for sec in sections:
            title = sec.get("title", "未命名")
            hint = sec.get("generation_hint", "")
            example = sec.get("example_snippet", "")

            summary = f"## {title}\n"
            if hint:
                hint_preview = hint[:80] + "..." if len(hint) > 80 else hint
                summary += f"- 提示: {hint_preview}\n"
            if example:
                example_preview = example[:100] + "..." if len(example) > 100 else example
                summary += f"- 示例: {example_preview}\n"
            else:
                summary += "- 示例: 无\n"

            if hint or example:
                hints.append(summary)

            children = sec.get("children", [])
            if children:
                self._build_generation_hints_recursive(children, hints)

    def _extract_json(self, raw: str) -> dict:
        text = raw.strip()

        if "```json" in text:
            start = text.find("```json") + 7
            end = text.rfind("```")
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.rfind("```")
            text = text[start:end].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON: {text[:200]}")
            return self._get_fallback_assessment()

    def _get_fallback_assessment(self) -> dict:
        return {
            "overall_score": 50,
            "dimensions": {
                "completeness": {"score": 50, "strengths": [], "issues": ["评估服务暂时不可用"]},
                "accuracy": {"score": 50, "strengths": [], "issues": ["评估服务暂时不可用"]},
                "consistency": {"score": 50, "strengths": [], "issues": ["评估服务暂时不可用"]},
                "compliance": {"score": 50, "strengths": [], "issues": ["评估服务暂时不可用"]},
                "freshness": {"score": 50, "strengths": [], "issues": ["评估服务暂时不可用"]},
            },
            "suggestions": ["请稍后重试质量评估"],
            "quality_grade": "未知",
        }
