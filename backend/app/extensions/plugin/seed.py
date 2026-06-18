"""Seed built-in plugins into the registry. Idempotent."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import Plugin

logger = logging.getLogger(__name__)

BUILTIN_PLUGINS = [
    {
        "name": "地质数据连接器",
        "type": "data_connector",
        "description": "对接地质钻孔数据库,拉取地层信息。",
        "config_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "title": "主机地址"},
                "port": {"type": "integer", "default": 5432, "title": "端口"},
                "database": {"type": "string", "title": "数据库名"},
            },
            "required": ["host", "database"],
        },
    },
    {
        "name": "环境监测连接器",
        "type": "data_connector",
        "description": "对接在线监测平台,获取实时监测数据。",
        "config_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "title": "API 地址"}},
            "required": ["url"],
        },
    },
    {
        "name": "CAD 文件预览",
        "type": "tool",
        "description": "解析 DWG/DXF,生成预览图和元数据。",
        "config_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string", "title": "文件路径"}},
        },
    },
    {
        "name": "GIS 数据可视化",
        "type": "tool",
        "description": "加载 Shapefile/GeoJSON,在报告中嵌入地图。",
        "config_schema": {
            "type": "object",
            "properties": {"layer_url": {"type": "string", "title": "图层地址"}},
        },
    },
]


async def seed_builtin_plugins(db: AsyncSession) -> None:
    """Insert built-in plugins if not present. Idempotent by (name, version)."""
    added = 0
    for p in BUILTIN_PLUGINS:
        name = p["name"]
        version = p.get("version", "1.0.0")
        existing = await db.execute(
            select(Plugin).where(Plugin.name == name, Plugin.version == version)
        )
        if existing.scalars().first():
            continue
        db.add(
            Plugin(
                name=name,
                type=p["type"],
                version=version,
                description=p.get("description"),
                config_schema=p.get("config_schema"),
                permissions=[],
                status="registered",
            )
        )
        added += 1
    if added:
        await db.commit()
        logger.info("Seeded %d built-in plugins", added)
