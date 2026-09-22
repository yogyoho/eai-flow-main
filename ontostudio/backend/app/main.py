"""OntoStudio 本体建模系统独立后端.

EAI-CUSTOM: 自 backend/app/extensions/ 迁出独立(设计 docs/superpowers/specs/2026-09-17-ontostudio-standalone-design.md)。
Task 2 落地: JWT 鉴权中间件(app/auth.py) + MCP streamable-http 双端点(/mcp/ontology、/mcp/doc-graph)
+ CORS 显式 origin 白名单(env ONTOSTUDIO_CORS_ORIGINS, 默认 localhost:2026/3010)。

MCP transport 选型(S1 Task 2 报告项): **streamable-http**（官方 SDK mcp 1.30
`StreamableHTTPSessionManager`, stateless + json_response）而非 legacy HTTP+SSE
(`SseServerTransport`)。理由: ① extensions_config.json 远程条目既有惯例即 type:"http" 单 URL
(knowledge-factory/cad/text-to-cad 同款, harness http 通道在本仓库 Docker 拓扑已验证);
② 单端点免 /sse+/messages/ 成对挂载; ③ MCP spec 已以 Streamable HTTP 取代 HTTP+SSE。
两 server 低层实现零改动——`app.ontology.mcp.server` / `app.doc_graph.mcp.server` 原样复用,
仅传输层从 stdio 换 streamable-http(各 mcp.py 的 stdio main() 保留不动)。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from app import auth
from app.db import ensure_tables
from app.doc_graph.mcp import server as doc_graph_mcp_server
from app.doc_graph.routers import router as doc_graph_router
from app.ontology.formal import router as formal_router
from app.ontology.mcp import server as ontology_mcp_server
from app.ontology.registry_content import router as registry_content_router
from app.ontology.routers import router as ontology_router

_DEFAULT_CORS_ORIGINS = "http://localhost:2026,http://localhost:3010"

logger = logging.getLogger(__name__)


class MCPAsgiGuard:
    """ASGI 包装: MCP 端点鉴权(X-Internal-Auth / Bearer JWT, 见 app.auth.mcp_request_authorized)
    后转交 StreamableHTTPSessionManager。挂成 starlette Route 的非函数 endpoint(裸 ASGI),
    方法显式 GET/POST/DELETE(streamable-http 三动词)。

    manager 由 lifespan 每次 startup (re)bind——SDK 限定 StreamableHTTPSessionManager.run()
    只能调用一次, 故 manager 不能在 create_app 建一次复用(多轮 TestClient/uvicorn --reload
    会二次进 lifespan)。"""

    def __init__(self) -> None:
        self._manager: StreamableHTTPSessionManager | None = None

    def bind(self, manager: StreamableHTTPSessionManager) -> None:
        self._manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            if not auth.mcp_request_authorized(headers):
                body = b'{"detail":"Unauthorized"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("latin-1")),
                            (b"www-authenticate", b"Bearer"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        if self._manager is None:  # pragma: no cover — lifespan 未启动的防御分支
            body = b'{"detail":"MCP transport not started"}'
            await send({"type": "http.response.start", "status": 503, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("latin-1"))]})
            await send({"type": "http.response.body", "body": body})
            return
        await self._manager.handle_request(scope, receive, send)


def _cors_origins() -> list[str]:
    """显式 origin 白名单（T1 评审遗留收紧: `["*"]`+credentials 是无效组合）。"""
    raw = os.getenv("ONTOSTUDIO_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    ontology_guard = MCPAsgiGuard()
    doc_graph_guard = MCPAsgiGuard()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # EAI-CUSTOM(Task 3): 本服务接管 dg_* 建表（app/db.py 预告的「Task 3 起本服务接管」）。
        # 降级而非致命：DB 未起时服务仍能提供 registry/kernel 等无库读路径，逐请求的 DB 失败
        # 各自报错；若在此硬失败，启动瞬间的 DB 抖动（或离线部署里 postgres 尚未 healthy）
        # 会整服务拒起——代价大于收益。建表失败留 WARNING, 不静默。
        try:
            await ensure_tables()
        except Exception as exc:  # noqa: BLE001 — 任何失败都不阻断启动, 但必须留痕
            logger.warning("dg_* 建表失败（服务降级启动；DB 恢复后重启即补建）: %s", exc)
        # stateless: 每 HTTP 请求新 transport, 免会话簿记, 容器重启零残留;
        # json_response: 响应为纯 JSON。manager.run() 初始化 TaskGroup, 一次性 → 每次
        # startup 新建实例（缺 run() 则 handle_request 抛 "Task group is not initialized",
        # TestClient 须 with 上下文触发 lifespan）。
        ontology_mcp = StreamableHTTPSessionManager(app=ontology_mcp_server, stateless=True, json_response=True)
        doc_graph_mcp = StreamableHTTPSessionManager(app=doc_graph_mcp_server, stateless=True, json_response=True)
        ontology_guard.bind(ontology_mcp)
        doc_graph_guard.bind(doc_graph_mcp)
        async with ontology_mcp.run(), doc_graph_mcp.run():
            yield

    app = FastAPI(title="OntoStudio 本体建模系统", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(ontology_router)
    app.include_router(registry_content_router)
    app.include_router(formal_router)
    app.include_router(doc_graph_router)

    # MCP streamable-http 双端点（Route 精确匹配; harness 条目 url 即此路径, 无尾斜杠）
    app.routes.append(Route("/mcp/ontology", ontology_guard, methods=["GET", "POST", "DELETE"], name="mcp_ontology"))
    app.routes.append(Route("/mcp/doc-graph", doc_graph_guard, methods=["GET", "POST", "DELETE"], name="mcp_doc_graph"))

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "ontostudio-backend"}

    return app


app = create_app()
