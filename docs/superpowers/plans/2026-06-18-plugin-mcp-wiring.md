# 插件→MCP 接线(type=tool)+ demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `type=tool` 插件启用时把其 `entry_point` 注册成 `extensions_config.mcpServers` 一条,Agent 经 function calling 立即获得其工具;禁用/卸载摘除。消除插件孤岛。

**Architecture:** plugin service 加 `sync_mcp_registration(instance, plugin, *, remove=False)`——读 raw `extensions_config.json`(保留其它 key)→改 `mcpServers["plugin_<id>"]`→写回→`reload_extensions_config()` 触发 harness mtime 热加载。在 create/update/delete_instance 钩子里调。附 `builtin/demo_mcp.py` 极简 MCP server + seed 一条示例插件端到端验证。

**Tech Stack:** Python 3.12 · FastAPI · `mcp.server` (stdio) · `deerflow.config.extensions_config`。pytest。

**约束:** 提交用 pathspec(活跃分支有并发 agent);后端测试从 `backend/` 跑 `PYTHONPATH=. uv run pytest`;sync 文件写失败仅 log warning 不抛;env 由 `instance.config` 平铺(字符串直传、其余 `json.dumps`)。

---

## 文件结构

新增:
- `backend/app/extensions/plugin/builtin/__init__.py`(空)
- `backend/app/extensions/plugin/builtin/demo_mcp.py`(demo MCP server)
- `backend/tests/test_plugin_mcp_wiring.py`(sync + demo 测试)

修改:
- `backend/app/extensions/plugin/service.py` — 加 `sync_mcp_registration` + 3 个钩子 + 顶部 import
- `backend/app/extensions/plugin/seed.py` — 加"示例工具"插件(entry_point=demo_mcp)
- `backend/app/extensions/plugin/routers.py`(无改;钩子在 service)— 不改
- `CLAUDE.md` — 加"扩展能力 3 层模型(北极星)"小节

---

## Task 1: `sync_mcp_registration` + 测试

**Files:** plugin/service.py · tests/test_plugin_mcp_wiring.py(新建)

- [ ] **Step 1: 写失败测试** `backend/tests/test_plugin_mcp_wiring.py`:

```python
"""Tests for plugin→MCP wiring (sync_mcp_registration) + demo module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.extensions.plugin.service import PluginService


def _plugin(type_="tool", entry="app.extensions.plugin.builtin.demo_mcp"):
    m = MagicMock()
    m.id = "pid"
    m.name = "示例工具"
    m.type = type_
    m.entry_point = entry
    m.description = "演示"
    return m


def _instance(status="active", config=None):
    m = MagicMock()
    m.id = "iid"
    m.status = status
    m.config = config if config is not None else {}
    return m


def _write_cfg(tmp_path, servers=None):
    cfg = tmp_path / "extensions_config.json"
    cfg.write_text(json.dumps({"mcpServers": servers or {}}), encoding="utf-8")
    return cfg


class TestSyncMcpRegistration:
    def test_active_tool_writes_entry(self, tmp_path):
        cfg = _write_cfg(tmp_path)
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ):
            PluginService.sync_mcp_registration(_instance(), _plugin())
        data = json.loads(cfg.read_text(encoding="utf-8"))
        entry = data["mcpServers"]["plugin_pid"]
        assert entry["enabled"] is True
        assert entry["args"] == ["-m", "app.extensions.plugin.builtin.demo_mcp"]
        assert entry["command"] == "/app/backend/.venv/bin/python"
        assert entry["cwd"] == "/app/backend"

    def test_inactive_removes_entry(self, tmp_path):
        cfg = _write_cfg(tmp_path, {"plugin_pid": {"enabled": True}})
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ):
            PluginService.sync_mcp_registration(_instance(status="disabled"), _plugin())
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "plugin_pid" not in data["mcpServers"]

    def test_force_remove_even_if_active(self, tmp_path):
        cfg = _write_cfg(tmp_path, {"plugin_pid": {"enabled": True}})
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ):
            PluginService.sync_mcp_registration(_instance(status="active"), _plugin(), remove=True)
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "plugin_pid" not in data["mcpServers"]

    def test_non_tool_type_not_registered(self, tmp_path):
        cfg = _write_cfg(tmp_path)
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ):
            PluginService.sync_mcp_registration(_instance(), _plugin(type_="data_connector"))
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "plugin_pid" not in data["mcpServers"]

    def test_idempotent_double_register(self, tmp_path):
        cfg = _write_cfg(tmp_path)
        for _ in range(2):
            with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
                "app.extensions.plugin.service.reload_extensions_config"
            ):
                PluginService.sync_mcp_registration(_instance(), _plugin())
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert list(data["mcpServers"].keys()).count("plugin_pid") == 1

    def test_write_failure_does_not_raise(self, tmp_path):
        cfg = _write_cfg(tmp_path)
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ), patch("builtins.open", side_effect=OSError("disk full")):
            PluginService.sync_mcp_registration(_instance(), _plugin())  # no raise
```

