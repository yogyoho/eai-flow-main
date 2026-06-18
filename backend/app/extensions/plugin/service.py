"""Plugin service: config validation, instance CRUD, API key issuance.

Metadata only — no plugin execution this round."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import shutil
from pathlib import Path

import jsonschema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import ApiKey, DataSource, Plugin, PluginInstance
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
        PluginService.sync_skill_registration(inst, plugin)
        await PluginService.sync_data_source_registration(db, inst, plugin)
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
        PluginService.sync_skill_registration(inst, plugin)
        await PluginService.sync_data_source_registration(db, inst, plugin)
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
        PluginService.sync_skill_registration(inst, plugin, remove=True)
        await PluginService.sync_data_source_registration(db, inst, plugin, remove=True)
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

    # ── plugin→DataSource wiring (data_connector) ──

    @staticmethod
    async def sync_data_source_registration(
        db: AsyncSession, instance, plugin, *, remove: bool = False
    ) -> None:
        """Provision/remove a DataSource for a type=data_connector plugin.

        Install (active) → upsert a DataSource (name=plugin.name, type=plugin.entry_point,
        connection_config=instance.config). Disable/uninstall → remove it. name-based linkage.
        The DataSource reuses the generic data-source layer (datasets, query_dataset, UI).
        """
        should = (
            not remove
            and getattr(instance, "status", None) == "active"
            and plugin.type == "data_connector"
            and plugin.entry_point in ("database", "api", "file", "gis")
        )
        existing = (
            await db.execute(select(DataSource).where(DataSource.name == plugin.name))
        ).scalars().first()
        if should:
            if existing is None:
                db.add(
                    DataSource(
                        name=plugin.name,
                        type=plugin.entry_point,
                        connection_config=instance.config or {},
                        description=plugin.description,
                        auth_type="none",
                        sync_mode="manual",
                    )
                )
            else:
                existing.type = plugin.entry_point
                existing.connection_config = instance.config or {}
                if plugin.description:
                    existing.description = plugin.description
            await db.flush()
        elif existing is not None:
            await db.delete(existing)
            await db.flush()

    # ── plugin→Skill wiring (output type) ──

    @staticmethod
    def sync_skill_registration(instance, plugin, *, remove: bool = False) -> None:
        """Register/remove an output plugin as a skill (SKILL.md in skills/custom/).

        Install → write SKILL.md + enable in extensions_config.skills → harness skills
        loader (mtime hot-reload) injects it into the agent's system prompt.
        Never raises — a failure only logs a warning.
        """
        logger = logging.getLogger(__name__)
        skill_name = f"plugin-{plugin.id}"
        should = (
            not remove
            and getattr(instance, "status", None) == "active"
            and plugin.type == "output"
        )
        try:
            from deerflow.config import get_app_config

            cfg_path = get_app_config().skills.path
            if cfg_path:
                skills_custom = Path(cfg_path) / "custom"
            else:
                skills_custom = Path(__file__).resolve().parents[4] / "skills" / "custom"
            skill_dir = skills_custom / skill_name

            if should:
                skill_dir.mkdir(parents=True, exist_ok=True)
                body = (plugin.description or "").strip() or f"# {plugin.name}"
                content = (
                    f"---\n"
                    f"name: {skill_name}\n"
                    f"description: {plugin.name}: {plugin.description or ''}\n"
                    f"license: MIT\n"
                    f"---\n\n"
                    f"{body}\n"
                )
                (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
            elif skill_dir.exists():
                shutil.rmtree(skill_dir)

            config_path = ExtensionsConfig.resolve_config_path()
            if config_path and config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)
                skills_cfg = data.setdefault("skills", {})
                if should:
                    skills_cfg[skill_name] = {"enabled": True}
                else:
                    skills_cfg.pop(skill_name, None)
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                reload_extensions_config()
        except Exception as e:
            logger.warning("sync_skill_registration failed for plugin %s: %s", plugin.id, e)

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
