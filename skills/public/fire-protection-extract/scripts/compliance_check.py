#!/usr/bin/env python3
"""消防设计专篇合规检查 — 10项 GB 规范校验。

读取报告 markdown，逐项检查关键内容是否完整。
输出 markdown 格式的合规检查报告。

Usage:
  python compliance_check.py <report.md>
"""
import re
import sys
from pathlib import Path


# 10项检查规则
CHECKS = [
    {
        "id": "1. 耐火等级",
        "standard": "GB50016 §3",
        "desc": "建筑物耐火等级标注（一级/二级/三级/四级）",
        "pass_keywords": [["耐火等级", "二级"], ["耐火等级", "一级"]],
        "warn_keywords": [["耐火等级"]],
    },
    {
        "id": "2. 火灾危险性分类",
        "standard": "GB50016/GB50160",
        "desc": "储存物品火灾危险性类别（甲/乙/丙/丁/戊类）",
        "pass_keywords": [["丙类"], ["乙类"], ["甲类"], ["丁类"], ["戊类"]],
        "warn_keywords": [["火灾危险"]],
    },
    {
        "id": "3. 防火间距",
        "standard": "GB50016 §5.2",
        "desc": "防火间距具体数值",
        "pass_keywords": [["防火间距"], ["间距"]],
        "extra_check": r"(\d+\.?\d*)\s*m",
        "extra_desc": "间距数值",
    },
    {
        "id": "4. 消防给水量",
        "standard": "GB50974",
        "desc": "消防用水量标注",
        "pass_keywords": [["消防水量", "m3"], ["消防用水量"], ["消防水", "L/s"]],
        "warn_keywords": [["消防水"]],
    },
    {
        "id": "5. 室内消火栓",
        "standard": "GB50974",
        "desc": "室内消火栓系统描述",
        "pass_keywords": [["室内消火栓"], ["消火栓", "DN65"], ["消火栓", "水枪"]],
        "warn_keywords": [["消火栓"]],
    },
    {
        "id": "6. 火灾自动报警",
        "standard": "GB50116",
        "desc": "火灾自动报警系统描述",
        "pass_keywords": [["火灾自动报警", "探测器"], ["火灾报警", "感烟"], ["火灾报警", "感温"]],
        "warn_keywords": [["火灾报警"], ["火灾自动报警"]],
    },
    {
        "id": "7. 灭火器配置",
        "standard": "GB50140",
        "desc": "灭火器配置描述",
        "pass_keywords": [["灭火器"]],
    },
    {
        "id": "8. 消防通道",
        "standard": "GB50016 §7.1",
        "desc": "消防道路/通道描述（宽度、转弯半径）",
        "pass_keywords": [["消防道", "宽度"], ["消防通道", "宽度"], ["环形消防"]],
        "warn_keywords": [["消防道"], ["消防通道"]],
    },
    {
        "id": "9. 防雷接地",
        "standard": "GB50057",
        "desc": "防雷接地系统描述",
        "pass_keywords": [["防雷", "接地"], ["避雷", "接地"]],
        "warn_keywords": [["防雷"], ["接地"]],
    },
    {
        "id": "10. 核心标准引用",
        "standard": "GB50016+GB50160",
        "desc": "核心消防设计标准引用完整性",
        "pass_keywords": [
            ["GB50016", "GB50160"],
            ["GB50016", "GB 50160"],
            ["GB 50016", "GB50160"],
            ["GB 50016", "GB 50160"],
        ],
        "warn_keywords": [
            ["GB50016"], ["GB50160"], ["GB 50016"], ["GB 50160"],
        ],
    },
]


def evaluate(report_md, check):
    """评估单条检查，返回 (status, detail)。status: PASS/WARN/FAIL"""
    # Check pass keywords (any group fully matched)
    for group in check.get("pass_keywords", []):
        if all(kw in report_md for kw in group):
            # Extra check (e.g., numeric value)
            if "extra_check" in check:
                nums = re.findall(check["extra_check"], report_md)
                if nums:
                    return "PASS", f"找到 {len(nums)} 处{check.get('extra_desc', '数值')}"
                return "WARN", f"提到了{check['desc']}但未找到具体数值"
            return "PASS", None
    # Check warn keywords
    for group in check.get("warn_keywords", []):
        if all(kw in report_md for kw in group):
            return "WARN", f"提到了相关内容但不够详细（{check['desc']}）"
    return "FAIL", f"未找到{check['desc']}"


def run_checks(report_md):
    """运行全部检查，返回结果列表。"""
    results = []
    for check in CHECKS:
        status, detail = evaluate(report_md, check)
        results.append({**check, "status": status, "detail": detail})
    return results


def format_report(results):
    """生成 markdown 格式的合规检查报告。"""
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    lines = ["# 消防设计合规检查报告", ""]
    lines.append(f"**检查结果：** {pass_count} 通过 / {warn_count} 警告 / {fail_count} 不通过")
    lines.append("")

    if fail_count > 0:
        lines.append(f"🔴 须修复：{fail_count} 项不通过")
        for r in results:
            if r["status"] == "FAIL":
                lines.append(f"- **{r['id']}**（{r['standard']}）— {r['detail']}")
        lines.append("")

    if warn_count > 0:
        lines.append(f"🟡 建议完善：{warn_count} 项警告")
        for r in results:
            if r["status"] == "WARN":
                lines.append(f"- **{r['id']}**（{r['standard']}）— {r['detail']}")
        lines.append("")

    lines.append(f"🟢 已通过：{pass_count} 项")
    for r in results:
        if r["status"] == "PASS":
            detail = f" — {r['detail']}" if r["detail"] else ""
            lines.append(f"- **{r['id']}**（{r['standard']}）{detail}")
    lines.append("")

    return "\n".join(lines)


def main(argv):
    if len(argv) != 1:
        print("usage: compliance_check.py <report.md>", file=sys.stderr)
        return 2
    report = Path(argv[0]).read_text(encoding="utf-8")
    results = run_checks(report)
    output = format_report(results)
    print(output)
    # Exit code: 0 if all pass, 1 if any warn/fail
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
