#!/usr/bin/env bash
# 消防设计专篇 一键流水线：解析 → 查契约 → 抽取 → 溯源校验。
#
# 单文档（向后兼容）：
#   bash run.sh "<设计说明书.docx>" "<项目名>" [contract_name]
#
# 多文档融合（E7）— 第2个参数也是 .docx 时自动启用：
#   bash run.sh "<总说明书.docx>" "<给排水册.docx>" "<电气册.docx>" "<项目名>" [contract_name]

set -euo pipefail

# Ensure UTF-8 output on all platforms (Python defaults to GBK on Windows)
export PYTHONIOENCODING=utf-8

if [ "$#" -lt 2 ]; then
  echo "usage: bash run.sh <设计说明书.docx> [分册.docx ...] <项目名> [contract_name]" >&2
  exit 2
fi

# Detect multi-doc mode: if $2 ends with .docx, all args before project name are docx paths
DOCX_FILES=()
PROJECT=""
CONTRACT_NAME=""
MULTI_DOC=false

# Collect docx args
for arg in "$@"; do
  case "$arg" in
    *.docx|*.doc)
      DOCX_FILES+=("$arg")
      ;;
    *)
      if [ -z "$PROJECT" ]; then
        PROJECT="$arg"
      else
        CONTRACT_NAME="$arg"
      fi
      ;;
  esac
done

