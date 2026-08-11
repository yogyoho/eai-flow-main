"""Formula DAG engine — dependency graph, topological execution, dirty propagation, consistency validation.

Generic computation layer. Zero domain knowledge. Usable by any engineering discipline skill
(water drainage, HVAC, piping, fire protection, etc.).

Domain-specific data (formula definitions, consistency contracts) lives alongside each skill.
"""

from app.extensions.formula_engine.consistency import (
    ConsistencyEngine,
    Contract,
    ContractType,
    Severity,
    Violation,
)
from app.extensions.formula_engine.graph import (
    FormulaGraph,
    FormulaNode,
    ParamSource,
    ParamSourceType,
)

__all__ = [
    "FormulaGraph",
    "FormulaNode",
    "ParamSource",
    "ParamSourceType",
    "ConsistencyEngine",
    "Contract",
    "ContractType",
    "Severity",
    "Violation",
]
