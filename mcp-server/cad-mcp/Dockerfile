# CAD Comprehension MCP Server — standalone container.
# Phase 1: DXF-only (ezdxf + matplotlib). No ODA, no native CAD kernel.
# Shares the deer-flow data volume (mounted at /data) to read uploads / write outputs.
FROM python:3.12-slim-bookworm

# Mirror the backend Dockerfile's restricted-network handling: allow a pip index
# override (e.g. an Aliyun mirror) via build arg.
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8003

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt
COPY server.py .

EXPOSE 8003
CMD ["python", "server.py"]