if [ ${#DOCX_FILES[@]} -eq 0 ]; then
  echo "ERROR: no .docx/.doc file found in arguments" >&2
  echo "usage: bash run.sh <设计说明书.docx> [分册.docx ...] <项目名> [contract_name]" >&2
  exit 2
fi

if [ ${#DOCX_FILES[@]} -gt 1 ]; then
  MULTI_DOC=true
fi

WORK_DIR="${WORK:-/mnt/user-data/workspace}"
OUT_DIR="${OUT:-/mnt/user-data/outputs}"
for _try in "/app/skills" "/mnt/skills" "$(dirname "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")")"; do
  if [ -f "${_try}/public/fire-protection-extract/scripts/parse_spec.py" ]; then
    SKILL_DIR="${_try}/public/fire-protection-extract"
    break
  fi
  # Also try: _try itself IS the skill dir
  if [ -f "${_try}/scripts/parse_spec.py" ]; then
    SKILL_DIR="${_try}"
    break
  fi
done
if [ -z "${SKILL_DIR:-}" ]; then
  echo "ERROR: skills dir not found (tried /app/skills, /mnt/skills)" >&2
  exit 1
fi

REPORT="${OUT_DIR}/${PROJECT}消防设计专篇.md"
DEFAULT_MAPPING="${SKILL_DIR}/references/fire_spec_mapping.json"
MAPPING="${WORK_DIR}/${PROJECT}_mapping.json"

mkdir -p "$WORK_DIR" "$OUT_DIR"

# ── [1/4] 解析说明书 ─────────────────────────────────────────────
echo "[1/4] 解析说明书..."
if $MULTI_DOC; then
  echo "  多文档模式: ${#DOCX_FILES[@]} 个源文件"
  STRUCT_FILES=()
  for i in "${!DOCX_FILES[@]}"; do
    SF="${WORK_DIR}/${PROJECT}_struct_${i}.json"
    python "${SKILL_DIR}/scripts/parse_spec.py" "${DOCX_FILES[$i]}" "$SF"
    STRUCT_FILES+=("$SF")
  done
  # Merge into single structure
  STRUCT="${WORK_DIR}/${PROJECT}_struct.json"
  python "${SKILL_DIR}/scripts/merge_structures.py" "$STRUCT" "${STRUCT_FILES[@]}"
  echo "  → 合并完成: $(python -c "import json; d=json.loads(open('$STRUCT',encoding='utf-8').read()); print(f\"{len(d['paras'])} paras, {len(d['tables'])} tables\")")"
else
  STRUCT="${WORK_DIR}/${PROJECT}_struct.json"
  python "${SKILL_DIR}/scripts/parse_spec.py" "${DOCX_FILES[0]}" "$STRUCT"
fi

# ── [2/4] 契约查找 ────────────────────────────────────────────────
echo "[2/4] 查找最佳契约..."
FOUND=""
if [ -n "$CONTRACT_NAME" ]; then
  echo "  指定契约: ${CONTRACT_NAME}"
  if python "${SKILL_DIR}/scripts/contract_store.py" load "$CONTRACT_NAME" > "$MAPPING" 2>/dev/null; then
    FOUND="$CONTRACT_NAME"
  else
    echo "  ⚠ 指定契约不存在，回退到默认契约"
  fi
fi

if [ -z "$FOUND" ]; then
  MATCH_RESULT=$(python "${SKILL_DIR}/scripts/contract_store.py" find "$STRUCT" 2>/dev/null || echo "NO_MATCH")
  if echo "$MATCH_RESULT" | grep -q '"name"'; then
    FOUND=$(echo "$MATCH_RESULT" | python -c "import sys,json; print(json.load(sys.stdin)['name'])" 2>/dev/null || echo "")
    echo "  最佳匹配: ${FOUND}"
    echo "$MATCH_RESULT" | python -c "import sys,json; m=json.load(sys.stdin)['mapping']; print(json.dumps(m,ensure_ascii=False,indent=2))" > "$MAPPING" 2>/dev/null
  fi
fi

if [ -z "$FOUND" ]; then
  echo "  ⚠ 未找到匹配契约 — 需要使用 E3 工作流生成契约"
  echo "  → 默认契约（基地项目模板）作为兜底，预期会有大量 [⚠未找到]"
  echo "CONTRACT_NEEDED: ${STRUCT}"
  echo "DEFAULT_MAPPING: ${DEFAULT_MAPPING}"
  # fall back to default mapping so pipeline doesn't break
  cp "$DEFAULT_MAPPING" "$MAPPING"
else
  echo "  ✓ 使用契约: ${FOUND}"
fi

# ── [3/4] 按契约抽取报告 ──────────────────────────────────────────
echo "[3/4] 按契约抽取报告..."
python "${SKILL_DIR}/scripts/extract.py" "$STRUCT" "$MAPPING" "$REPORT"

# ── [4/4] 逐字溯源校验 ────────────────────────────────────────────
echo "[4/4] 逐字溯源校验..."
GROUNDING_ERR_LOG="${WORK_DIR}/${PROJECT}_grounding_err.log"
GROUNDING_OUT=$(python "${SKILL_DIR}/scripts/grounding_check.py" "$REPORT" "$STRUCT" "$MAPPING" 2>"$GROUNDING_ERR_LOG") || true
echo "$GROUNDING_OUT"

GROUNDING="CHECK_OUTPUT_ABOVE"
if echo "$GROUNDING_OUT" | grep -q '"rate"'; then
  RATE=$(echo "$GROUNDING_OUT" | python -c "import sys,json; print(json.load(sys.stdin).get('rate',0))" 2>/dev/null || echo "0")
  echo "grounding_rate: ${RATE}"
  if python -c "exit(0 if float(${RATE:-0}) >= 0.85 else 1)" 2>/dev/null; then
    GROUNDING="PASS"
  fi
fi

# ── 失配提示 ──────────────────────────────────────────────────────
if grep -q "\[⚠未找到" "$REPORT"; then
  MISS_COUNT=$(grep -c "\[⚠未找到" "$REPORT" || echo "0")
  echo ""
  echo "⚠ 报告含 ${MISS_COUNT} 处失配锚。"
  if [ -z "$FOUND" ] || [ "$FOUND" = "" ]; then
    echo "  → 这是新项目类型，需要生成专属契约（E3 工作流）。"
    echo "  → 不要手动改写报告正文——让 agent 分析 structure.json 生成新契约后重跑。"
  else
    echo "  → 可能是契约与说明书版本不一致，人工审核后更新契约。"
  fi
fi

echo ""
echo "grounding: ${GROUNDING}"
echo "contract: ${FOUND:-default}"
echo "report_chars: $(wc -m < "$REPORT" | tr -d ' ')"

# ── [5/5] 合规检查 ────────────────────────────────────────────────
echo "[5/5] 合规检查..."
COMPLIANCE="${OUT_DIR}/${PROJECT}消防设计合规检查报告.md"
COMPLIANCE_STATUS="pass"
if python "${SKILL_DIR}/scripts/compliance_check.py" "$REPORT" > "$COMPLIANCE" 2>&1; then
  echo "  ✓ 合规检查通过"
else
  COMPLIANCE_STATUS="issues"
  echo "  ⚠ 合规检查发现问题，详见报告"
fi
echo "COMPLIANCE_READY: ${COMPLIANCE}"

# ── Report Passport（阶段间元数据传递）─────────────────────────────
PASSPORT="${OUT_DIR}/${PROJECT}_passport.json"
REPORT_CHARS=$(wc -m < "$REPORT" | tr -d ' ')
GROUNDING_JSON=$(echo "$GROUNDING_OUT" | python -c "import sys,json; d=sys.stdin.read(); print(json.dumps(json.loads(d[d.find('{'):])))" 2>/dev/null || echo "{}")

python "${SKILL_DIR}/scripts/gen_passport.py" \
  "$PASSPORT" "$PROJECT" "$REPORT" "$COMPLIANCE" \
  "${FOUND:-default}" "$GROUNDING_JSON" "$COMPLIANCE_STATUS" "$REPORT_CHARS" 2>&1

# 完整性关卡：从 passport 读 report_status
REPORT_STATUS=$(python -c "import json; print(json.loads(open('$PASSPORT',encoding='utf-8').read())['report_status'])" 2>/dev/null || echo "READY")

echo "REPORT_${REPORT_STATUS}: ${REPORT}"
