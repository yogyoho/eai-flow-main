"""Ontology 统一语义层（市场/分析数据域，只读投影）.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md (R4)
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md
"""

# EAI-CUSTOM: doc_graph 构建侧表模型在此导入, 注册进 Base.metadata 使 create_all 能建 dg_* 表
# （lint 同样经此链路注册）。建表已由本服务接管: lifespan → app.db.ensure_tables()
# （2026-09-22 Task 3 兑现；此前「过渡期仍由 gateway init_db 承担」的说法随搬迁失效——dg_* 已
# 不在 gateway 的 Base 上, 那句话 2026-09-17 起就是空的）。
from app.doc_graph import tables  # noqa: F401
