# OntoStudio Backend Dockerfile — standalone FastAPI service (ontology + doc_graph)
# EAI-CUSTOM (S1 Task 3): 自 backend/app/extensions 迁出独立服务（设计:
# docs/superpowers/specs/2026-09-17-ontostudio-standalone-design.md）。风格照
# backend/Dockerfile：uv 基础镜像拷贝 + pyproject/uv.lock 先拷后 sync --frozen（层缓存
# 友好）。单阶段简化：依赖全为预编译 wheel（fastapi/uvicorn[standard]/asyncpg/mcp 等，
# 无源码编译项），无需 build-essential/Node/Docker CLI。
# 构建上下文 = ontostudio/backend/（compose build.context 指向本目录）。

# UV source image (override for restricted networks that cannot reach ghcr.io)
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.1
FROM ${UV_IMAGE} AS uv-source

FROM python:3.12-slim-bookworm

# PyPI index 可覆盖（受限网络；与 gateway 构建参数同名同默认）
ARG UV_INDEX_URL=https://pypi.org/simple

COPY --from=uv-source /uv /uvx /usr/local/bin/

# UTF-8 locale prevents UnicodeEncodeError on Chinese/emoji content（照 backend/Dockerfile）
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 依赖清单先行拷贝：pyproject/uv.lock 不变时本层缓存命中。
COPY pyproject.toml uv.lock ./

# --no-dev: pyproject 设 default-groups=["dev"]，须显式关掉（pytest/ruff 不进生产镜像）。
# --no-install-project: 项目为 virtual 包（uv.lock source=virtual），显式跳过自装。
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_INDEX_URL="${UV_INDEX_URL}" UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-600}" \
    uv sync --frozen --no-dev --no-install-project

# 应用代码（.dockerignore 已排除 .venv/tests/缓存 —— .venv 是 Windows 二进制，严禁入镜像）
COPY app ./app

EXPOSE 8005

# --no-sync: 运行时零网络依赖（离线容器必需；照 gateway CMD 惯例）
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
