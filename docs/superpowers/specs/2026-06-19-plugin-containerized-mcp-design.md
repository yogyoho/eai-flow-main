# 插件市场容器化 MCP + Compose 编排 + 独立生命周期管理 — 技术方案

> 日期: 2026-06-19 | 状态: 设计草稿 | 驱动案例: cad-mcp 的接入过程暴露了插件系统与真实 MCP 服务器开发的脱节

## 1. 问题陈述

cad-mcp 的开发过程完成了 6 步手动操作,插件页面**一步都没参与**:

```
手动步骤                          插件系统当前能做的
──────────────────────────────────────────────────────────
1. 写 server.py (FastMCP)         ✗ 没有
2. 写 Dockerfile                  ✗ 只支持 stdio(同进程,无容器)
3. 写 test_analyze.py             ✗ 没有
4. 改 docker-compose-dev.yaml     ✗ 不动 compose
5. 改 extensions_config.json      △ 能生成 stdio 模板,不生成 http
6. 构建镜像 + 启动容器 + 重启 gw   ✗ 不管理容器生命周期
```

**根因**: `sync_mcp_registration`(service.py:109-154) 只能生成同进程 stdio 的 MCP 配置。它假设 MCP 服务器跑在 gateway 容器内,所以只需要 `command + args`。真实世界的能力(需要独立容器、独立依赖、独立生命周期)不在它的设计范围内。

**目标**: 让插件系统能安装、管理、卸载**容器化 MCP 服务器**。cad-mcp 是第一个真实案例,也是迁移验证目标。

## 2. 架构概览

```
用户点击 "安装" (插件页面 → 市场 Tab → 某个 tool 插件 → 安装)
  │
  ▼
POST /api/extensions/plugins/instances  {plugin_id: "...", config: {...}}
  │
  ▼
PluginService.create_instance()
  │
  ├─ 1. 查 Plugin 记录 → 拿到 manifest 路径 (如 plugins/cad-comprehension/plugin.yaml)
  │
  ├─ 2. 读 plugin.yaml → 解析 container 段的配置(port, env, volumes, build)
  │
  ├─ 3. 生成 per-plugin compose 文件 (如 .deer-flow/plugins/compose/cad.yml)
  │     services:
  │       plugin-<id>:
  │         build: {context, dockerfile, args}
  │         container_name: eai-flow-plugin-<id>
  │         environment: {...}
  │         volumes: [...]
  │         networks: [eai-flow-net]
  │         restart: unless-stopped
  │
  ├─ 4. docker compose up -d --build   (通过 gateway 的 DooD /var/run/docker.sock)
  │
  ├─ 5. 写 extensions_config.json mcpServers
  │     "plugin_<id>": {
  │       "enabled": true,
  │       "type": "http",
  │       "url": "http://plugin-<id>:<port>/mcp"
  │     }
  │
  ├─ 6. 写 PluginInstance 行 (status=active, container_id=...)
  │
  └─ 返回 { id, status: "active", mcp_url: "http://..." }

Gateway 重启(或 mtime 热量新)后 → Agent 获得新工具
```

卸载是这个过程的逆操作(compose down → 删除配置 → 删除行)。

## 3. 插件 Manifest (`plugin.yaml`)

每个容器化插件在目录根下携带一个声明文件。以下基于 cad-mcp 的真实结构反推:

```yaml
# plugins/cad-comprehension/plugin.yaml
name: cad-comprehension
version: "1.0.0"
type: tool                    # tool = MCP 服务器(目前唯一需要容器的)
transport: container          # stdio | container (新增字段)
description: "CAD 解析(DXF parse + rasterize),供消防/环评报告使用"
author: "deer-flow"
icon: "📐"                    # 市场卡片图标(可选)

mcp:
  name: cad                   # extensions_config.json 中的 key;Agent 看到 cad_analyze_cad
  port: 8003                  # 容器内监听端口
  path: /mcp                  # streamable-http 路径(默认 /mcp)
  description: "CAD comprehension (DXF parse + rasterize) for fire-protection/EIA drawing ingestion"

container:
  build:
    dockerfile: Dockerfile    # 相对于 plugin 目录的路径
    args:                     # 构建参数,可以引用 env/compose 变量
      PIP_INDEX_URL: "${UV_INDEX_URL:-https://pypi.org/simple}"
  environment:                # 注入容器的环境变量
    MCP_HOST: "0.0.0.0"      # 固定: 容器间网络需要 0.0.0.0
    CAD_DATA_ROOT: "/data"
  volumes:                    # 挂载卷,可引用 ${DEER_FLOW_HOME} 等 compose 变量
    - "${DEER_FLOW_HOME:-../backend/.deer-flow}:/data:rw"
  # networks 和 restart 由系统自动注入(加入 eai-docker_eai-flow-net, restart=unless-stopped)
```

