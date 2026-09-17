"""OntoStudio 本体建模系统独立后端.

EAI-CUSTOM: 自 backend/app/extensions/ 迁出独立(设计 docs/superpowers/specs/2026-09-17-ontostudio-standalone-design.md)。
鉴权中间件 Task 2 落地(当前无鉴权——仅本地/内网开发态)；MCP SSE 端点 Task 2 落地。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.doc_graph.routers import router as doc_graph_router
from app.ontology.routers import router as ontology_router


def create_app() -> FastAPI:
    app = FastAPI(title="OntoStudio 本体建模系统", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])  # Task 2 收紧
    app.include_router(ontology_router)
    app.include_router(doc_graph_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "ontostudio-backend"}

    return app


app = create_app()
