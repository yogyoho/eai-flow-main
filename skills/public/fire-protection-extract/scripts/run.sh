#!/usr/bin/env bash
# 消防设计专篇 一键流水线：解析 → 阶段检测 → 大纲 → 契约 → 抽取 → 溯源校验。
#   bash run.sh "<设计说明书.docx>" "<项目名>" [初步设计|基础设计]

set -euo pipefail
export PYTHONIOENCODING=utf-8

if [ "$#" -lt 2 ]; then
  echo "usage: bash run.sh <设计说明书.docx> <项目名> [初步设计|基础设计]" >&2
  exit 2
fi

DOCX="${1:?need docx}"
PROJECT="${2:?need project}"
STAGE_OVERRIDE="${3:-}"

WORK_DIR="${WORK:-/mnt/user-data/workspace}"
OUT_DIR="${OUT:-/mnt/user-data/outputs}"
for _try in "/app/skills" "/mnt/skills" "$(dirname "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")")"; do
  if [ -f "${_try}/public/fire-protection-extract/scripts/parse_spec.py" ]; then
    SKILL_DIR="${_try}/public/fire-protection-extract"; break
  fi
  if [ -f "${_try}/scripts/parse_spec.py" ]; then SKILL_DIR="${_try}"; break; fi
done
if [ -z "${SKILL_DIR:-}" ]; then echo "ERROR: skills dir not found" >&2; exit 1; fi

REPORT="${OUT_DIR}/${PROJECT}消防设计专篇.md"
STRUCT="${WORK_DIR}/${PROJECT}_struct.json"
OUTLINE_DIR="${SKILL_DIR}/references/stage-outlines"
MAPPING="${WORK_DIR}/${PROJECT}_mapping.json"

mkdir -p "$WORK_DIR" "$OUT_DIR"

echo "[1/5] 解析说明书..."
python "${SKILL_DIR}/scripts/parse_spec.py" "$DOCX" "$STRUCT"

echo "[2/5] 阶段检测..."
if [ -n "$STAGE_OVERRIDE" ]; then
  STAGE="$STAGE_OVERRIDE"
  echo "  显式阶段: $STAGE"
else
  STAGE=$(python "${SKILL_DIR}/scripts/detect_stage.py" "$STRUCT")
  echo "  自动识别: $STAGE"
fi
OUTLINE="${OUTLINE_DIR}/${STAGE}.json"
if [ ! -f "$OUTLINE" ]; then echo "ERROR: 阶段大纲不存在 $OUTLINE" >&2; exit 3; fi

echo "[3/5] 契约查找 (stage=$STAGE)..."
FOUND=""
# find 退出码：0=命中, 3=格式错误, 4=未匹配, 2=参数错误
set +e
FIND_OUT=$(python "${SKILL_DIR}/scripts/contract_store.py" find "$STAGE" "$STRUCT" 2>&1)
FIND_RC=$?
set -e
if [ "$FIND_RC" -eq 0 ]; then
  FOUND=$(echo "$FIND_OUT" | python -c "import sys,json; print(json.load(sys.stdin)['name'])" 2>/dev/null || echo "")
  echo "$FIND_OUT" | python -c "import sys,json; m=json.load(sys.stdin)['mapping']; json.dump(m,sys.stdout,ensure_ascii=False,indent=2)" > "$MAPPING" 2>/dev/null || true
  echo "  ✓ 使用契约: ${FOUND}"
  # 契约大纲版本漂移守卫：映射记录的 _outline_version 与当前大纲不一致 → 拒绝使用。
  # 注：路径必须作为 argv 传入（MSYS/GitBash 会把 /d/.. 转成 D:/..），内嵌进 -c 字符串会打不开
  OUTLINE_VERSION_ERR=$(python -c "import json,sys; m=json.load(open(sys.argv[1],encoding='utf-8')); o=json.load(open(sys.argv[2],encoding='utf-8')); m_v=m.get('_outline_version'); o_v=o.get('outline_version'); print(f'契约基于旧大纲版本 {m_v}，当前大纲版本 {o_v}，需 E3 重跑' if (m_v is not None and o_v is not None and m_v != o_v) else '')" "$MAPPING" "$OUTLINE" 2>/dev/null || echo "")
  if [ -n "$OUTLINE_VERSION_ERR" ]; then
    echo "CONTRACT_STALE: $OUTLINE_VERSION_ERR" >&2
    echo "  → 契约大纲版本过旧，删除后重跑 E3 生成新映射" >&2
    exit 3
  fi
