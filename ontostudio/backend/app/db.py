"""SQLAlchemy declarative base（独立服务本地）+ 建表入口.

EAI-CUSTOM: 自 backend/app/extensions/database.py 抽出 Base 定义——ontology 包迁出独立
（设计: docs/superpowers/specs/2026-09-17-ontostudio-standalone-design.md）后，
dg_* ORM 模型（app/doc_graph/tables.py）需本地 Base 注册元数据（lint / 导入侧链路）。
本服务直连同一 extensions 库（dg_* 表暂留，零数据迁移）。
建表职责（2026-09-22 Task 3 兑现）: 本服务 lifespan 启动时调 ensure_tables()——原先那句
「过渡期由 gateway init_db 建表」随搬迁失效（dg_* 已不在 gateway 的 Base 上），见下。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


async def ensure_tables() -> None:
    """建缺失表（幂等）——由 app/main.py 的 lifespan 在启动时调用。

    EAI-CUSTOM(2026-09-22 Task 3): 2026-09-17 搬迁把 dg_* 模型从 gateway 的 Base 摘到本地
    Base（本模块），「过渡期仍由 gateway create_all 建表」的过渡安排随之失效——现存 4 张 dg_*
    表是搬迁前建的，而新表（dg_action_audit）在活库里根本不存在。本函数兑现那句「Task 3 起
    本服务接管」：建表从此是启动路径的一部分，离线部署走同一段代码（无人手步骤）。

    **已知限制（有意，非疏漏）**：create_all 只建**缺失的表**，不做 schema 变更——既有表加列/
    改类型/加约束仍须人工迁移。这是本仓既有取向（gateway init_db 同样只 create_all），但必须
    写明：别把本函数当成自动迁移。

    引擎照 app/doc_graph/ingest.py 既有模式（create_async_engine + NullPool，URL 取
    connectors._ext_url 单一真源）。`_ext_url` 用函数内延迟 import——app.ontology.__init__
    会反手 import app.doc_graph.tables（即本模块的 Base），模块级 import 成环。
    """
    from app.ontology.connectors import _ext_url

    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            # create_all 是同步 API，异步引擎下须 run_sync 包一层
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