### manifest 字段职责

| 字段 | 用途 | 谁消费 |
|---|---|---|
| `name` / `version` / `type` | 与现有 Plugin 模型对齐 | DB Plugin 表(seed 时写入) |
| `transport` | 决定走 stdio 旧路径还是 container 新路径 | PluginService.create_instance() |
| `mcp.name` | extensions_config.json 的 key | extensions_config → agent 工具名 |
| `mcp.port` / `mcp.path` | 生成 `url: "http://<container_name>:<port><path>"` | extensions_config |
| `container.build` | docker compose service 的 build 段 | docker compose up --build |
| `container.environment` | docker compose service 的 environment 段 | docker compose |
| `container.volumes` | docker compose service 的 volumes 段 | docker compose |

**设计原则**: manifest 里只放插件开发者需要声明的信息。`container_name`、`networks`、`restart` 等运维字段由 PluginService 自动生成,不暴露给插件开发者。

## 4. 插件目录结构

以 cad-mcp 为例,迁移后的目录:

```
plugins/cad-comprehension/
├── plugin.yaml              ← 清单(系统读的唯一入口)
├── Dockerfile               ← 构建
├── requirements.txt          ← 依赖
├── server.py                 ← MCP 服务器
├── test_analyze.py           ← 自检
└── README.md                 ← 文档
```

**关键规则**:
- `plugin.yaml` 必须在目录根下,文件名固定
- `container.build.dockerfile` 是相对于 plugin 目录的路径(通常是 `Dockerfile`,也可以是 `Dockerfile.gpu` 等)
- 插件目录可以是 git 跟踪的(如 `plugins/cad-comprehension/`——在 repo 中随版本发布),也可以是上传的(如 `.skill` ZIP 解压后放到 `plugins/<name>/`)

## 5. 安装流程(详细步骤)

```
POST /api/extensions/plugins/instances
  body: {plugin_id: UUID, config: {可选, 覆盖 manifest 的环境变量}}

PluginService.create_instance():
│
├─ Step 1: 校验
│   plugin = await get_plugin(db, plugin_id)
│   if plugin.transport != "container": → 走旧路径(stdio),return
│
├─ Step 2: 读 manifest
│   manifest = load_manifest(plugin.manifest_path)  # 插件安装时可把路径存进 Plugin 模型
│   校验 manifest 必填字段
│
├─ Step 3: 生成 per-plugin compose 文件
│   compose_yaml = render_compose_service(plugin, manifest, instance)
│   写入: {DEER_FLOW_PLUGIN_DIR}/compose/plugin-{instance.id}.yml
│
│   生成的 compose 内容:
│   ┌─────────────────────────────────────────────
│   │ services:
│   │   plugin-<instance_id>:
│   │     build:
│   │       context: <plugin_dir>
│   │       dockerfile: <manifest.container.build.dockerfile>
│   │       args: <manifest.container.build.args>
│   │     container_name: eai-flow-plugin-<instance_id>
│   │     environment:
│   │       <manifest.container.environment>
│   │       MCP_PORT: "<manifest.mcp.port>"    # 自动注入
│   │     volumes:
│   │       <manifest.container.volumes>
│   │     networks:
│   │       - eai-flow-net
│   │     restart: unless-stopped
│   │ networks:
│   │   eai-flow-net:
│   │     external: true
│   │     name: eai-docker_eai-flow-net
│   └─────────────────────────────────────────────
│
├─ Step 4: 构建镜像 + 启动容器
│   compose_file = .deer-flow/plugins/compose/plugin-{instance.id}.yml
│   # gateway 有 DooD(/var/run/docker.sock 已挂载),可以调 docker compose
│   subprocess.run([
│       "docker", "compose", "-p", "eai-docker",
│       "-f", compose_file,
│       "up", "-d", "--build"
│   ], check=True, timeout=300)
│
├─ Step 5: 注册 MCP 服务器
│   key = f"plugin_{plugin.id}"
│   写 extensions_config.json:
│     mcpServers[key] = {
│       "enabled": true,
│       "type": "http",                              ← 容器化=type:http
│       "url": f"http://plugin-{instance.id}:{manifest.mcp.port}{manifest.mcp.path}",
│       "command": null, "args": [], "env": {}, "cwd": null,
│       "headers": {}, "oauth": null,
│       "description": manifest.mcp.description
│     }
│   reload_extensions_config()
│
├─ Step 6: 持久化
│   instance.status = "active"
│   instance.config = {..., "container_name": "eai-flow-plugin-{id}"}
│   db.add(instance)
│   await db.commit()
│
└─ 返回 PluginInstanceResponse
```