elif [ "$FIND_RC" -eq 3 ]; then
  echo "CONTRACT_ERROR: $FIND_OUT" >&2
  echo "  → 契约解析/格式异常，检查 struct.json 或重跑 E3" >&2
  exit 3
elif [ "$FIND_RC" -eq 4 ]; then
  echo "CONTRACT_NEEDED: ${STRUCT}"
  echo "STAGE: ${STAGE}"
  echo "OUTLINE: ${OUTLINE}"
  echo "  → 新项目/新阶段，需 E3 生成 <项目名>_mapping.json 后重跑" >&2
  exit 3
else
  echo "ERROR: contract_store find 失败 rc=$FIND_RC" >&2
  echo "$FIND_OUT" >&2
  exit 3
fi

echo "[4/5] 按契约抽取报告..."
python "${SKILL_DIR}/scripts/extract.py" "$STRUCT" "$OUTLINE" "$MAPPING" "$REPORT" "$PROJECT"

echo "[5/5] 逐字溯源校验..."
GROUNDING_ERR_LOG="${WORK_DIR}/${PROJECT}_grounding_err.log"
GROUNDING_OUT=$(python "${SKILL_DIR}/scripts/grounding_check.py" "$REPORT" "$STRUCT" "$OUTLINE" "$MAPPING" 2>"$GROUNDING_ERR_LOG") || true
echo "$GROUNDING_OUT"
if [ -z "$GROUNDING_OUT" ] && [ -s "$GROUNDING_ERR_LOG" ]; then
  echo "⚠ grounding_check 异常，日志:" >&2
  cat "$GROUNDING_ERR_LOG" >&2
fi

REPORT_STATUS="NEEDS_REVIEW"
if echo "$GROUNDING_OUT" | grep -q '"rate"'; then
  RATE=$(echo "$GROUNDING_OUT" | python -c "import sys,json; print(json.load(sys.stdin).get('rate',0))" 2>/dev/null || echo "0")
  MISS=$(echo "$GROUNDING_OUT" | python -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('missing_anchors',[])) + len(d.get('uncovered_sections',[])) + len(d.get('conflict_failures',[])))" 2>/dev/null || echo "99")
  echo "grounding_rate: ${RATE}  missing+uncovered+conflict: ${MISS}"
  if python -c "exit(0 if float(${RATE:-0}) >= 0.85 and int(${MISS:-99}) == 0 else 1)" 2>/dev/null; then
    REPORT_STATUS="READY"
  fi
fi

if grep -q "\[⚠未找到" "$REPORT"; then
  echo "⚠ 报告含 $(grep -c '\[⚠未找到' "$REPORT" || true) 处失配锚。E5 校准或 E3 重跑。"
fi

# ── 合规检查 ──────────────────────────────────
COMPLIANCE="${OUT_DIR}/${PROJECT}消防设计合规检查报告.md"
COMPLIANCE_STATUS="pass"
if python "${SKILL_DIR}/scripts/compliance_check.py" "$REPORT" > "$COMPLIANCE" 2>&1; then
  echo "  ✓ 合规检查通过"
else
  COMPLIANCE_STATUS="issues"
  echo "  ⚠ 合规检查发现问题，详见报告"
fi

# ── Passport ──────────────────────────────────
PASSPORT="${OUT_DIR}/${PROJECT}_passport.json"
REPORT_CHARS=$(wc -m < "$REPORT" | tr -d ' ')
GROUNDING_JSON=$(echo "$GROUNDING_OUT" | python -c "import sys,json; d=sys.stdin.read(); print(json.dumps(json.loads(d[d.find('{'):])))" 2>/dev/null || echo "{}")
python "${SKILL_DIR}/scripts/gen_passport.py" "$PASSPORT" "$PROJECT" "$REPORT" "$COMPLIANCE" \
  "${FOUND:-default}" "$GROUNDING_JSON" "$COMPLIANCE_STATUS" "$REPORT_CHARS" 2>&1 || \
  echo "⚠ passport 生成失败" >&2

# 覆盖 report_status 为 run.sh 门限结果（rate≥0.85 且 MISS==0）
# 注：路径必须作为 argv 传入（MSYS/GitBash 会把 /d/.. 转成 D:/..），内嵌进 -c 字符串会打不开
python -c "import json,sys; p=json.load(open(sys.argv[1],encoding='utf-8')); p['report_status']=sys.argv[2]; json.dump(p,open(sys.argv[1],'w',encoding='utf-8'),ensure_ascii=False,indent=2)" "$PASSPORT" "$REPORT_STATUS" 2>/dev/null || true

echo "REPORT_${REPORT_STATUS}: ${REPORT}"