- [ ] **Step 2: 运行确认失败**
`cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_mcp_wiring.py -q`
Expected: AttributeError — `sync_mcp_registration` 不存在。

- [ ] **Step 3a: 顶部 import** — 在 `backend/app/extensions/plugin/service.py` 顶部 import 区加(与现有 import 并列):
```python
import json
import logging

from deerflow.config.extensions_config import ExtensionsConfig, reload_extensions_config
```
(`json`/`logging` 若已导入则不重复。)

- [ ] **Step 3b: sync 方法** — 在 `PluginService` 类内(`delete_instance` 方法之后、`list_api_keys` 之前)加:
```python
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
```

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_mcp_wiring.py -q`
Expected: 6 passed。

- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/plugin/service.py backend/tests/test_plugin_mcp_wiring.py
git commit -m "feat(plugin): sync_mcp_registration — wire type=tool plugins to MCP"
```

---

## Task 2: 钩子(create/update/delete 调 sync)+ 路由测试

**Files:** plugin/service.py · tests/test_plugin_mcp_wiring.py(追加)

- [ ] **Step 1: 追加测试** — 在 `test_plugin_mcp_wiring.py` 末尾加(验证钩子调用 sync):
```python
class TestHooksCallSync:
    @pytest.mark.asyncio
    async def test_create_instance_calls_sync(self):
        db = AsyncMock()
        plugin = _plugin()
        req = MagicMock(); req.plugin_id = "pid"; req.config = {}
        inst = _instance()
        with patch.object(PluginService, "get_plugin", AsyncMock(return_value=plugin)), patch.object(
            PluginService, "validate_config", MagicMock(return_value=None)
        ), patch.object(PluginService, "sync_mcp_registration") as sync:
            db.add = MagicMock(); db.flush = AsyncMock()
            await PluginService.create_instance(db, req, user_id=None)
        sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_instance_calls_sync_remove(self):
        db = AsyncMock()
        inst = _instance()
        plugin = _plugin()
        db.get = AsyncMock(return_value=inst)
        db.delete = AsyncMock(); db.flush = AsyncMock()
        with patch.object(PluginService, "get_plugin", AsyncMock(return_value=plugin)), patch.object(
            PluginService, "sync_mcp_registration"
        ) as sync:
            await PluginService.delete_instance(db, "iid")
        sync.assert_called_once()
        assert sync.call_args.kwargs.get("remove") is True
```
(需在文件顶部加 `from unittest.mock import AsyncMock, MagicMock, patch`,若已有则不重复。)

- [ ] **Step 2: 运行确认失败**
`cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_mcp_wiring.py::TestHooksCallSync -q`
Expected: AssertionError(sync 未被调)。

- [ ] **Step 3: 加钩子** — 在 `backend/app/extensions/plugin/service.py`:

`create_instance` 在 `await db.flush()` 之后、`return inst` 之前加:
```python
        PluginService.sync_mcp_registration(inst, plugin)
```

