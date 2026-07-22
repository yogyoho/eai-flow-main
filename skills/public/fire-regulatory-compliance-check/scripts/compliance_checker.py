#!/usr/bin/env python3
"""
Fire Code Compliance Checker
Validates fire protection design reports (Markdown) against GB standards.
"""

import argparse
import re
import sys
from pathlib import Path
from datetime import datetime


class ComplianceChecker:
    def __init__(self, report_path: str):
        self.report_path = Path(report_path)
        self.findings = []
        self.passed = 0
        self.warnings = 0
        self.failed = 0

    def load_report(self) -> str:
        with open(self.report_path, 'r', encoding='utf-8') as f:
            return f.read()

    # ── 1. 火灾危险性分类 (GB50016 / GB50160) ──

    def check_fire_hazard_classification(self, content: str):
        patterns = [
            r'火灾危险性分类[：:]\s*([甲乙丙丁戊])类',
            r'火灾危险[性级][：:]\s*(轻危险级|中危险级|严重危险级)',
            r'([甲乙丙丁戊])类\s*(火灾危险性|危险)',
            r'生产火灾危险性[：:]\s*([甲乙丙丁戊])',
            r'储存物品?火灾危险性[：:]\s*([甲乙丙丁戊])',
            r'\*\*([甲乙丙丁戊])类\*\*',       # bold: **甲类**
            r'[：:]\s*([甲乙丙丁戊])类\s*$',   # line ending with : 甲类
        ]
        for p in patterns:
            if re.search(p, content):
                self._add('火灾危险性分类', 'GB50016/GB50160', 'PASS',
                          '火灾危险性分类已明确标注')
                return
        self._add('火灾危险性分类', 'GB50016/GB50160', 'FAIL',
                  '未找到明确的火灾危险性分类（甲/乙/丙/丁/戊类）标注——第3章必须包含')

    # ── 2. 建筑耐火等级 (GB50016 §3.2.1, §5.2.1) ──

    def check_fire_resistance_rating(self, content: str):
        patterns = [
            r'耐火等级[：:]\s*(一|二|三|四)级',
            r'耐火等级\s*(一|二|三|四)级',
            r'燃烧性能[：:]\s*(不燃|难燃|可燃)',
            r'耐火极限[：:≥≥]?\s*\d+\.?\d*\s*h',
            r'\|\s*(一|二|三|四)级\s*\|',     # table cell: | 二级 |
        ]
        for p in patterns:
            if re.search(p, content):
                self._add('建筑耐火等级', 'GB50016 §3.2.1/§5.2.1', 'PASS',
                          '耐火等级信息已标注')
                return
        self._add('建筑耐火等级', 'GB50016 §3.2.1/§5.2.1', 'FAIL',
                  '未找到耐火等级（一/二/三/四级）标注——第4章必须包含')

    # ── 3. 防火间距 (GB50016 §5.2 / GB50160) ──

    def check_fire_separation(self, content: str):
        patterns = [
            r'防火间距[：:≥≥]?\s*\d+',
            r'间距[：:]\s*\d+\s*m',
            r'防火间距',
        ]
        for p in patterns:
            if re.search(p, content):
                self._add('防火间距', 'GB50016 §5.2/GB50160', 'PASS',
                          '防火间距信息已标注')
                return
        self._add('防火间距', 'GB50016 §5.2/GB50160', 'WARN',
                  '建议补充防火间距的具体数值——第4章总平面布置部分')

    # ── 4. 消防给水系统 (GB50974) ──

    def check_fire_water_system(self, content: str):
        keywords = ['消防水量', '室外消火栓', '室内消火栓', '消防水池',
                    '消防水泵', '消防给水', '消火栓系统']
        found = [k for k in keywords if k in content]
        if len(found) >= 3:
            self._add('消防给水系统', 'GB50974-2014', 'PASS',
                      f'消防给水要素齐全 ({len(found)}/{len(keywords)}项)')
        elif len(found) >= 1:
            self._add('消防给水系统', 'GB50974-2014', 'WARN',
                      f'消防给水要素不完整 ({len(found)}/{len(keywords)}项)，缺少: {", ".join(k for k in keywords if k not in found)}')
        else:
            self._add('消防给水系统', 'GB50974-2014', 'FAIL',
                      '完全未涉及消防给水系统——第5章必须包含')

    # ── 5. 火灾自动报警系统 (GB50116) ──

    def check_fire_alarm_system(self, content: str):
        keywords = ['感烟探测器', '感温探测器', '手动报警按钮',
                    '火灾报警控制器', '火灾自动报警', '报警系统']
        found = [k for k in keywords if k in content]
        if len(found) >= 3:
            self._add('火灾自动报警系统', 'GB50116-2013', 'PASS',
                      f'报警系统要素齐全 ({len(found)}/{len(keywords)}项)')
        elif len(found) >= 1:
            self._add('火灾自动报警系统', 'GB50116-2013', 'WARN',
                      f'报警系统要素不完整 ({len(found)}/{len(keywords)}项)')
        else:
            self._add('火灾自动报警系统', 'GB50116-2013', 'FAIL',
                      '完全未涉及火灾报警系统——第5章必须包含')

    # ── 6. 灭火器配置 (GB50140) ──

    def check_fire_extinguishers(self, content: str):
        keywords = ['灭火器', 'MF/ABC', 'MT', 'MFZ', 'MFT', '灭火器箱',
                    '灭火器配置', '保护距离']
        found = [k for k in keywords if k in content]
        if len(found) >= 2:
            self._add('建筑灭火器配置', 'GB50140-2005', 'PASS',
                      f'灭火器配置已说明 ({len(found)}/{len(keywords)}项)')
        elif len(found) >= 1:
            self._add('建筑灭火器配置', 'GB50140-2005', 'WARN',
                      '灭火器配置信息不够详细，建议补充型号和数量')
        else:
            self._add('建筑灭火器配置', 'GB50140-2005', 'FAIL',
                      '未提及灭火器配置——第5章必须包含')

    # ── 7. 爆炸危险环境电气 (GB50058) ──

    def check_explosive_atmosphere_electrical(self, content: str):
        keywords = ['爆炸危险', '防爆', '爆炸环境', '危险区域划分',
                    'GB50058', '防爆等级', '隔爆', '本安']
        found = [k for k in keywords if k in content]
        if len(found) >= 2:
            self._add('爆炸危险环境电气', 'GB50058-2014', 'PASS',
                      f'防爆电气设计已说明 ({len(found)}/{len(keywords)}项)')
        elif len(found) >= 1:
            self._add('爆炸危险环境电气', 'GB50058-2014', 'WARN',
                      '防爆电气设计不够详细——化工项目应在第4章补充')
        else:
            self._add('爆炸危险环境电气', 'GB50058-2014', 'WARN',
                      '化工项目建议补充爆炸危险区域划分和防爆电气设计（GB50058）')

    # ── 8. 灭火救援设施 (GB50016 §7.1) ──

    def check_fire_fighting_access(self, content: str):
        keywords = ['消防车道', '消防登高', '回转场地', '消防通道',
                    '消防救援', '消防车']
        found = [k for k in keywords if k in content]
        if len(found) >= 2:
            self._add('灭火救援设施', 'GB50016 §7.1', 'PASS',
                      f'救援设施已说明 ({len(found)}/{len(keywords)}项)')
        elif len(found) >= 1:
            self._add('灭火救援设施', 'GB50016 §7.1', 'WARN',
                      '灭火救援设施不够详细——第6章应补充消防车道宽度和回转场地')
        else:
            self._add('灭火救援设施', 'GB50016 §7.1', 'FAIL',
                      '完全未涉及灭火救援设施——第6章必须包含')

    # ── 9. 标准引用完整性 ──

    def check_standards_referenced(self, content: str):
        required = [
            (r'GB\s*50160', '石油化工企业设计防火标准'),
            (r'GB\s*50016', '建筑设计防火规范'),
            (r'GB\s*50058', '爆炸危险环境电力装置设计规范'),
            (r'GB\s*50116', '火灾自动报警系统设计规范'),
            (r'GB\s*50140', '建筑灭火器配置设计规范'),
            (r'GB\s*50974', '消防给水及消火栓系统技术规范'),
        ]
        found_std = []
        missing_std = []
        for pat, name in required:
            if re.search(pat, content):
                found_std.append(name)
            else:
                missing_std.append(name)
        n_found = len(found_std)
        if n_found >= 5:
            self._add('标准引用完整性', '—', 'PASS',
                      f'已引用 {n_found}/6 项核心标准')
        elif n_found >= 3:
            self._add('标准引用完整性', '—', 'WARN',
                      f'仅引用 {n_found}/6 项标准，缺少: {", ".join(missing_std)}')
        else:
            self._add('标准引用完整性', '—', 'FAIL',
                      f'仅引用 {n_found}/6 项标准——第1章必须列出主要设计标准')

    # ── 10. 法律合规 (消防法 2019) ──

    def check_legal_compliance(self, content: str):
        keywords = ['消防法', '中华人民共和国消防法', '建设工程消防设计审查',
                    '消防设计审查', '消防验收']
        found = [k for k in keywords if k in content]
        if len(found) >= 1:
            self._add('法律合规', '消防法（2019修订）', 'PASS',
                      '已引用消防法律法规')
        else:
            self._add('法律合规', '消防法（2019修订）', 'WARN',
                      '建议在第1章补充引用《中华人民共和国消防法》（2019修订）')

    # ── helpers ──

    def _add(self, item: str, standard: str, status: str, detail: str):
        self.findings.append({'item': item, 'standard': standard,
                              'status': status, 'detail': detail})
        if status == 'PASS':
            self.passed += 1
        elif status == 'FAIL':
            self.failed += 1
        else:
            self.warnings += 1

    def run_checks(self):
        content = self.load_report()
        self.check_fire_hazard_classification(content)
        self.check_fire_resistance_rating(content)
        self.check_fire_separation(content)
        self.check_fire_water_system(content)
        self.check_fire_alarm_system(content)
        self.check_fire_extinguishers(content)
        self.check_explosive_atmosphere_electrical(content)
        self.check_fire_fighting_access(content)
        self.check_standards_referenced(content)
        self.check_legal_compliance(content)

    def generate_report(self) -> str:
        lines = [
            "# 消防设计合规检查报告\n",
            f"**检查文件**: {self.report_path.name}",
            f"**检查日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**通过**: {self.passed}  |  **警告**: {self.warnings}  |  **不通过**: {self.failed}",
            "",
            "## 检查结果",
            "",
            "| # | 检查项目 | 标准 | 状态 | 详情 |",
            "|---|----------|------|------|------|",
        ]
        for i, f in enumerate(self.findings, 1):
            icon = {'PASS': '✅', 'WARN': '⚠️', 'FAIL': '❌'}.get(f['status'], '?')
            lines.append(f"| {i} | {f['item']} | {f['standard']} | {icon} {f['status']} | {f['detail']} |")

        lines.append("")
        lines.append("## 整改建议")
        lines.append("")
        fails = [f for f in self.findings if f['status'] == 'FAIL']
        warns = [f for f in self.findings if f['status'] == 'WARN']
        if fails:
            lines.append("### ❌ 必须修复")
            for f in fails:
                lines.append(f"- **{f['item']}** — {f['detail']}")
        if warns:
            lines.append("\n### ⚠️ 建议完善")
            for f in warns:
                lines.append(f"- **{f['item']}** — {f['detail']}")
        if not fails and not warns:
            lines.append("✅ 全部 10 项检查通过，报告合规。")
        return "\n".join(lines) + "\n"

    def save_report(self, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(self.generate_report())


def main():
    parser = argparse.ArgumentParser(description='Fire Code Compliance Checker')
    parser.add_argument('--report', required=True,
                        help='Path to fire protection report (Markdown .md)')
    parser.add_argument('--output', required=True,
                        help='Path to output compliance report (.md)')
    args = parser.parse_args()

    checker = ComplianceChecker(args.report)
    checker.run_checks()
    checker.save_report(args.output)

    # Console summary (plain text for cross-platform compatibility)
    print(f"\n合规检查完成: PASS={checker.passed} WARN={checker.warnings} FAIL={checker.failed}")
    return 0 if checker.failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
