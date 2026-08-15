"""Ontology 双 connector（postgres_ext 直连 / data_source 托管连接）.

复用边界（plan D9）：
- `assert_readonly_select` 从 data_source/service.py **import 单一真源**（安全规则不复制）
- 连接管道自建：`run_readonly_query` 无绑定参数支持（`conn.execute(text(sql))`），
  故照抄其 NullPool + `SET TRANSACTION READ ONLY` 每查询引擎模式，params 透传 text()。
- 断连绝不静默空结果：fetch 抛 ConnectorError，availability() 显式 available:false。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.extensions.config import get_extensions_config
from app.extensions.data_source.service import _build_db_url, assert_readonly_select
from app.extensions.ontology.schemas import AccessConfig

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """连接/执行失败（显式，不静默空结果）。"""


def _ext_url() -> str:
    """扩展库 URL：MCP 子进程 env 不继承(bug-698) → ONTOLOGY_DB_URL 显式覆盖优先。"""
    return os.environ.get("ONTOLOGY_DB_URL") or get_extensions_config().database.url


class OntologyConnectors:
    """实现 engine.ConnectorResolver 协议。"""

    # ── 协议实现 ──

    async def fetch(self, access: AccessConfig, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        guarded = assert_readonly_select(sql)  # D9: 安全单一真源（LIMIT 追加与引擎显式 LIMIT 共存）
        url = await self._resolve_url(access)
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                try:
                    await conn.execute(text("SET TRANSACTION READ ONLY"))
                except Exception:  # 与 data_source 模式一致：非事务型驱动容忍
                    pass
                res = await conn.execute(text(guarded), params or {})
                return [dict(row) for row in res.mappings().all()]
        except Exception as e:
            raise ConnectorError(f"{access.path}:{access.source_id or access.table} 查询失败: {e}") from e
        finally:
            await engine.dispose()

    def same(self, a: AccessConfig, b: AccessConfig) -> bool:
        """两侧是否同一物理库（决定单 SQL join 还是分块应用侧 join）。"""
        if a.path != b.path:
            return False
        if a.path == "postgres_ext":
            return True  # 扩展库单库
        return a.source_id == b.source_id  # 同一托管数据源

    # ── 可用性（断连显式 available:false，绝不静默空结果） ──

    async def availability(self, accesses: list[AccessConfig]) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for access in accesses:
            key = f"{access.path}:{access.source_id or access.table}"
            if key in out:
                continue
            try:
                await self.fetch(access, "SELECT 1")
                out[key] = True
            except ConnectorError as e:
                logger.warning("ontology connector unavailable: %s (%s)", key, e)
                out[key] = False
        return out

    # ── URL 解析 ──

    async def _resolve_url(self, access: AccessConfig) -> str:
        if access.path == "postgres_ext":
            return _ext_url()
        if access.path == "data_source":
            cfg = await self._source_config(access.source_id or "")
            return _build_db_url(cfg)
        raise ConnectorError(f"未知 access path: {access.path}")

    async def _source_config(self, source_id: str) -> dict:
        """data_source 名称 → connection_config（经扩展库查 data_sources 行）。"""
        url = _ext_url()
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                try:
                    await conn.execute(text("SET TRANSACTION READ ONLY"))
                except Exception:
                    pass
                res = await conn.execute(text("SELECT connection_config FROM data_sources WHERE name = :n LIMIT 1"), {"n": source_id})
                row = res.mappings().first()
        finally:
            await engine.dispose()
        if not row:
            raise ConnectorError(f"data_source '{source_id}' 未注册")
        cfg = row["connection_config"] or {}
        if not isinstance(cfg, dict) or not cfg.get("database"):
            raise ConnectorError(f"data_source '{source_id}' 非 database 类型或连接配置缺失")
        return cfg
