"""Ontology 统一语义层（市场/分析数据域，只读投影）.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md (R4)
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md
"""

# EAI-CUSTOM: doc_graph 构建侧表模型在此导入, 使 gateway 启动 init_db 的
# Base.metadata.create_all 能建 dg_* 表（MCP 子进程与 lint 同样经此链路注册）。
from app.extensions.ontology.doc_graph import tables  # noqa: F401