`update_instance` 在 `await db.flush()` 之后、`return inst` 之前加:
```python
        plugin = await PluginService.get_plugin(db, inst.plugin_id)
        PluginService.sync_mcp_registration(inst, plugin)
```
(注意:`update_instance` 原 `return None`(inst 不存在)分支保持不变,只在成功路径末尾加钩子。)

`delete_instance` 在 `await db.delete(inst)` 之前加(取 plugin)+ 之后加(sync remove):
```python
        plugin = await PluginService.get_plugin(db, inst.plugin_id)
        await db.delete(inst)
        await db.flush()
        PluginService.sync_mcp_registration(inst, plugin, remove=True)
        return True
```

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_mcp_wiring.py -q`
Expected: 8 passed(6 + 2)。

- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/plugin/service.py backend/tests/test_plugin_mcp_wiring.py
git commit -m "feat(plugin): hook sync_mcp_registration into create/update/delete instance"
```

---

## Task 3: demo MCP 模块 + seed 示例插件

**Files:** plugin/builtin/__init__.py(新) · plugin/builtin/demo_mcp.py(新) · plugin/seed.py · tests/test_plugin_mcp_wiring.py(追加)

- [ ] **Step 1: 写失败测试** — 在 `test_plugin_mcp_wiring.py` 末尾加:
```python
class TestDemoModule:
    def test_demo_module_exposes_greet(self):
        from app.extensions.plugin.builtin import demo_mcp

        names = {t.name for t in demo_mcp.TOOLS}
        assert "demo_greet" in names

    def test_seed_includes_demo_plugin(self):
        from app.extensions.plugin import seed as seed_mod

        demo = [p for p in seed_mod.BUILTIN_PLUGINS if p["name"].startswith("示例工具")]
        assert demo and demo[0]["type"] == "tool"
        assert demo[0]["entry_point"] == "app.extensions.plugin.builtin.demo_mcp"
```

- [ ] **Step 2: 运行确认失败**
`cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_mcp_wiring.py::TestDemoModule -q`
Expected: ImportError(demo_mcp 不存在)。

- [ ] **Step 3a: `builtin/__init__.py`** — 新建空文件 `backend/app/extensions/plugin/builtin/__init__.py`。

- [ ] **Step 3b: `demo_mcp.py`** — 新建 `backend/app/extensions/plugin/builtin/demo_mcp.py`:
```python
"""Demo MCP server — proves plugin→MCP wiring end-to-end.

Registered as a `type=tool` plugin (entry_point=this module). When the plugin
instance is enabled, sync_mcp_registration writes it into extensions_config.mcpServers,
and the agent gains the `demo_greet` tool via function calling.
"""

from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

TOOLS = [
    Tool(
        name="demo_greet",
        description="演示工具(来自插件 MCP):返回一句问候。证明插件→MCP→function calling 通路已接通。",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "要问候的名字"}},
            "required": ["name"],
        },
    )
]


async def _handle_demo_greet(arguments: dict) -> list[TextContent]:
    name = arguments.get("name", "世界")
    return [TextContent(type="text", text=f"你好,{name}!这是来自插件 MCP 的演示工具。")]


server = Server("plugin_demo")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "demo_greet":
        return await _handle_demo_greet(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3c: seed.py 加示例插件** — 在 `backend/app/extensions/plugin/seed.py` 的 `BUILTIN_PLUGINS` 列表末尾加一项:
```python
    {
        "name": "示例工具(演示接线)",
        "type": "tool",
        "description": "演示插件→MCP 接线:启用后 Agent 获得 demo_greet 工具。",
        "entry_point": "app.extensions.plugin.builtin.demo_mcp",
        "config_schema": {"type": "object"},
    },
```
并在 `seed_builtin_plugins` 的 `Plugin(...)` 构造里把 `entry_point` 传进去(若构造里还没有 entry_point 形参,加上 `entry_point=p.get("entry_point")`)。

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_mcp_wiring.py -q`
Expected: 10 passed(8 + 2)。

- [ ] **Step 5: import 冒烟**
`cd backend && PYTHONPATH=. uv run python -c "from app.extensions.plugin.builtin import demo_mcp; print([t.name for t in demo_mcp.TOOLS])"`
Expected: `['demo_greet']`

