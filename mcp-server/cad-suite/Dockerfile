# CAD Suite — ONE merged container for all CAD capability (user decision 2026-09-11).
#
# Three services supervised in one image:
#   - text-to-cad MCP  :8004  (build123d STEP/STL/DXF generation, inspect,
#                              snapshot renders, parts catalog, DfAM facts)
#   - cad / EDP MCP    :8003  (2D engineering drawings: analyze_cad +
#                              cad_compose_drawing with domain packs)
#   - cad-viewer       :4178  (node browser 3D viewer for GLB/STEP/STL)
#
# Merging: one rebuild for everything CAD, one deploy unit for offline
# templates, shared OCP/cadpy/ezdxf layers instead of three copies. The MCP
# DNS names `text-to-cad` and `cad` survive via compose network aliases, so
# extensions_config.json URLs are unchanged.
#
# Build context is mcp-server/ (dockerfile: cad-suite/Dockerfile) so the three
# source trees COPY directly.
FROM python:3.12-slim-bookworm

# Restricted-network handling: reuse the backend's pip index mirror if set.
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8004 \
    CAD_DATA_ROOT=/data

WORKDIR /app

# apt layer 1 — libgl1 (OCP import on slim), CJK fonts (EDP PNG title blocks),
# curl/gnupg (nodesource). Layer ordered BEFORE pip so the heavy OCP wheel
# (~400MB+) stays cached if this layer ever changes — a reorder would force a
# full OCP re-download.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 curl ca-certificates gnupg \
        fonts-dejavu-core fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# Node 22 for the cad-viewer server (upstream ships node:22-alpine; merged
# image runs it on debian). Separate layer so OCP/pip caches survive node bumps.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# pip layer — the vendored engine (cadpy) is editable-installed from ./cad-skill,
# so cad-skill must COPY before pip. requirements.txt now also carries
# playwright (snapshot renders) and rtree (DfAM ray-cast thickness).
COPY text-to-cad-mcp/cad-skill ./cad-skill
COPY text-to-cad-mcp/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

# Chromium for the snapshot renderer (~300MB — the layer deliberately cut on
# 2026-06-24, restored 2026-09-11 for agent-side visual self-check). --with-deps
# pulls the libnss/libgbm/libasound family chromium needs on slim-bookworm.
# Render time itself is fully offline (route interception + inline three.js).
RUN python -m playwright install --with-deps chromium

# Code layers (baked, like today's per-service images; only /data bind-mounts).
COPY text-to-cad-mcp/server.py ./server.py
COPY text-to-cad-mcp/step-parts ./step-parts
COPY text-to-cad-mcp/dfam ./dfam
COPY cad-mcp ./cad-mcp
COPY cad-viewer/viewer ./viewer
COPY cad-suite/supervisor.py ./supervisor.py

EXPOSE 8003 8004 4178
CMD ["python", "supervisor.py"]
