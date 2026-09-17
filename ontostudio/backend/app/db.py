"""SQLAlchemy declarative base（独立服务本地）.

EAI-CUSTOM: 自 backend/app/extensions/database.py 抽出 Base 定义——ontology 包迁出独立
（设计: docs/superpowers/specs/2026-09-17-ontostudio-standalone-design.md）后，
dg_* ORM 模型（app/doc_graph/tables.py）需本地 Base 注册元数据（lint / 导入侧链路）。
引擎/会话管理仍属 gateway；本服务直连同一 extensions 库（dg_* 表暂留，零数据迁移）。
建表职责: 过渡期沿用 gateway 启动 create_all；Task 3 容器化时由本服务 lifespan 接管。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass
