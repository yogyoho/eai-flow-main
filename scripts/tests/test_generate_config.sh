#!/usr/bin/env bash
# Self-check for generate-config.sh (Ponytail: one small runnable check, no framework).
# Run: bash scripts/tests/test_generate_config.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GEN="$HERE/../generate-config.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Minimal deploy.conf — exercises spaced+quoted value (BRAND_FOOTER) to catch parser bugs.
cat > "$WORK/deploy.conf" <<'EOF'
BRAND_NAME=客户A
BRAND_FOOTER="© 2026 客户A"
LLM_BASE_URL=http://10.0.0.5:8080/v1
LLM_API_KEY=sk-test
LLM_MODEL=qwen-plus
EOF

# generate-config 在包内完整 config.yaml/.env 基础上注入（模拟 offline-export 已拷入完整配置）
cp "$HERE/../../deploy/offline/config.yaml" "$WORK/config.yaml"
cp "$HERE/../../deploy/offline/.env" "$WORK/.env"

bash "$GEN" --conf "$WORK/deploy.conf" --out "$WORK" --root "/opt/eai" --secret "SECRETXYZ" --origin "http://10.0.0.5:4026"

# Assertions — each must hold or the script is wrong.
grep -q "EXTENSIONS_DB_HOST=postgres-ext" "$WORK/.env"               || { echo "FAIL: EXTENSIONS_DB_HOST"; exit 1; }
grep -q "BETTER_AUTH_SECRET=SECRETXYZ" "$WORK/.env"                  || { echo "FAIL: secret"; exit 1; }
grep -q "DEER_FLOW_TRUSTED_ORIGINS=http://10.0.0.5:4026" "$WORK/.env" || { echo "FAIL: origin"; exit 1; }
# bug-1015 回归：shipped 完整 .env 必须被保留（定向 patch），不能被最小模板覆盖。
# GATEWAY_WORKERS / CAD_VIEWER_PORT 只在 shipped .env 里、不在 fallback 最小集 → 存活即证明非破坏。
grep -q "^GATEWAY_WORKERS=4" "$WORK/.env"                            || { echo "FAIL: shipped .env clobbered (GATEWAY_WORKERS lost — bug-1015 regression!)"; exit 1; }
grep -q "^CAD_VIEWER_PORT=" "$WORK/.env"                             || { echo "FAIL: shipped .env clobbered (CAD_VIEWER_PORT lost)"; exit 1; }
# deploy.conf 的 LLM_API_KEY 应定向注入到 INTERNAL_LLM_API_KEY（覆盖 shipped 的 sk-placeholder）
grep -q "^INTERNAL_LLM_API_KEY=sk-test" "$WORK/.env"                || { echo "FAIL: INTERNAL_LLM_API_KEY not patched from LLM_API_KEY"; exit 1; }
grep -q "base_url: http://10.0.0.5:8080/v1" "$WORK/config.yaml"     || { echo "FAIL: llm base_url"; exit 1; }
grep -q "model: qwen-plus" "$WORK/config.yaml"                      || { echo "FAIL: llm model"; exit 1; }
grep -q "^sandbox:" "$WORK/config.yaml"                             || { echo "FAIL: sandbox section lost (regression — gateway would crash!)"; exit 1; }
grep -q "mcpServers" "$WORK/extensions_config.json"                 || { echo "FAIL: extensions_config"; exit 1; }

echo "PASS: generate-config.sh"
