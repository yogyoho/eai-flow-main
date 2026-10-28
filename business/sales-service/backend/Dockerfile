FROM python:3.12-slim-bookworm

WORKDIR /app

# Build-time network here is slow; uv's default 30s per-request timeout is too
# short for the larger wheels (temporalio, botocore).
ENV UV_HTTP_TIMEOUT=300

# Mirror the default package index for fast builds in China (e.g. the Tsinghua
# mirror passed via compose). uv honours UV_DEFAULT_INDEX; PIP_INDEX_URL keeps
# the build-arg name consistent with the workflow-backend image.
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV UV_DEFAULT_INDEX=$PIP_INDEX_URL

COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /usr/local/bin/

COPY pyproject.toml requirements.txt ./
RUN uv pip install --system -r requirements.txt

COPY . .

EXPOSE 3004
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3004"]
