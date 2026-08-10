#!/bin/bash
# =============================================================
# Upstream sync 2026-08-02 — PHASE 1 (SAFE SET) ONLY
# Applies: PORTABLE 21 + backend B-core 64 (gateway + harness).
# Frontend B-core (33) and the 4 feature clusters are NOT here —
# see .wolf/sync-manifest-2026-08-02.md for phase 2/3 + EAI merge points.
# Never `git restore` EAI-custom files (services.py/deps.py/app.py/message-list-item.tsx).
# =============================================================
set -euo pipefail
UP_REF=7025ccee
# Usage: bash .wolf/sync-upstream-2026-08-02.sh          # dry-run (default)
#        bash .wolf/sync-upstream-2026-08-02.sh apply    # apply
MODE="${1:-dry}"

FILES=(
  # --- Group B: PORTABLE (21) ---
  backend/packages/harness/deerflow/skills/projection.py
  backend/packages/harness/deerflow/utils/thread_id.py
  extensions_config.example.json
  frontend/src/core/messages/workspace-change-anchor.ts
  frontend/src/core/workspace-changes/api.ts
  scripts/_detector_cli.py
  scripts/bump_version.sh
  scripts/deploy.sh
  scripts/detect_blocking_io_static.py
  scripts/detect_thread_boundaries.py
  scripts/detect_uv_extras.py
  scripts/scan_changed_blocking_io.py
  scripts/setup-sandbox.sh
  scripts/setup_wizard.py
  scripts/support_bundle.py
  scripts/tool-error-degradation-detection.sh
  scripts/wizard/providers.py
  scripts/wizard/steps/channels.py
  scripts/wizard/steps/llm.py
  scripts/wizard/ui.py
  scripts/wizard/writer.py
  # --- Group A backend: gateway (10) ---
  backend/app/gateway/authz.py
  backend/app/gateway/routers/artifacts.py
  backend/app/gateway/routers/browser.py
  backend/app/gateway/routers/console.py
  backend/app/gateway/routers/feedback.py
  backend/app/gateway/routers/mcp.py
  backend/app/gateway/routers/models.py
  backend/app/gateway/routers/scheduled_tasks.py
  backend/app/gateway/routers/skills.py
  backend/app/gateway/routers/uploads.py
  # --- Group A backend: harness (54) ---
  backend/packages/harness/deerflow/agents/lead_agent/agent.py
  backend/packages/harness/deerflow/agents/lead_agent/prompt.py
  backend/packages/harness/deerflow/agents/memory/backends/deermem/deermem/core/prompts/consolidation.yaml
  backend/packages/harness/deerflow/agents/memory/backends/deermem/deermem/core/prompts/memory_update.chat.yaml
  backend/packages/harness/deerflow/agents/memory/backends/deermem/deermem/core/updater.py
  backend/packages/harness/deerflow/agents/memory/backends/mem0/config.py
  backend/packages/harness/deerflow/agents/memory/backends/mem0/mem0_manager.py
  backend/packages/harness/deerflow/agents/memory/manager.py
  backend/packages/harness/deerflow/agents/memory/tools.py
  backend/packages/harness/deerflow/agents/middlewares/sandbox_audit_middleware.py
  backend/packages/harness/deerflow/client.py
  backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox.py
  backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py
  backend/packages/harness/deerflow/community/aio_sandbox/ownership/factory.py
  backend/packages/harness/deerflow/community/boxlite/box.py
  backend/packages/harness/deerflow/community/browser_automation/session.py
  backend/packages/harness/deerflow/community/e2b_sandbox/__init__.py
  backend/packages/harness/deerflow/community/e2b_sandbox/e2b_sandbox.py
  backend/packages/harness/deerflow/community/e2b_sandbox/e2b_sandbox_provider.py
  backend/packages/harness/deerflow/config/app_config.py
  backend/packages/harness/deerflow/config/checkpointer_config.py
  backend/packages/harness/deerflow/config/database_config.py
  backend/packages/harness/deerflow/config/extensions_config.py
  backend/packages/harness/deerflow/config/model_config.py
  backend/packages/harness/deerflow/config/paths.py
  backend/packages/harness/deerflow/config/sandbox_config.py
  backend/packages/harness/deerflow/mcp/tools.py
  backend/packages/harness/deerflow/models/factory.py
  backend/packages/harness/deerflow/persistence/bootstrap.py
  backend/packages/harness/deerflow/persistence/engine.py
  backend/packages/harness/deerflow/persistence/migrations/env.py
  backend/packages/harness/deerflow/runtime/checkpointer/async_provider.py
  backend/packages/harness/deerflow/runtime/checkpointer/provider.py
  backend/packages/harness/deerflow/runtime/events/store/jsonl.py
  backend/packages/harness/deerflow/runtime/journal.py
  backend/packages/harness/deerflow/runtime/runs/schemas.py
  backend/packages/harness/deerflow/runtime/store/async_provider.py
  backend/packages/harness/deerflow/runtime/store/provider.py
  backend/packages/harness/deerflow/sandbox/local/local_sandbox.py
  backend/packages/harness/deerflow/sandbox/local/local_sandbox_provider.py
  backend/packages/harness/deerflow/sandbox/sandbox.py
  backend/packages/harness/deerflow/sandbox/tools.py
  backend/packages/harness/deerflow/scheduler/schedules.py
  backend/packages/harness/deerflow/skills/storage/local_skill_storage.py
  backend/packages/harness/deerflow/skills/storage/skill_storage.py
  backend/packages/harness/deerflow/skills/storage/user_scoped_skill_storage.py
  backend/packages/harness/deerflow/subagents/builtins/bash_agent.py
  backend/packages/harness/deerflow/subagents/builtins/general_purpose.py
  backend/packages/harness/deerflow/tools/builtins/task_tool.py
  backend/packages/harness/deerflow/tools/skill_manage_tool.py
  backend/packages/harness/deerflow/tui/session.py
  backend/packages/harness/deerflow/uploads/manager.py
)

if [ "$MODE" = "apply" ]; then
  git restore --source="$UP_REF" -- "${FILES[@]}"
  echo "== Applied $UP_REF. Changed: $(git status --short "${FILES[@]}" | wc -l) files =="
  git status --short "${FILES[@]}"
else
  echo "== DRY RUN: files that would change (diff vs $UP_REF) =="
  git diff --name-only "$UP_REF" -- "${FILES[@]}"
  echo "== Apply with: bash .wolf/sync-upstream-2026-08-02.sh apply =="
fi
