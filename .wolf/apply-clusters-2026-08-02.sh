#!/bin/bash
# Apply four upstream feature clusters (2026-08-02) — CLEAN-PORT files only.
# Source: bytedance/deer-flow main @ 7025ccee. Run from repo root.
#
# Clusters (NOT skipped per user decision):
#   1 消息列表虚拟化  message-list / virtual-message-list / derived-state / render-activity / chat-box / messages utils
#   2 inline artifact 编辑  code-editor-extensions / core/artifacts api,editing / code-editor / artifacts hooks,loader,preview,index / artifacts context,file-detail / mock route
#   3 代码高亮  shiki-highlight / code-block
#   4 context-usage 实时窗口  context-usage-badge,format / token-usage / thread types / backend context_usage.py
#
# NOT included (EAI-custom, manual merge):
#   backend/app/gateway/services.py, deps.py, app.py  (wire build_thread_checkpoint_state_accessor + context_usage)
#   frontend/src/components/workspace/messages/message-list-item.tsx  (EAI rewritten; verify new message-list interface)
#   frontend/src/core/i18n/locales/{en-US,zh-CN,types}.ts  (add contextUsage keys to EAI versions)
#   backend/tests/test_gateway_services.py  (tests EAI's services.py — belongs with the manual merge)
set -e
cd "$(dirname "$0")/.."

git --literal-pathspecs restore --source=7025ccee -- \
  frontend/src/components/workspace/messages/virtual-message-list.tsx \
  frontend/src/core/messages/derived-state.ts \
  frontend/src/core/dom/render-activity.ts \
  frontend/src/components/workspace/code-editor-extensions.ts \
  frontend/src/core/artifacts/api.ts \
  frontend/src/core/artifacts/editing.ts \
  frontend/src/components/ai-elements/shiki-highlight.ts \
  frontend/src/components/workspace/context-usage-badge.tsx \
  frontend/src/components/workspace/context-usage-format.ts \
  backend/app/gateway/context_usage.py \
  frontend/src/components/workspace/messages/message-list.tsx \
  frontend/src/components/workspace/messages/message-group.tsx \
  frontend/src/components/workspace/messages/markdown-content.tsx \
  frontend/src/components/workspace/chats/chat-box.tsx \
  frontend/src/core/messages/utils.ts \
  frontend/src/components/workspace/code-editor.tsx \
  frontend/src/core/artifacts/hooks.ts \
  frontend/src/core/artifacts/loader.ts \
  frontend/src/core/artifacts/preview.ts \
  frontend/src/core/artifacts/index.ts \
  frontend/src/components/workspace/artifacts/artifact-file-detail.tsx \
  frontend/src/components/workspace/artifacts/context.tsx \
  "frontend/src/app/mock/api/threads/[thread_id]/artifacts/[[...artifact_path]]/route.ts" \
  frontend/src/components/ai-elements/code-block.tsx \
  frontend/src/core/threads/token-usage.ts \
  frontend/src/core/threads/types.ts \
  frontend/src/components/workspace/token-usage-indicator.tsx \
  backend/app/gateway/routers/artifacts.py

echo "Applied 28 clean-port files (4 clusters)."

echo ""
echo "=== Optional: cluster unit tests (new/modified) ==="
echo "git --literal-pathspecs restore --source=7025ccee -- \\
  frontend/tests/unit/components/ai-elements/code-block.test.ts \\
  frontend/tests/unit/components/ai-elements/code-block.dom.test.tsx \\
  frontend/tests/unit/components/workspace/code-editor-extensions.test.ts \\
  frontend/tests/unit/components/workspace/artifacts/large-preview-source.test.ts \\
  frontend/tests/unit/components/workspace/context-usage-badge.test.ts \\
  frontend/tests/unit/components/workspace/context-usage-format.test.ts \\
  frontend/tests/unit/components/workspace/messages/virtual-message-list.test.ts \\
  frontend/tests/unit/components/workspace/messages/human-input-card.test.ts \\
  frontend/tests/unit/components/workspace/messages/human-input-card.dom.test.tsx \\
  frontend/tests/unit/components/workspace/messages/markdown-content.dom.test.tsx \\
  frontend/tests/unit/components/workspace/messages/message-group.test.ts \\
  frontend/tests/unit/core/artifacts/api.test.ts \\
  frontend/tests/unit/core/artifacts/editing.test.ts \\
  frontend/tests/unit/core/artifacts/hooks.dom.test.tsx \\
  frontend/tests/unit/core/artifacts/loader.test.ts \\
  frontend/tests/unit/core/artifacts/preview.test.ts \\
  frontend/tests/unit/core/dom/render-activity.dom.test.ts \\
  frontend/tests/unit/core/messages/derived-state.test.ts \\
  frontend/tests/unit/core/messages/utils.test.ts \\
  frontend/tests/unit/core/threads/token-usage.test.ts"

echo ""
echo "=== Verify after apply ==="
echo "cd frontend && pnpm typecheck      # frontend (shiki already in deps @3.23.0, no image rebuild)"
echo "docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -c \"import app.gateway.context_usage\"'"
echo "docker compose -p eai-docker restart frontend gateway"
