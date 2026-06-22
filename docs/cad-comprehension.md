# CAD 解析内容理解 — 设计与操作手册

> 版本: Phase 1 (DXF-only)  |  日期: 2026-06-19  |  状态: 已部署并端到端验证

## 1. 架构概览

```
用户的 DWG/DXF  上传(前端 UploadsMiddleware)
       │
       ▼
  Agent 拿到虚拟路径 /mnt/user-data/uploads/cad.dxf
       │
       │  调 MCP 工具 cad_analyze_cad(file_path="...")
       ▼
  Gateway (MultiServerMCPClient) ──http──▶  eai-flow-cad 容器 (独立, port 8003)
                                               │
                                               │  ezdxf 解析 (~2s)
                                               │  结构化事实 JSON
                                               │  + 可选栅格 PNG (~80s, opt-in)
                                               ▼
  Agent 拿到 {status, facts, raster_png?, warnings?}
       │
       │  将 facts 喂给 消防/环评 合规技能
       ▼
  Office-Word MCP / docmgr → 带图纸感知的 Word 报告
```

**关键设计决策:**
- CAD 工具跑在**独立容器**(`eai-flow-cad`),不是 gateway 容器。gateway 镜像零膨胀、启动时间不变。
- MCP 传输 = `streamable-http`(uri `http://cad:8003/mcp`),因为 stdio 仅限同进程树。
- 开发编排 = `docker/docker-compose-dev.yaml`(不是 extensions overlay——`scripts/docker.sh:16` 只加载 dev 文件)。
- Phase 1 只接受 DXF(DWG 需上游 AutoCAD DXFOUT 转换;ODA File Converter 延后)。

## 2. 文件清单

| 文件 | 作用 |
|---|---|
| `mcp-server/cad-mcp/server.py` | FastMCP 服务器,单一工具 `analyze_cad` |
| `mcp-server/cad-mcp/Dockerfile` | `python:3.12-slim` + ezdxf + matplotlib + mcp |
| `mcp-server/cad-mcp/requirements.txt` | ezdxf>=1.4, matplotlib>=3.8, mcp>=1.2 |
| `mcp-server/cad-mcp/test_analyze.py` | 自检(解析 + 虚拟路径解析 + 错误路径) |
| `mcp-server/cad-mcp/README.md` | 运行、路径契约、限制 |
| `docker/docker-compose-dev.yaml` | `cad` 服务定义(第 186-222 行) |
| `extensions_config.json` | `mcpServers.cad` 条目(type: http, url: `http://cad:8003/mcp`) |

## 3. 数据流详解

### 3.1 Agent → MCP 工具调用

```
Agent 被 UploadsMiddleware 告知: /mnt/user-data/uploads/cad.dxf (虚拟路径)
Agent calls: cad_analyze_cad(file_path="/mnt/user-data/uploads/cad.dxf")
                    ↑
                    工具名带 cad_ 前缀——MultiServerMCPClient 的 tool_name_prefix=True
                    把 analyze_cad 变成 cad_analyze_cad (避免跨服务器重名)
```

### 3.2 路径解析(_resolve_path, server.py L45-65)

```
/mnt/user-data/... (Agent 传的虚拟路径)
       │
       ▼  工具内 _resolve_path()
       │  1. Path.exists()? → 直接用(物理路径)
       │  2. 包含 /mnt/user-data/? → glob CAD_DATA_ROOT/users/*/threads/*/user-data/<rest>
       │     ponytail: glob 假设文件名跨线程唯一; 线程名冲突时传物理路径消除歧义
       ▼
/data/users/{uid}/threads/{tid}/user-data/uploads/cad.dxf   ← 真实文件
       │
       │  CAD_DATA_ROOT=/data, 挂载源 = ${DEER_FLOW_HOME}(主机上 backend/.deer-flow)
       ▼
  ezdxf.readfile() → 解析
```

### 3.3 结构化事实提取

从 DXF 中提取(确定性,零幻觉):

| 字段 | 来源 | 示例 |
|---|---|---|
| `entity_count` | modelspace 实体数 | 34709 |
| `entity_counts` | 按 DXF 类型统计 | LINE:16656, INSERT:5999, TEXT:4182... |
| `layers[]` | 图层名 + 每层实体数 | WALL:5393, 器械:574... |
| `pipe_diameters[]` | TEXT/MTEXT 中的 DN\d+ 正则 | DN100:437, DN50:277... |
| `hydrant_risers[]` | TEXT/MTEXT 中的 XL-?\d+ 正则 | XL-1:10, XL-2:13... |
| `axis_dimensions_mm_sample[]` | DIMENSION.get_measurement() | [6500, 53000, 4000...] |
| `extent` | $EXTMIN/$EXTMAX(header) 或 bbox.extents(fast=True) | 904660 x 580178 mm |
| `text_samples[]` | 前 25 条 TEXT/MTEXT | ["DN100", "XL-1", "DN70"...] |

