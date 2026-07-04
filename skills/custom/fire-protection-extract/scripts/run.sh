#!/usr/bin/env bash
# 消防设计专篇 一键流水线：解析 → 抽取 → 溯源校验，报告直接落盘到 outputs/。
#
# 用法（agent 把路径放在环境变量里一起传——沙箱只翻译命令串里的路径，不翻译脚本内部）：
#   WORK=/mnt/user-data/workspace OUT=/mnt/user-data/outputs \
#     bash run.sh "<设计说明书.docx>" "<项目名>"
#
# 报告由脚本生成并写入 outputs/<项目名>消防设计专篇.md。
# agent 不是报告作者——不要 read_file 说明书、不要 write_file 改报告。
# 最后一行 `REPORT_READY: <path>` 即成品路径，直接 present_files 它。

set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: WORK=/mnt/user-data/workspace OUT=/mnt/user-data/outputs bash run.sh <设计说明书.docx> <项目名>" >&2
  exit 2
fi

DOCX="$1"
PROJECT="$2"

# 沙箱的 replace_virtual_paths_in_command 会把命令串里的 /mnt/user-data/ →
# 宿主机路径（在 env 赋值里也一样翻译）。但脚本内部的路径不在命令串里，沙箱
# 不会翻译，所以这里用宿主机路径。
#   /mnt/skills → /app/skills （固定映射，永远不变）
#   /mnt/user-data/... → 从环境变量取值（已被沙箱翻译为宿主机路径）
WORK_DIR="${WORK:-/mnt/user-data/workspace}"
OUT_DIR="${OUT:-/mnt/user-data/outputs}"
SKILL_DIR="/app/skills/custom/fire-protection-extract"

STRUCT="${WORK_DIR}/${PROJECT}_struct.json"
REPORT="${OUT_DIR}/${PROJECT}消防设计专篇.md"
MAPPING="${SKILL_DIR}/references/fire_spec_mapping.json"

mkdir -p "$WORK_DIR" "$OUT_DIR"

echo "[1/3] 解析说明书..."
python "${SKILL_DIR}/scripts/parse_spec.py" "$DOCX" "$STRUCT"

echo "[2/3] 按契约抽取报告..."
python "${SKILL_DIR}/scripts/extract.py" "$STRUCT" "$MAPPING" "$REPORT"

echo "[3/3] 逐字溯源校验..."
if python "${SKILL_DIR}/scripts/grounding_check.py" "$REPORT" "$STRUCT" "$MAPPING"; then
  GROUNDING="PASS"
else
  GROUNDING="CHECK_OUTPUT_ABOVE"
fi

# 报告里若含失配标记，提示 agent 走校准（不要自己改写报告正文）
if grep -q "\[⚠未找到" "$REPORT"; then
  echo ""
  echo "⚠ 报告含失配锚（说明书结构与样本契约有差异）。按 references/extractor_rules.md"
  echo "  校准一份 workspace 下的 mapping 副本后重跑本命令。不要手动改写报告正文。"
fi

echo ""
echo "grounding: ${GROUNDING}"
echo "report_chars: $(wc -m < "$REPORT" | tr -d ' ')"
echo "REPORT_READY: ${REPORT}"