### 容器命名约定

生成的容器名为 `eai-flow-plugin-{instance_id前8位}`,与现有命名对齐(`eai-flow-cad`、`eai-flow-collab`)。

### 网络

所有插件容器加入同一个外部网络 `eai-docker_eai-flow-net`,所以:
- Gateway 可以通过容器名解析到插件(`http://plugin-<id>:8003/mcp`)
- 所有插件和 gateway 在同一个二层网络中

### 构建镜像的 pip 源

`manifest.container.build.args` 中声明 `${UV_INDEX_URL:-...}`,PluginService 不修改它——由 compose 的环境变量解析。开发环境如 `.env` 中设置了 `UV_INDEX_URL`,构建时自动使用镜像源。

## 6. 卸载流程

```
DELETE /api/extensions/plugins/instances/{instance_id}

PluginService.delete_instance():
│
├─ Step 1: 停容器 + 删镜像
│   compose_file = .deer-flow/plugins/compose/plugin-{id}.yml
│   subprocess.run(["docker", "compose", "-p", "eai-docker",
│                    "-f", compose_file, "down", "--rmi", "local"])
│   os.remove(compose_file)
│
├─ Step 2: 注销 MCP 服务器
│   从 extensions_config.json 删 mcpServers[f"plugin_{plugin.id}"]
│   reload_extensions_config()
│
├─ Step 3: 删 DB 行
│   await db.delete(instance)
│   await db.commit()
│
└─ 返回 204
```

## 7. 生命周期管理(UI 暴露的操作)

| 用户操作 | 后端动作 | Docker 命令 |
|---|---|---|
| 启用/禁用 | toggle instance.status + 重写 extensions_config | `docker compose start/stop` |
| 查看日志 | 返回最近 N 行 | `docker compose logs --tail 100` |
| 查看状态 | 返回容器运行状态 | `docker compose ps --format json` |
| 重新配置 | update instance.config, 重新生成 compose, 重启容器 | `docker compose up -d` |
| 重启 | 直接重启容器 | `docker compose restart` |

### 新增 API 端点

```
GET  /api/extensions/plugins/instances/{id}/status    → {status, container, uptime}
GET  /api/extensions/plugins/instances/{id}/logs?tail=50 → {logs: "..."}
POST /api/extensions/plugins/instances/{id}/restart   → 204
```

## 8. 数据库 Schema 变更

在 `Plugin` 模型中新增 1 个字段:

```python
# app/extensions/models.py — Plugin 模型
class Plugin(Base):
    ...
    entry_point = Column(String, nullable=True)      # 旧字段: stdio 时存模块路径
    transport = Column(String, default="stdio")      # ★ 新增: "stdio" | "container"
    manifest_path = Column(String, nullable=True)    # ★ 新增: 容器插件 manifest 文件路径
```

在 `PluginInstance` 模型中新增:

```python
class PluginInstance(Base):
    ...
    container_name = Column(String, nullable=True)   # ★ 新增: 运行时容器名
    compose_file = Column(String, nullable=True)     # ★ 新增: per-instance compose 文件路径
```

`seed.py` 中的 BUILTIN_PLUGINS 新增 cad-comprehension 条目:

```python
{
    "name": "CAD 解析",
    "type": "tool",
    "transport": "container",          # ★
    "manifest_path": "plugins/cad-comprehension/plugin.yaml",  # ★
    "entry_point": None,               # 容器插件不需要
    "description": "解析 DXF 图纸,提取管径/消火栓立管/图层/尺寸等结构化事实。",
}
```