**编码:ezdxf 正确解码 GBK 中文为 Unicode** (已验证: `器械` = U+5668 U+68B0)。
控制台显示乱码是终端渲染问题,不是数据损坏——Agent 收到的 JSON(UTF-8)含合法中文。

### 3.4 栅格化(可选,opt-in)

```
rasterize=True → _rasterize(): matplotlib + ezdxf Frontend → PNG
  ~80s (34k 实体图纸)
  输出: 输入文件同级目录 .preview.png (如 cad.preview.png)
```

## 4. 运维指南

### 4.1 构建 + 启动(开发环境)

```bash
# 构建镜像 + 启动 cad 容器(仅 cad,不影响其他服务)
cd docker
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  docker compose -p eai-docker -f docker-compose-dev.yaml up -d --build cad

# 检查容器状态
docker ps --filter name=eai-flow-cad
# 预期: eai-flow-cad   Up ... (健康)

# 检查日志
docker logs eai-flow-cad
# 预期: Uvicorn running on http://0.0.0.0:8003 (Press CTRL+C to quit)

# 验证 MCP 服务可达
docker exec deer-flow-gateway python -c "
import urllib.request
try: r=urllib.request.urlopen('http://cad:8003/mcp',timeout=5); print('HTTP',r.status)
except Exception as e: print(type(e).__name__,e)
"
# 预期: HTTP 406 (正常——MCP 期望 POST,非 200 GET 说明服务在跑)

# 验证工具暴露
docker exec eai-flow-cad python -c "
import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
async def main():
    async with streamablehttp_client('http://localhost:8003/mcp') as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
asyncio.run(main())
"
# 预期: ['analyze_cad']
```

### 4.2 启用 + 接线(Agent 获取工具)

```bash
# 1. 启用 MCP 服务器(如未启用)
# 编辑 extensions_config.json → mcpServers.cad.enabled = true
# (已预置该条目,默认 enabled: true)

# 2. 重启 gateway(使其重新构建 agent 工具集)
cd docker
docker compose -p eai-docker -f docker-compose-dev.yaml restart gateway

# 3. 验证 Agent 拿到工具
docker exec deer-flow-gateway sh -c "cd /app/backend && PYTHONPATH=. .venv/bin/python -c \"
import asyncio
from deerflow.mcp.tools import get_mcp_tools
async def main():
    tools = await get_mcp_tools()
    cad = [t for t in tools if 'cad' in t.name.lower()]
    print('cad tools:', [t.name for t in cad])
asyncio.run(main())
\""
# 预期: cad tools: ['cad_analyze_cad']
```

### 4.3 停用 / 清理

```bash
# 停用(暂不暴露给 Agent)
# extensions_config.json → mcpServers.cad.enabled = false
# docker compose -p eai-docker -f docker/docker-compose-dev.yaml restart gateway

# 停止容器(释放资源)
docker compose -p eai-docker -f docker/docker-compose-dev.yaml stop cad

# 完全删除(镜像 + 容器)
docker compose -p eai-docker -f docker/docker-compose-dev.yaml down cad
docker rmi eai-docker-cad
```

### 4.4 自检(本地,不需要 Docker)

```bash
cd mcp-server/cad-mcp
pip install -r requirements.txt
CAD_FIXTURE=D:\aiproj\knowledge\cad.dxf python test_analyze.py
# 预期输出:
#   all self-checks passed
#   (含虚拟路径解析测试,pytest 风格断言)
```

## 5. API 参考: `analyze_cad`

### Agent 可见名称

`cad_analyze_cad` (网关的 `tool_name_prefix=True` 机制)

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `file_path` | str | — | 文件路径。支持: (1) agent 虚拟路径 `/mnt/user-data/uploads/X.dxf` (工具内自动解析) (2) 容器内物理绝对路径 |
| `rasterize` | bool | `false` | 是否生成 PNG 预览。~80s/大图,仅在 VLM 符号识别步骤开启 |

### 返回(JSON)

成功:
```json
{
  "status": "ok",
  "file": "/mnt/user-data/uploads/cad.dxf",
  "facts": {
    "dxf_version": "AC1018",
    "codepage": null,
    "entity_count": 34709,
    "entity_counts": {"LINE": 16656, "INSERT": 5999, "LWPOLYLINE": 4539, "TEXT": 4182, "DIMENSION": 1787, ...},
    "layers": [{"name": "0", "entities": 6250}, {"name": "WALL", "entities": 5393}, ...],
    "pipe_diameters": [{"size": "DN100", "count": 437}, ...],
    "hydrant_risers": [{"id": "XL-2", "count": 13}, ...],
    "axis_dimensions_mm_sample": [6500, 53000, 4000, ...],
    "text_samples": ["DN100", "XL-1", ...],
    "extent": {"min": [...], "max": [...], "width_mm": 904659.9, "height_mm": 580178.3}
  },
  "raster_png": "/data/users/.../cad.preview.png",   // 仅 rasterize=true 时
  "warnings": []                                       // 暂为空(编码已确认正常)
}
```

