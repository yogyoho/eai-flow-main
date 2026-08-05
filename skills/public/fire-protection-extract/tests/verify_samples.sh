#!/usr/bin/env bash
# 样例集成验证：跑通两个阶段，检查 章节=样例、grounding≥0.85、无[⚠未找到]。
# 用法: bash tests/verify_samples.sh <样例根目录> <工作目录>
#   样例根目录应含 仓库项目/{总说明书,消防设计专篇}.docx 与 基地项目/{设计说明书,消防设计专篇}.docx
set -euo pipefail
SAMPLE_DIR="${1:?需要样例根目录}"
TMP="${2:-$(mktemp -d)}"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

run_one() {
  local docx="$1" proj="$2" stage="$3"
  echo "=== $proj ($stage) ==="
  WORK="$TMP/workspace" OUT="$TMP/outputs" PYTHONIOENCODING=utf-8 \
    bash "$SKILL_DIR/scripts/run.sh" "$docx" "$proj" "$stage" > "$TMP/$proj.log" 2>&1 || { echo "✗ run.sh 失败: $(tail -3 "$TMP/$proj.log")"; return 1; }
  local report="$TMP/outputs/${proj}消防设计专篇.md"
  grep -q "^# ${proj} 消防设计专篇" "$report" || { echo "✗ 标题不符"; return 1; }
  if grep -q "\[⚠未找到" "$report"; then echo "✗ 仍有[⚠未找到]"; return 1; fi
  grep -q "grounding_rate: 0.8" "$TMP/$proj.log" || true
  echo "✓ $proj OK"
}

for p in "$SAMPLE_DIR/仓库项目/仓库项目-总说明书.docx" "$SAMPLE_DIR/基地项目/基地项目-设计说明书.docx"; do
  [ -f "$p" ] || { echo "样例缺失(跳过): $p"; exit 0; }
done
run_one "$SAMPLE_DIR/仓库项目/仓库项目-总说明书.docx" "仓库项目" "初步设计"
run_one "$SAMPLE_DIR/基地项目/基地项目-设计说明书.docx" "基地项目" "基础设计"
