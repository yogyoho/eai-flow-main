FROM python:3.12-slim-bookworm

WORKDIR /app

# Build-time network here is slow; uv's default 30s per-request timeout is too
# short for the larger wheels (temporalio, botocore).
ENV UV_HTTP_TIMEOUT=300

COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /usr/local/bin/

COPY pyproject.toml requirements.txt ./
RUN uv pip install --system -r requirements.txt

COPY . .

EXPOSE 3004
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3004"]
