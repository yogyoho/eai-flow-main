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

# generate-config 在包内完整 config.yaml 基础上注入（模拟 offline-export 已拷入完整配置）
cp "$HERE/../../deploy/offline/config.yaml" "$WORK/config.yaml"

bash "$GEN" --conf "$WORK/deploy.conf" --out "$WORK" --root "/opt/eai" --secret "SECRETXYZ" --origin "http://10.0.0.5:4026"

# Assertions — each must hold or the script is wrong.
grep -q "EXTENSIONS_DB_HOST=postgres-ext" "$WORK/.env"               || { echo "FAIL: EXTENSIONS_DB_HOST"; exit 1; }
grep -q "BETTER_AUTH_SECRET=SECRETXYZ" "$WORK/.env"                  || { echo "FAIL: secret"; exit 1; }
grep -q "DEER_FLOW_TRUSTED_ORIGINS=http://10.0.0.5:4026" "$WORK/.env" || { echo "FAIL: origin"; exit 1; }
grep -q "base_url: http://10.0.0.5:8080/v1" "$WORK/config.yaml"     || { echo "FAIL: llm base_url"; exit 1; }
grep -q "model: qwen-plus" "$WORK/config.yaml"                      || { echo "FAIL: llm model"; exit 1; }
grep -q "^sandbox:" "$WORK/config.yaml"                             || { echo "FAIL: sandbox section lost (regression — gateway would crash!)"; exit 1; }
grep -q "mcpServers" "$WORK/extensions_config.json"                 || { echo "FAIL: extensions_config"; exit 1; }

echo "PASS: generate-config.sh"
