# Procurement Service Backend Dockerfile
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /usr/local/bin/

# Copy pyproject.toml and uv.lock for dependency management
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY . .

# Expose port
EXPOSE 3001

# Run the application
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3001"]