错误(含类型帮助信息):
```json
{"status": "error", "error": "unsupported_format", "file": "x.dwg",
 "suffix": ".dwg", "hint": "Phase 1 accepts .dxf only. Convert .dwg to .dxf via AutoCAD DXFOUT, then retry."}
```
```json
{"status": "error", "error": "file_not_found", "file": "/mnt/user-data/uploads/missing.dxf"}
```
```json
{"status": "error", "error": "parse_failed", "file": "...", "detail": "DXF parse failed: ..."}
```

## 6. Agent 端使用示例

用户在 deer-flow 聊天界面:

```
用户: 上传 cad.dxf
      解析这张给排水图纸,提取管径和消防立管

Agent 内部:
  1. UploadsMiddleware 注入: /mnt/user-data/uploads/cad.dxf
  2. 调用 cad_analyze_cad(file_path="/mnt/user-data/uploads/cad.dxf")
  3. 收到 facts: 34709 实体, 50 图层, DN100 主, XL-1..5
  4. 回答:
     "该图纸包含 34,709 个实体,分布在 50 个图层中。
      管道: DN100(437处) > DN50(277) > DN32(201) > DN25(144) > DN75(110)
      消防立管: XL-1(10处) XL-2(13处) XL-3..5(各9处)
      图纸范围: 905m × 580m
      主要图层: WALL(5393), PUB_DIM(2258), LGBZ(2134)
      需要我进一步检查哪些图层或标注?"
```

如需视觉识别(非标消防符号):
```
用户: 看看有没有消火栓

Agent 内部:
  1. cad_analyze_cad(file_path="...", rasterize=true)
  2. 收到 facts + raster_png 路径
  3. 用 view_image / vision 读 PNG,识别消火栓符号
  4. 结合 structured facts + 视觉识别结果回答
```

## 7. 已知限制(Phase 2 延后项)

| 限制 | 影响 | 何时加 |
|---|---|---|
| **DXF only**(不接受 DWG) | 用户必须先 AutoCAD DXFOUT 导出 DXF | 上游给不出 DXF 时,集成 ODA File Converter(Linux 二进制,再分发受限,需在 Dockerfile 里 curl 下载) |
| **无几何计算** | 疏散距离/防火分区面积/喷淋覆盖率等定量合规核查做不了 | Phase 2: 加 shapely + 合规映射(geometry_feasible → GB50016 条款) |
| **栅格 ~80s** | 大图开 rasterize=true 慢 | 按图层/视口切块;或用 ODA 自带的 PNG 导出(比 matplotlib 快很多) |
| **文件名字典冲突** | 虚拟路径解析 glob 假设文件名唯一;同线程同名文件会歧义 | 传线程上下文(context/thread_id)做精确解析 |
| **编码恢复** | 极少数 DXF 写入时真丢了 `$DWGCODEPAGE`→中文无法恢复 | ezdxf 已正确解码常见 GBK/GB2312;本环境 verified ok |

## 8. 关键参数速查

| 参数 | 位置 | 默认值 | 说明 |
|---|---|---|---|
| `MCP_TRANSPORT` | cad compose env | `streamable-http` | stdio / sse / streamable-http |
| `MCP_HOST` | cad compose env | `0.0.0.0` | 必须 `0.0.0.0`(容器间网络可达) |
| `MCP_PORT` | cad compose env | `8003` | |
| `MCP_PATH` | cad compose env | `/mcp` | streamable-http 路径,与 extensions_config url 一致 |
| `CAD_DATA_ROOT` | cad compose env | `/data` | 挂载点;`_resolve_path` 在此之下搜索线程目录 |
| `PIP_INDEX_URL` | cad compose build arg | `${UV_INDEX_URL:-https://pypi.org/simple}` | pip 镜像源(受限网络必须设为清华/阿里云等) |
| `UV_INDEX_URL` | `.env` 或命令行 | — | 后端 uv + cad pip 共用;永久设置在 `.env` 中 |
| `${DEER_FLOW_HOME}` | docker compose | — | 主机数据根目录;cad 挂载到 `/data` 以共享上传和输出 |

### 容器资源估算

| 指标 | 值 |
|---|---|
| 镜像大小 | ~350 MB(含 ezdxf + matplotlib + mcp + 传递依赖) |
| 内存(解析) | ~60 MB(34k 实体 DXF) |
| 内存(栅格) | ~250 MB(matplotlib 渲染) |
| 构建时间(含镜像) | ~2-4 min |
| 解析时间 | ~18s(34k 实体,含 bbox 计算); ~2s(不含 bbox) |
| 栅格时间 | ~80s(34k 实体, dpi=80) |
