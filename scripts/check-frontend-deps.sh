#!/usr/bin/env bash
# EAI-CUSTOM (bug-4240; supersedes the missing docker.sh subcommand, bug-1278):
# warn when host frontend/pnpm-lock.yaml differs from the lockfile baked into the
# running frontend image. Image deps are frozen at build time (node_modules is NOT
# bind-mounted on host=Windows), so drift silently keeps stale/mixed deps.
set -u
cd "$(dirname "$0")/.." || exit 1

# EAI-CUSTOM (2026-11-08 重新归类): business.yaml left the eai-docker chain
# (business subsystems now live in their own `eai-ext` group); this check only
# execs into the base `frontend` service, so 3 overlays suffice.
COMPOSE_FILES="-f docker-compose-dev.yaml -f docker-compose.extensions.yaml -f docker-compose.ragflow.yaml"

host_hash=$(sha256sum frontend/pnpm-lock.yaml | cut -d' ' -f1)
# MSYS_NO_PATHCONV: Git Bash would otherwise rewrite /app/... into a Windows path
# before it reaches the container (harmless no-op on Linux).
container_hash=$(cd docker && MSYS_NO_PATHCONV=1 docker compose -p eai-docker $COMPOSE_FILES exec -T frontend sha256sum /app/frontend/pnpm-lock.yaml 2>/dev/null | cut -d' ' -f1)

if [ -z "$container_hash" ]; then
    echo "WARNING: frontend container not running — cannot verify baked deps."
    echo "After 'make dev', re-run 'make check-frontend-deps'."
    exit 0
fi

if [ "$host_hash" != "$container_hash" ]; then
    echo "WARNING: host frontend/pnpm-lock.yaml differs from the frontend image."
    echo "Run 'make rebuild-frontend' (a plain restart keeps stale/mixed deps — bug-1278)."
    exit 1
fi

echo "frontend deps in sync (host == image)"
