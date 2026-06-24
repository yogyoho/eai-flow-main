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
# Fonts for the matplotlib PNG preview (edp/render.py rasterize). python:3.12-slim
# ships NO fonts, so without these the PNG has geometry but no text — incl. the CJK
# title block / 标高 / 标注. DejaVu = ASCII; WenQuanYi Zen Hei = CJK. The DXF itself
# is unaffected (TEXT entities render via the viewer's fonts). Layer ordered before
# pip so font install stays cached across code-only rebuilds.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-wqy-zenhei && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt
COPY server.py .
# Engineering Drawing Platform: domain-agnostic core + domain packs (declarative
# assets). See PLATFORM_SPEC.md.
COPY edp/ ./edp/
COPY domains/ ./domains/

EXPOSE 8003
CMD ["python", "server.py"]
