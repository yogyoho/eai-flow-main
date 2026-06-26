# eai-flow-ocr — standalone OCR service for contract price analysis (v2 Phase 0).
# Scanned-contract table extraction: pdf2image + OpenCV table-line detection +
# RapidOCR. Keeps heavy OCR/onnxruntime + poppler OUT of the gateway image so
# gateway startup stays fast. Called over HTTP (POST /ocr) by the
# contract_price gateway extension and the contract-price-analysis skill.
# Mirrors mcp-server/text-to-cad-mcp / cad-mcp build conventions.
FROM python:3.12-slim-bookworm

# Restricted-network handling: reuse the backend's pip index mirror if set
# (e.g. https://pypi.tuna.tsinghua.edu.cn/simple — see cerebrum bug-cad-002).
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONUNBUFFERED=1 \
    OCR_HOST=0.0.0.0 \
    OCR_PORT=8010

WORKDIR /app
# Restricted-network: swap debian apt sources to Tsinghua mirror FIRST.
# deb.debian.org / fastly CDN is unreachable here (DNS resolves but connect
# refused), so a bare apt-get update fails to locate poppler. The pypi mirror
# is handled below via PIP_INDEX_URL. python:3.12-slim-bookworm uses DEB822
# format at sources.list.d/debian.sources (fall back to legacy sources.list).
RUN (sed -i 's|http://deb.debian.org|http://mirrors.tuna.tsinghua.edu.cn|g; s|http://security.debian.org|http://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null \
      || sed -i 's|http://deb.debian.org|http://mirrors.tuna.tsinghua.edu.cn|g; s|http://security.debian.org|http://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null \
      || true) \
    && apt-get update && apt-get install -y --no-install-recommends \
      poppler-utils libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt
COPY schemas.py ocr_engine.py server.py ./

EXPOSE 8010
CMD ["python", "server.py"]
