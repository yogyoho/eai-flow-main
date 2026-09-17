"""Ontology 统一语义层（市场/分析数据域，只读投影）.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md (R4)
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md
"""

# EAI-CUSTOM: doc_graph 构建侧表模型在此导入, 注册进 Base.metadata 使 create_all 能建 dg_* 表
# （lint 同样经此链路注册）。过渡期建表仍由 gateway init_db 承担（dg_* 暂留 extensions 库）,
# S1 Task 3 容器化后由本服务接管。
from app.doc_graph import tables  # noqa: F401
