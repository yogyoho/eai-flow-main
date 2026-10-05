"""G3 直连文档抽取——文本→大纲/实体候选/本体产物(规则抽取, 零第三方依赖).

移植自 gateway eia_samples 模块(EAI-CUSTOM 2026-10-05, 设计 D14 预取模式):
- extract.py: read_source_text(txt/docx stdlib 解析)/extract_outline/extract_entities
- ontology_extract.py: extract_ontology(四类目标规则抽取, 与 registry eia.yaml 词汇对齐)
直连任务流: 源文件副本 → run_direct_extract → outline_json → 既有 converter → dg_*。
"""

from .extract import ExtractSourceError, read_source_text, run_extract
from .ontology_extract import extract_ontology

__all__ = ["ExtractSourceError", "read_source_text", "run_extract", "extract_ontology"]
