#!/usr/bin/env sh
#
# DeerFlow gateway dev entrypoint — runs inside the docker-compose-dev gateway
# container. Extracted from docker/docker-compose-dev.yaml's inline `command:`
# (PR #2767, addressing review on Issue #2754).
#
# Responsibilities:
#   1. Resolve `--extra X` flags from UV_EXTRAS (comma- or whitespace-separated,
#      mirroring scripts/detect_uv_extras.py for parity with local `make dev`).
#   2. Validate each extra against [A-Za-z][A-Za-z0-9_-]* so a stray shell
#      metacharacter in `.env` cannot reach `uv sync`.
#   3. `uv sync --all-packages` so workspace member extras (deerflow-harness's
#      postgres extra in particular) are installed — see PR #2584.
#   4. Self-heal: if the first sync fails, recreate .venv and retry once.
#   5. Hand off to uvicorn with reload, replacing this shell so uvicorn becomes
#      PID 1 inside the container.
#
# Anchored at /bin/sh (not bash) since alpine-based base images may not ship
# bash. Uses POSIX-only constructs throughout.

set -e

# `--print-extras` is a dry-run hook: parse + validate UV_EXTRAS, print the
# resulting `--extra X` flags to stdout, and exit. Used by the unit test in
# backend/tests/test_dev_entrypoint.py and useful for ad-hoc debugging.
PRINT_EXTRAS_ONLY=0
if [ "${1:-}" = "--print-extras" ]; then
    PRINT_EXTRAS_ONLY=1
fi

# Mirror the legacy command's behavior: redirect both stdout and stderr to the
# host-mounted log file (../logs/gateway.log → /app/logs/gateway.log). Skip
# the redirect under --print-extras so the test runner can capture stdout.
# EAI-CUSTOM (bug-1242): append (>>) instead of truncate (>) — `>` wipes the
# log on every container restart, destroying forensic evidence for incidents
# that occurred before the restart. Upgrade path: logrotate/compression if the
# file grows unbounded in long-lived dev environments.
if [ "$PRINT_EXTRAS_ONLY" = "0" ]; then
    exec >>/app/logs/gateway.log 2>&1
fi

# ── Resolve extras ──────────────────────────────────────────────────────────

EXTRAS_FLAGS=""
if [ -n "${UV_EXTRAS:-}" ]; then
    # Normalize comma → space, then split on whitespace via the unquoted `for`.
    for raw in $(printf '%s' "$UV_EXTRAS" | tr ',' ' '); do
        [ -z "$raw" ] && continue
        # Reject anything that does not look like an identifier.
        # Two patterns: leading non-letter, or any non-[A-Za-z0-9_-] character.
        case "$raw" in
            [!A-Za-z]* | *[!A-Za-z0-9_-]*)
                echo "[startup] UV_EXTRAS entry '$raw' is invalid (must match [A-Za-z][A-Za-z0-9_-]*) — aborting" >&2
                exit 1
                ;;
        esac
        EXTRAS_FLAGS="$EXTRAS_FLAGS --extra $raw"
    done
fi

if [ "$PRINT_EXTRAS_ONLY" = "1" ]; then
    # Trim leading space for tidier output, then exit.
    printf '%s\n' "${EXTRAS_FLAGS# }"
    exit 0
fi

if [ -n "$EXTRAS_FLAGS" ]; then
    echo "[startup] uv extras:$EXTRAS_FLAGS"
fi

# ── Sync dependencies (with self-heal) ──────────────────────────────────────

cd /app/backend

# `--all-packages` propagates extras into workspace members (PR #2584).
# `$EXTRAS_FLAGS` intentionally unquoted so each `--extra X` becomes its own arg.
# `--locked` keeps the container on the committed uv.lock (upstream #4780);
# the self-heal retry falls back to an unlocked sync so a stale lock does not
# brick the dev container (EAI-CUSTOM).
# shellcheck disable=SC2086 # word-splitting is intentional here
if ! uv sync --locked --all-packages $EXTRAS_FLAGS; then
    echo "[startup] locked uv sync failed; recreating .venv and retrying unlocked once"
    uv venv --allow-existing .venv
    # shellcheck disable=SC2086
    uv sync --all-packages $EXTRAS_FLAGS
fi

# ── Install MCP server dependencies ──────────────────────────────────────

# Auto-install dependencies for enabled MCP servers whose source is mounted
# into the container. This runs after the main `uv sync` so the venv is ready.
if [ -d /app/mcp-server/Office-Word-MCP-Server ]; then
    echo "[startup] Installing Office-Word-MCP-Server dependencies"
    cd /app/backend && uv pip install --quiet python-docx fastmcp msoffcrypto-tool docx2pdf || \
        echo "[startup] Warning: Office-Word-MCP-Server deps install failed (non-fatal)"
fi

# ── Hand off to uvicorn ─────────────────────────────────────────────────────

# EAI-CUSTOM: exclude runtime projection dir (.deer-flow/skills_view rebuilds
# hundreds of files every boot → triggers WatchFiles reload death-loop → nginx 502).
# NOTE (bug-1239): the exclude MUST resolve to a real directory, NOT a glob like
# '.deer-flow/**'. uvicorn's FileFilter does `Path(pattern).is_dir()` — a literal
# '**' is never a dir, so the pattern falls into path.match(), where '**' is NOT
# recursive (right-anchored, single-component) and deep projection files don't
# match. A real dir goes into exclude_dirs → is_relative_to() → truly recursive.
# Absolute paths (upstream's mechanism, see test_gateway_runtime_cleanup) avoid
# any cwd dependence; .venv is a named volume inside the watched tree that
# uv sync rewrites.
PYTHONPATH=. exec uv run --no-sync uvicorn app.gateway.app:app \
    --host 0.0.0.0 --port 8001 \
    --reload --reload-exclude='/app/backend/.deer-flow' --reload-exclude='/app/backend/.venv' \
    --reload-exclude='/app/backend/tests' \
    --reload-include='*.yaml .env'
# EAI-CUSTOM (bug-1242): exclude tests/ — concurrent sessions editing/running
# backend tests fire WatchFiles reloads that kill in-flight KF extraction tasks
# (asyncio task dies with the process; DB row stuck at running = zombie).
# App-code edits still hot-reload; full-immunity upgrade path: drop --reload.