## 9. Compose 集成(dev 和 prod 的差异)

### 开发环境

dev 启动(`scripts/docker.sh start`)已经运行了 `docker-compose-dev.yaml`。插件不在这个文件里——它们由 PluginService 在安装时独立启动,使用同一个 Docker 项目名(`eai-docker`)和同一个网络(`eai-docker_eai-flow-net`)。

```
make docker-start
  → docker compose -f docker-compose-dev.yaml up -d
     (nginx + frontend + gateway + provisioner + cad)

用户安装插件 "X"
  → PluginService creates:
     docker compose -f .deer-flow/plugins/compose/plugin-{id}.yml up -d --build
     (plugin-X joins eai-docker_eai-flow-net)
```

**关键优势**: 主 compose 文件不受污染。插件独立管理,dev 启动流程不变。

### 生产环境

同模式,只是 compose 文件路径和网络名来自生产环境的 compose(`docker-compose.yaml`)。

### compose 文件目录

```
.deer-flow/plugins/
├── compose/                          # 运行时生成的 compose 文件
│   ├── plugin-abc123.yml             # 每个实例一个文件
│   └── plugin-def456.yml
└── instances/                        # 插件实例的工作数据(可选)
    └── abc123/
        └── ...
```

## 10. 与现有体系的关系

```
插件安装后的效果                      对用户可见的位置
──────────────────────────────────────────────────────────────
tool(container)  → 启动容器           Settings → Tools Tab(新 MCP 服务器,可启用/禁用)
                 → 注册 type:http MCP  插件页面 → 已安装 Tab(可管理:启用/禁用/日志/卸载)

tool(stdio)      → 注册 type:stdio MCP  Settings → Tools Tab(同上,但 container_name 为空)
                                      插件页面 → 已安装 Tab

data_connector   → 创建 DataSource 行   数据源页面(现有流程,不变)

output           → 创建 SKILL.md +       Settings → Skills Tab(现有流程,不变)
                   extensions_config 注册
```

插件页面成为一个**统一的安装和管理入口**,安装后的能力在各个管理页面中都可查看和管理,但**安装这个动作只在插件页面完成**。

## 11. 迁移: cad-mcp 作为第一个容器化插件

当前 cad-mcp 在 `mcp-server/cad-mcp/` 中,手动在 compose 中:

1. 在 `plugins/cad-comprehension/` 下创建 `plugin.yaml`(按 §3 的格式)
2. 把 `server.py` / `Dockerfile` / `requirements.txt` / `test_analyze.py` 移到 `plugins/cad-comprehension/` 下
3. 从 `docker-compose-dev.yaml` 中移除 cad 服务
4. 在 seed.py 中添加 cad-comprehension 的 Plugin 行
5. 在 UI 中点击"安装 CAD 解析"
6. 验证:
   - 容器 `eai-flow-plugin-{id}` 启动,日志显示 Uvicorn running
   - extensions_config 中出现 `plugin_xxx` 的 MCP 条目(type:http)
   - Gateway 重启后,Agent 获得 `plugin_xxx_analyze_cad` 工具
7. 从 compose 中移除旧的 cad 服务定义

## 12. 实现阶段

| 阶段 | 内容 | 改动文件 |
|---|---|---|
| **Phase 1: 核心接线** | Plugin 模型加 transport/manifest_path; manifest 解析; compose 生成; docker compose up/down; extensions_config 注册/注销 | models.py, service.py, schemas.py, routers.py(新增 status/logs/restart 端点) |
| **Phase 2: 前端集成** | 插件卡片显示 transport; 安装后显示容器状态; 已安装 Tab 加日志/状态/重启按钮; 卸载确认对话框 | PluginMarketplace.tsx, PluginCard.tsx, api.ts |
| **Phase 3: cad-mcp 迁移** | 移动文件到 plugins/cad-comprehension/; 写 plugin.yaml; 改 seed.py; 验证端到端 | mcp-server/cad-mcp/* → plugins/cad-comprehension/*, docker-compose-dev.yaml(移除 cad 服务) |
| **Phase 4: 错误处理** | docker 故障时的友好错误消息; 构建失败→显示 pip 输出; 超时保护; 孤儿容器清理 | service.py |
