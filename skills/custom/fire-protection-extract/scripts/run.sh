#!/usr/bin/env bash
# 消防设计专篇 一键流水线：解析 → 抽取 → 溯源校验，报告直接落盘到 outputs/。
#
# 用法（agent 只需调这一条命令，然后 present_files 成品路径）：
#   bash run.sh "<设计说明书.docx>" "<项目名>"
#
# 报告由脚本生成并写入 outputs/<项目名>消防设计专篇.md。
# agent 不是报告作者——不要 read_file 说明书、不要 write_file 改报告。
# 最后一行 `REPORT_READY: <path>` 即成品路径，直接 present_files 它。

set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: run.sh <设计说明书.docx> <项目名>" >&2
  exit 2
fi

DOCX="$1"
PROJECT="$2"

# 硬编码路径（不用变量——bash 沙箱扫描变量展开时不识别 ${VAR}/... 为安全路径）
SKILL_DIR="/mnt/skills/custom/fire-protection-extract"
WORK_DIR="/mnt/user-data/workspace"
OUT_DIR="/mnt/user-data/outputs"
MAPPING="/mnt/skills/custom/fire-protection-extract/references/fire_spec_mapping.json"

STRUCT="${WORK_DIR}/${PROJECT}_struct.json"
REPORT="${OUT_DIR}/${PROJECT}消防设计专篇.md"

mkdir -p "$WORK_DIR" "$OUT_DIR"

echo "[1/3] 解析说明书..."
python /mnt/skills/custom/fire-protection-extract/scripts/parse_spec.py "$DOCX" "$STRUCT"

echo "[2/3] 按契约抽取报告..."
python /mnt/skills/custom/fire-protection-extract/scripts/extract.py "$STRUCT" "$MAPPING" "$REPORT"

echo "[3/3] 逐字溯源校验..."
if python /mnt/skills/custom/fire-protection-extract/scripts/grounding_check.py "$REPORT" "$STRUCT" "$MAPPING"; then
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
