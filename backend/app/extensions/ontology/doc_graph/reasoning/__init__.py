"""doc_graph 推理子包——vendored Rete 引擎 + 规则推理 facade（现算现返）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-reasoning-rules-design.md §3。
rete_engine.py vendor 自 semantica-agi/semantica@7057387775ecdf74c14e38d0067fd8e1267eaaf8
(MIT), 包内 import 剥离清单见 ./README.md。
"""

from app.extensions.ontology.doc_graph.reasoning.facade import (
    MAX_DERIVED,
    MAX_ITERATIONS,
    MAX_RULE_FIRES,
    RuleFacade,
)

__all__ = ["MAX_DERIVED", "MAX_ITERATIONS", "MAX_RULE_FIRES", "RuleFacade"]
