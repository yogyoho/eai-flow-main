"""
内置验证器实现

提供各类验证器实现：数据一致性、标准检查、需求检查、空间检查、引用检查、工程检查、合规检查。
"""

import re
from typing import Any

from .core import (
    BaseValidator,
    CheckContext,
    CheckResult,
    ValidationIssue,
    SeverityLevel,
    register_validator,
)


@register_validator("data_consistency")
class DataConsistencyValidator(BaseValidator):
    """数据一致性验证器：检查报告中数值的一致性（如总计与分项之和）。"""

    def validate(self, context: CheckContext, rule: dict) -> list[ValidationIssue]:
        issues = []
        threshold = rule.get("config", {}).get("threshold", 0.01)
        fields = rule.get("config", {}).get("fields", [])
        for f in fields:
            if f not in context.extracted_fields:
                continue
            val = context.extracted_fields[f]
            if not isinstance(val, (int, float)):
                continue
            expected_sum = sum(
                context.extracted_fields.get(ff, 0)
                for ff in fields
                if ff != f and isinstance(context.extracted_fields.get(ff), (int, float))
            )
            if abs(val - expected_sum) / max(abs(val), 1) > threshold:
                issues.append(
                    ValidationIssue(
                        rule_id=rule.get("rule_id", ""),
                        rule_name=rule.get("name", "数据一致性检查"),
                        severity=SeverityLevel.WARNING,
                        check_result=CheckResult.FAIL,
                        message=f"字段 {f} 的值与分项之和不一致",
                        field_name=f,
                        source_value=val,
                        target_value=expected_sum,
                    )
                )
        return issues


@register_validator("standard_check")
class StandardCheckValidator(BaseValidator):
    """标准检查验证器：检查报告是否包含必需的章节和内容。"""

    def validate(self, context: CheckContext, rule: dict) -> list[ValidationIssue]:
        issues = []
        required_sections = rule.get("config", {}).get("required_sections", [])
        report_data = context.report_data or {}
        sections = report_data.get("sections", {})
        for section in required_sections:
            section_key = str(section).lower()
            found = any(section_key in str(k).lower() for k in sections.keys())
            if not found:
                issues.append(
                    ValidationIssue(
                        rule_id=rule.get("rule_id", ""),
                        rule_name=rule.get("name", "标准章节检查"),
                        severity=SeverityLevel.WARNING,
                        check_result=CheckResult.FAIL,
                        message=f"缺少必需的章节：{section}",
                        location=section,
                    )
                )
        return issues


@register_validator("requirement_check")
class RequirementCheckValidator(BaseValidator):
    """需求检查验证器：检查关键指标是否符合法规要求。"""

    def validate(self, context: CheckContext, rule: dict) -> list[ValidationIssue]:
        issues = []
        limits = rule.get("config", {}).get("limits", {})
        for field, limit in limits.items():
            val = context.extracted_fields.get(field)
            if val is None:
                continue
            try:
                val_num = float(val)
                if isinstance(limit, dict):
                    max_val = limit.get("max")
                    min_val = limit.get("min")
                    if max_val is not None and val_num > max_val:
                        issues.append(
                            ValidationIssue(
                                rule_id=rule.get("rule_id", ""),
                                rule_name=rule.get("name", "需求限值检查"),
                                severity=SeverityLevel(rule.get("severity", "warning")),
                                check_result=CheckResult.FAIL,
                                message=f"{field} 超过限值：{val_num} > {max_val}",
                                field_name=field,
                                source_value=val_num,
                                target_value=max_val,
                            )
                        )
                    if min_val is not None and val_num < min_val:
                        issues.append(
                            ValidationIssue(
                                rule_id=rule.get("rule_id", ""),
                                rule_name=rule.get("name", "需求限值检查"),
                                severity=SeverityLevel(rule.get("severity", "warning")),
                                check_result=CheckResult.FAIL,
                                message=f"{field} 低于最小限值：{val_num} < {min_val}",
                                field_name=field,
                                source_value=val_num,
                                target_value=min_val,
                            )
                        )
            except (TypeError, ValueError):
                pass
        return issues


@register_validator("spatial_check")
class SpatialCheckValidator(BaseValidator):
    """空间检查验证器：检查地理/空间信息的完整性和合理性。"""

    def validate(self, context: CheckContext, rule: dict) -> list[ValidationIssue]:
        issues = []
        required_fields = rule.get("config", {}).get("required_fields", [])
        report_data = context.report_data or {}
        for field in required_fields:
            if field not in report_data or not report_data[field]:
                issues.append(
                    ValidationIssue(
                        rule_id=rule.get("rule_id", ""),
                        rule_name=rule.get("name", "空间信息检查"),
                        severity=SeverityLevel.INFO,
                        check_result=CheckResult.FAIL,
                        message=f"缺少空间/地理信息：{field}",
                        field_name=field,
                    )
                )
        return issues


@register_validator("reference_check")
class ReferenceCheckValidator(BaseValidator):
    """引用检查验证器：检查法规/标准引用的有效性和完整性。"""

    def validate(self, context: CheckContext, rule: dict) -> list[ValidationIssue]:
        issues = []
        required_patterns = rule.get("config", {}).get("patterns", [])
        raw_text = context.raw_text or ""
        for pattern in required_patterns:
            if isinstance(pattern, str):
                if not re.search(pattern, raw_text):
                    issues.append(
                        ValidationIssue(
                            rule_id=rule.get("rule_id", ""),
                            rule_name=rule.get("name", "引用检查"),
                            severity=SeverityLevel.INFO,
                            check_result=CheckResult.FAIL,
                            message=f"未找到必需的引用模式：{pattern}",
                        )
                    )
        return issues


@register_validator("engineering_check")
class EngineeringCheckValidator(BaseValidator):
    """工程检查验证器：检查工程参数的合理性和逻辑一致性。"""

    def validate(self, context: CheckContext, rule: dict) -> list[ValidationIssue]:
        issues = []
        constraints = rule.get("config", {}).get("constraints", {})
        for field, constraint in constraints.items():
            val = context.extracted_fields.get(field)
            if val is None:
                continue
            try:
                val_num = float(val)
                if "greater_than" in constraint:
                    if val_num <= constraint["greater_than"]:
                        issues.append(
                            ValidationIssue(
                                rule_id=rule.get("rule_id", ""),
                                rule_name=rule.get("name", "工程参数检查"),
                                severity=SeverityLevel.WARNING,
                                check_result=CheckResult.FAIL,
                                message=f"{field} 必须大于 {constraint['greater_than']}，实际为 {val_num}",
                                field_name=field,
                                source_value=val_num,
                            )
                        )
            except (TypeError, ValueError):
                pass
        return issues


@register_validator("compliance_check")
class ComplianceCheckValidator(BaseValidator):
    """合规性检查验证器：通用合规性规则检查。"""

    def validate(self, context: CheckContext, rule: dict) -> list[ValidationIssue]:
        issues = []
        raw_text = context.raw_text or ""
        keywords = rule.get("config", {}).get("forbidden_keywords", [])
        for kw in keywords:
            if kw in raw_text:
                issues.append(
                    ValidationIssue(
                        rule_id=rule.get("rule_id", ""),
                        rule_name=rule.get("name", "合规性检查"),
                        severity=SeverityLevel.CRITICAL,
                        check_result=CheckResult.FAIL,
                        message=f"发现禁止关键词：{kw}",
                        suggestion="请移除或替换违规内容",
                    )
                )
        return issues
