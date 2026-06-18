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
        "entry_point": "database",
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
        "entry_point": "api",
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
    {
        "name": "示例工具(演示接线)",
        "type": "tool",
        "description": "演示插件→MCP 接线:启用后 Agent 获得 demo_greet 工具。",
        "entry_point": "app.extensions.plugin.builtin.demo_mcp",
        "config_schema": {"type": "object"},
    },
    {
        "name": "报告图表生成器",
        "type": "output",
        "description": (
            "当用户需要在报告中嵌入数据图表时:\n"
            "1. 先从数据源获取数据(list_datasets / query_dataset / query_data_source)。\n"
            "2. 用 Python(matplotlib 或 plotly)生成图表(柱状图/折线图/饼图/散点图)。\n"
            "3. 保存为 PNG 或 HTML,嵌入报告对应章节。\n"
            "注意:图表应标注数据来源、单位、时间范围。"
        ),
        "config_schema": {"type": "object"},
    },
]


async def seed_builtin_plugins(db: AsyncSession) -> None:
    """Insert built-in plugins if not present; sync entry_point on existing. Idempotent."""
    added = 0
    updated = False
    for p in BUILTIN_PLUGINS:
        name = p["name"]
        version = p.get("version", "1.0.0")
        existing = (
            await db.execute(select(Plugin).where(Plugin.name == name, Plugin.version == version))
        ).scalars().first()
        if existing:
            # sync entry_point (added after initial seed) so data_connector wiring works
            ep = p.get("entry_point")
            if ep != existing.entry_point:
                existing.entry_point = ep
                updated = True
            desc = p.get("description")
            if desc and desc != existing.description:
                existing.description = desc
                updated = True
            continue
        db.add(
            Plugin(
                name=name,
                type=p["type"],
                version=version,
                description=p.get("description"),
                entry_point=p.get("entry_point"),
                config_schema=p.get("config_schema"),
                permissions=[],
                status="registered",
            )
        )
        added += 1
    if added or updated:
        await db.commit()
    if added:
        logger.info("Seeded %d built-in plugins", added)