- [ ] **Step 6: 提交**
```bash
git add backend/app/extensions/plugin/builtin/__init__.py backend/app/extensions/plugin/builtin/demo_mcp.py backend/app/extensions/plugin/seed.py backend/tests/test_plugin_mcp_wiring.py
git commit -m "feat(plugin): demo MCP module + seeded tool plugin (end-to-end wiring)"
```

---

## Task 4: CLAUDE.md 北极星 3 层模型

**Files:** CLAUDE.md

- [ ] **Step 1: 加小节** — 在 `CLAUDE.md` 的 "### Backend: Harness / App Split" 小节之后(或 Architecture 段末尾)加:
```markdown
### Extension Capability: 3-Layer Model (North Star)

Capability reaches the agent through exactly **3 primitives**: **MCP tools**, **Skills**, **custom sub-agents**. Anything else is a management/packaging layer that must wire into these primitives, or it's a silo.

- **Data source** = a *managed MCP provider* (connection config + read-only query tools, built on MCP). Wired ✓.
- **Plugin** = a *packaging/distribution layer*: a `type=tool` plugin's `entry_point` is an MCP server module; enabling it registers it in `extensions_config.mcpServers` so the agent gains its tools via function calling (see `plugin/service.py::sync_mcp_registration`).
- **Rule**: before adding any new tab/module, ask which layer it lives in and which primitive it wires to. Don't build capability that doesn't reach the agent through MCP/Skills/sub-agents.
```

- [ ] **Step 2: 提交**
```bash
git add CLAUDE.md
git commit -m "docs: north-star 3-layer extension model (primitives / managed provider / packaging)"
```

---

## Task 5: 落地验证

- [ ] **Step 1: 全量插件测试**
`cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_models.py tests/test_plugin_service.py tests/test_plugin_routers.py tests/test_plugin_mcp_wiring.py -q`
Expected: 全绿。

- [ ] **Step 2: 重启 gateway(seed 新插件 + 代码生效)**
`docker compose -p eai-docker restart gateway && sleep 18`

- [ ] **Step 3: 示例插件已 seed + demo 模块可启**
```bash
PG=$(docker ps --format "{{.Names}}" | grep -iE "postgres.*ext" | head -1)
docker exec "$PG" psql -U agentflow -d agentflow -c "SELECT name, type, entry_point FROM plugins WHERE name LIKE '示例工具';"
```
Expected: 1 行,type=tool,entry_point=`app.extensions.plugin.builtin.demo_mcp`。
```bash
docker compose -p eai-docker exec -T -w /app/backend gateway /app/backend/.venv/bin/python -c "from app.extensions.plugin.builtin import demo_mcp; print([t.name for t in demo_mcp.TOOLS])"
```
Expected: `['demo_greet']`。

- [ ] **Step 4: 端到端(人工,经 UI/API)** — 安装+启用"示例工具"实例 → 检查 `extensions_config.json` 出现 `plugin_<id>` 条目 → 在对话里 Agent 能用 `demo_greet` → 禁用 → 条目消失、工具消失。(人工确认 Agent 行为;可用 `docker exec` 直接看 extensions_config.json 验证条目写入。)

---

## Self-Review

- **Spec 覆盖**:§3.1 sync → Task 1;§3.3 钩子 → Task 2;§3.4 demo+seed → Task 3;§3.5 北极星文档 → Task 4;§7 验收 → Task 5。全覆盖。
- **占位符**:无 TBD;每步完整代码;sync/env/钩子/demo/seed 全具体。
- **类型一致**:`sync_mcp_registration(instance, plugin, *, remove=False)` 签名在 Task1 定义、Task2 钩子(remove=True)一致;mcpServers key `plugin_{plugin.id}` 一致;demo entry_point `app.extensions.plugin.builtin.demo_mcp` 在 seed/demo/测试一致。
- **边界**:sync 在 app 层(plugin service),导入 `deerflow.config.extensions_config`(app→deerflow 允许);不碰 harness 内部,只读写 extensions_config.json + reload。
