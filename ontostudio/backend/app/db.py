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

# 连接阶段超时（秒）。**必须有**：黑洞/丢包地址上 asyncpg 一直等（本机实测无 timeout = 21.5s，
# Linux TCP connect 可到 ~2 分钟），而这段窗口里 uvicorn 尚未进入服务状态 → 容器 healthcheck
# 失败、下游起不来。取 5 而非探针用的 2：探测只需确认可达，生产还要留出正常建表的裕度。
_CONNECT_TIMEOUT_S = 5

# 命令阶段超时（秒）——Task 5 Step 6 收口（计划 2026-09-22 Task 5「写路径韧性」）。
# 上面那个参数只界住**握手**：握手成功后 asyncpg 的 command_timeout 默认 None（无界），
# 链路被防火墙/NAT 静默掐断时只能等 TCP 自己发现（Windows keepalive 约 2 小时）——
# 即「启动楔死」失效模式的后移版本，连接阶段超时修不掉它。另一条路是 CREATE TABLE 需
# ACCESS EXCLUSIVE 锁，撞上并发 DDL/长事务会无限排队。
# 取 30 而非 60：本引擎 NullPool 且在同一次调用里 dispose，命令阶段只可能影响这**一次**
# create_all，而它的失败已被设计成非致命（WARNING + tables_ready=False）→ 误杀代价 ≈
# 一条 WARNING，故倾向早失败（这条取舍**不适用于写路径的命令阶段**：那边的超时会是用户
# 可见的 500，故 executor.py 只收口了握手、未收口命令阶段，见本文件末尾注释与计划
# Task 5 Step 6 报告）。
_COMMAND_TIMEOUT_S = 30


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
    connectors._ext_url 单一真源），另加 `_CONNECT_TIMEOUT_S` / `_COMMAND_TIMEOUT_S`
    （见常量处注释——没有前者，黑洞地址会把启动吊死到分钟级；没有后者，握手成功但链路
    被静默掐断的窗口内会等 TCP keepalive）。`_ext_url` 用函数内延迟 import——app.ontology.__init__
    会反手 import app.doc_graph.tables（即本模块的 Base），模块级 import 成环。

    **本函数被两个调用方复用**：app/main.py 的 lifespan，以及写路径的懒建
    （app/ontology/actions/executor.py）——建表只有这一条实现。
    """
    from app.ontology.connectors import _ext_url

    engine = create_async_engine(
        _ext_url(),
        poolclass=NullPool,
        connect_args={"timeout": _CONNECT_TIMEOUT_S, "command_timeout": _COMMAND_TIMEOUT_S},
    )
    try:
        async with engine.begin() as conn:
            # create_all 是同步 API，异步引擎下须 run_sync 包一层
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


# 写路径（app/ontology/actions/executor.py）自建引擎的超时收口——**两个阶段分开裁决**，
# 因为它们有「有没有合法的长等待」这一条本质差别（别再当一件事看）：
#
# | | 连接阶段（握手） | 命令阶段 |
# |---|---|---|
# | 有无合法长等待 | **无**——连不上就是连不上 | **有**——`SELECT ... FOR UPDATE` 撞上并发长事务时可以正当地等很久 |
# | 无超时的后果 | 请求永久挂起、占住 ASGI 任务（本机实测 21.5s，Linux 可到分钟级） | 同上，但那个等待可能是正当的 |
# | 误杀面 | **不存在** | 真实存在（30s 会把「等到后成功」变成用户可见的 500） |
# | 结论 | **Task 5 已补**：executor 的引擎传 `connect_args={"timeout": _CONNECT_TIMEOUT_S}` | **仍未收口**，留给 Task 6/7（暴露面）裁决 |
#
# 上面这条「连接阶段已补」不是顺手加的：本模块两处超时的理由都建立在「失败已是非致命
# （WARNING + tables_ready=False），误杀代价 ≈ 一条日志」之上，而写路径的同类失败是
# **用户可见的**——所以只有「没有合法等待、因而没有误杀面」的握手那一半能照搬过来，
# 命令阶段那一半必须由掌握暴露面取舍的人定。见计划 Task 5 Step 6 报告。
