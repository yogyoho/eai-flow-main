"""真库事实装载——dg_entities/dg_relations → RuleFacade 三元组事实.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-reasoning-rules-design.md §3。
连接模式照 ingest.py（_ext_url 单一真源 + NullPool + finally dispose）; SQL 全参数化。
装载语义（宁缺勿滥方向）:
- 类型事实 (name, etype, name)——三列同值: facade 单参模式 ``etype(?X)`` 绑定 subject 位;
- 关系事实 (s.canonical_name, r.predicate, o.canonical_name)。dg_relations 无 status 列——
  "有效关系"语义 = 双端实体均 active 且置信度达标（merged/pending_review 实体隐去后,
  挂在其上的边自然不可达）; 关系行自身 confidence 不设门槛（Task 3 方案定案, 写侧
  谓词角色校验已兜底, 需要收紧时在两处 WHERE 各加一行即可）。
- 同名歧义决策（评审加固）: uq_dg_entities_natural=(domain, etype, norm_name) 允许跨 etype
  同名实体; 事实空间按 canonical_name 作 symbol → 跨 etype 同名会发生类型事实合并 +
  关系 JOIN 歧义。本层语义决策 = **同名即同义**（对推理而言, 同名实体语义合并可接受）;
  如需精确区分, 后续收紧点 = symbol 加 etype 限定（如 ``name/etype``）。
- 双时间决策（评审加固）: valid_from/valid_to（业务有效期）当前不过滤——EIA 导入源恒 NULL,
  加过滤等于无操作; 有效期语义启用为后续收紧点（读侧按 NOW() 截尾即可）。
- MIN_CONFIDENCE 与 ingest.REVIEW_CONFIDENCE 同值不同源: 前者是推理可信子图的读侧阈值,
  后者是写侧复核阈值, 各自独立演进互不耦合。
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.extensions.ontology.connectors import _ext_url

MIN_CONFIDENCE = 0.7

_ENTITIES_SQL = text(
    """
    SELECT canonical_name, etype
    FROM dg_entities
    WHERE domain = :domain AND status = 'active' AND confidence >= :mc
    ORDER BY canonical_name, etype
    """
)

_RELATIONS_SQL = text(
    """
    SELECT s.canonical_name, r.predicate, o.canonical_name
    FROM dg_relations r
    JOIN dg_entities s ON s.id = r.subject_id
    JOIN dg_entities o ON o.id = r.object_id
    WHERE s.domain = :domain AND o.domain = :domain
      AND s.status = 'active' AND o.status = 'active'
      AND s.confidence >= :mc AND o.confidence >= :mc
    ORDER BY s.canonical_name, r.predicate, o.canonical_name
    """
)


async def load_facts(domain: str, min_confidence: float = MIN_CONFIDENCE) -> list[tuple[str, str, str]]:
    """装载指定域的活跃可信事实三元组（类型事实 + 关系事实），只读零落库。

    供 evaluate_rules 现算现返使用; 域内无数据返回空列表（空态合法, 不视为错误）。
    """
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    params = {"domain": domain, "mc": min_confidence}
    facts: list[tuple[str, str, str]] = []
    try:
        async with engine.connect() as conn:
            # 类型事实在前: 同名实体的 etype 断言先于引用它的关系事实入网络（facade 按轮全量重灌, 顺序仅影响确定性）
            for name, etype in await conn.execute(_ENTITIES_SQL, params):
                facts.append((name, etype, name))
            for s, p, o in await conn.execute(_RELATIONS_SQL, params):
                facts.append((s, p, o))
    finally:
        await engine.dispose()
    return facts
