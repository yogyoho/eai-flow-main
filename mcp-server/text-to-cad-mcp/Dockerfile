# text-to-cad MCP Server — standalone container.
# Phase 1: build123d STEP/STL generation from agent-supplied source.
# Keeps heavy CAD deps (build123d + OCP/OpenCascade native libs) out of the
# gateway image so gateway startup stays fast. Mirrors mcp-server/cad-mcp.
FROM python:3.12-slim-bookworm

# Restricted-network handling: reuse the backend's pip index mirror if set.
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8004

WORKDIR /app
# OCP (OpenCascade) needs libGL at import on slim images. Install BEFORE the
# pip layer so the heavy OCP wheel (~400MB+) stays cached if this apt layer
# ever changes — otherwise a reorder would force a full OCP re-download.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt
COPY server.py .

EXPOSE 8004
CMD ["python", "server.py"]
