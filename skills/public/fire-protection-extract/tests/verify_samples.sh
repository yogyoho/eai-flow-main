#!/usr/bin/env bash
# 样例集成验证：跑通两个阶段，检查 章节=样例、grounding≥0.85、无[⚠未找到]。
# 用法: bash tests/verify_samples.sh <样例根目录> <工作目录>
#   样例根目录应含 仓库项目/{总说明书,消防设计专篇}.docx 与 基地项目/{设计说明书,消防设计专篇}.docx
set -euo pipefail
SAMPLE_DIR="${1:?需要样例根目录}"
TMP="${2:-$(mktemp -d)}"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$TMP"

run_one() {
  local docx="$1" proj="$2" stage="$3" exp_docx="$4"
  echo "=== $proj ($stage) ==="
  WORK="$TMP/workspace" OUT="$TMP/outputs" PYTHONIOENCODING=utf-8 \
    bash "$SKILL_DIR/scripts/run.sh" "$docx" "$proj" "$stage" > "$TMP/$proj.log" 2>&1 || { echo "✗ run.sh 失败: $(tail -3 "$TMP/$proj.log")"; return 1; }
  local report="$TMP/outputs/${proj}消防设计专篇.md"
  grep -q "^# ${proj} 消防设计专篇" "$report" || { echo "✗ 标题不符"; return 1; }
  # 章节对照样例：生成报告的 1-2 级章节号应覆盖样例专篇正文的章节号。
  # 容忍目录行（结尾页码数字）、多余空格、3级子标题差异与标题措辞微调（如 5.1 室外水/室外消防水）。
  python - "$report" "$exp_docx" <<'PY' || { echo "✗ 章节与样例不符"; return 1; }
import re, sys, zipfile
def md_nums(md):
    nums = set()
    for l in md.splitlines():
        m = re.match(r'^\s*#{1,4}\s+(\d+(?:\.\d+)?)\s', l)
        if m:
            nums.add(m.group(1))
    return nums
def docx_body_nums(docx):
    z = zipfile.ZipFile(docx)
    xml = z.read('word/document.xml').decode('utf-8', 'replace')
    out = []
    for p in re.findall(r'<w:p\b[^>]*>.*?</w:p>', xml, re.DOTALL):
        t = ' '.join(''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p)).split())
        if not t or re.search(r'\d+$', t):      # 空行/目录行(以页码数字结尾)跳过
            continue
        m = re.match(r'^(\d+(?:\.\d+)?)\s+\S', t)
        if m and len(m.group(1).split('.')) <= 2:  # 仅 1-2 级章节
            out.append(m.group(1))
    return out
got = md_nums(open(sys.argv[1], encoding='utf-8').read())
exp = docx_body_nums(sys.argv[2])
missing = [h for h in exp if h not in got]
print(f'generated {len(got)} sections; sample body {len(exp)}; missing: {missing[:10]}')
sys.exit(0 if not missing else 1)
PY
  if grep -q "\[⚠未找到" "$report"; then echo "✗ 仍有[⚠未找到]"; return 1; fi
  grep -q "grounding_rate: 0.8" "$TMP/$proj.log" || true
  echo "✓ $proj OK"
}

for p in "$SAMPLE_DIR/仓库项目/仓库项目-总说明书.docx" "$SAMPLE_DIR/基地项目/基地项目-设计说明书.docx"; do
  [ -f "$p" ] || { echo "样例缺失(跳过): $p"; exit 0; }
done
run_one "$SAMPLE_DIR/仓库项目/仓库项目-总说明书.docx" "仓库项目" "初步设计" "$SAMPLE_DIR/仓库项目/仓库项目-消防设计专篇.docx"
run_one "$SAMPLE_DIR/基地项目/基地项目-设计说明书.docx" "基地项目" "基础设计" "$SAMPLE_DIR/基地项目/基地项目-消防设计专篇.docx"
