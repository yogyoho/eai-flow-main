"""Plugin service: config validation, instance CRUD, API key issuance.

Metadata only — no plugin execution this round."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets

import jsonschema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import ApiKey, Plugin, PluginInstance
from app.extensions.plugin.schemas import ApiKeyCreate, PluginInstanceCreate, PluginInstanceUpdate
from deerflow.config.extensions_config import ExtensionsConfig, reload_extensions_config


class PluginService:
    # ── config validation ──

    @staticmethod
    def validate_config(plugin, config: dict) -> None:
        """Validate config against plugin.config_schema (JSON Schema). Raises
        jsonschema.ValidationError if invalid. No-op when schema is absent."""
        schema = plugin.config_schema
        if schema:
            jsonschema.validate(instance=config, schema=schema)

    # ── registry ──

    @staticmethod
    async def list_plugins(db: AsyncSession) -> list[Plugin]:
        result = await db.execute(select(Plugin).order_by(Plugin.name.asc()))
        return list(result.scalars().all())

    @staticmethod
    async def get_plugin(db: AsyncSession, plugin_id) -> Plugin | None:
        return await db.get(Plugin, plugin_id)

    # ── instances ──

    @staticmethod
    async def list_instances(db: AsyncSession, project_id=None) -> list[PluginInstance]:
        stmt = select(PluginInstance).order_by(PluginInstance.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create_instance(db: AsyncSession, req: PluginInstanceCreate, user_id=None) -> PluginInstance:
        plugin = await PluginService.get_plugin(db, req.plugin_id)
        if plugin is None:
            raise ValueError(f"插件不存在: {req.plugin_id}")
        PluginService.validate_config(plugin, req.config)
        inst = PluginInstance(
            plugin_id=plugin.id,
            plugin_name=plugin.name,
            plugin_type=plugin.type,
            project_id=req.project_id,
            config=req.config,
            status="active",
            created_by=user_id,
        )
        db.add(inst)
        await db.flush()
        PluginService.sync_mcp_registration(inst, plugin)
        return inst

    @staticmethod
    async def update_instance(db: AsyncSession, instance_id, req: PluginInstanceUpdate) -> PluginInstance | None:
        inst = await db.get(PluginInstance, instance_id)
        if inst is None:
            return None
        if req.config is not None:
            plugin = await PluginService.get_plugin(db, inst.plugin_id)
            if plugin is not None:
                PluginService.validate_config(plugin, req.config)
            inst.config = req.config
        if req.status is not None:
            inst.status = req.status
        await db.flush()
        plugin = await PluginService.get_plugin(db, inst.plugin_id)
        PluginService.sync_mcp_registration(inst, plugin)
        return inst

    @staticmethod
    async def delete_instance(db: AsyncSession, instance_id) -> bool:
        inst = await db.get(PluginInstance, instance_id)
        if inst is None:
            return False
        plugin = await PluginService.get_plugin(db, inst.plugin_id)
        await db.delete(inst)
        await db.flush()
        PluginService.sync_mcp_registration(inst, plugin, remove=True)
        return True

    # ── plugin→MCP wiring ──

    @staticmethod
    def sync_mcp_registration(instance, plugin, *, remove: bool = False) -> None:
        """Register/remove a type=tool plugin's MCP server in extensions_config.json.

        Idempotent. Never raises — a config write failure only logs a warning so
        plugin CRUD is not blocked by MCP-wiring trouble.
        """
        logger = logging.getLogger(__name__)
        key = f"plugin_{plugin.id}"
        should_register = (
            not remove
            and getattr(instance, "status", None) == "active"
            and plugin.type == "tool"
            and plugin.entry_point
        )
        try:
            path = ExtensionsConfig.resolve_config_path()
            if path is None or not path.exists():
                return
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            servers = data.setdefault("mcpServers", {})
            if should_register:
                env = {
                    k: (v if isinstance(v, str) else json.dumps(v))
                    for k, v in (instance.config or {}).items()
                }
                servers[key] = {
                    "enabled": True,
                    "type": "stdio",
                    "command": "/app/backend/.venv/bin/python",
                    "args": ["-m", plugin.entry_point],
                    "env": env,
                    "cwd": "/app/backend",
                    "url": None,
                    "headers": {},
                    "oauth": None,
                    "description": f"{plugin.name}: {plugin.description or ''}",
                }
            else:
                servers.pop(key, None)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            reload_extensions_config()
        except Exception as e:  # non-fatal: plugin data is already persisted
            logger.warning("sync_mcp_registration failed for plugin %s: %s", plugin.id, e)

    # ── API keys ──

    @staticmethod
    async def list_api_keys(db: AsyncSession) -> list[ApiKey]:
        result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def create_api_key(db: AsyncSession, req: ApiKeyCreate, user_id=None) -> tuple[ApiKey, str]:
        raw = secrets.token_urlsafe(32)
        rec = ApiKey(
            name=req.name,
            key_prefix=raw[:8],
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            scope=req.scope or [],
            project_id=req.project_id,
            created_by=user_id,
            expires_at=req.expires_at,
        )
        db.add(rec)
        await db.flush()
        return rec, raw

    @staticmethod
    async def delete_api_key(db: AsyncSession, key_id) -> bool:
        rec = await db.get(ApiKey, key_id)
        if rec is None:
            return False
        await db.delete(rec)
        await db.flush()
        return True
