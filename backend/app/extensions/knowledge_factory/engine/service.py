"""
规则执行服务

提供统一的规则执行入口，支持按规则类型匹配验证器。
"""

import logging
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .core import (
    BaseValidator,
    CheckContext,
    CheckResult,
    CheckResultSummary,
    SeverityLevel,
    ValidationIssue,
    ValidatorRegistry,
)
from .validators import (
    DataConsistencyValidator,
    StandardCheckValidator,
    RequirementCheckValidator,
    SpatialCheckValidator,
    ReferenceCheckValidator,
    EngineeringCheckValidator,
    ComplianceCheckValidator,
)

logger = logging.getLogger(__name__)


class ComplianceEngine:
    """
    合规规则执行引擎

    负责执行合规性检查，协调验证器和规则库。
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # 确保验证器已注册
        self._ensure_validators_registered()

    def _ensure_validators_registered(self):
        """确保所有内置验��器已注册"""
        # 手动导入并触发注册
        from . import validators  # noqa: F401

    async def check(
        self,
        context: CheckContext,
        rule_ids: Optional[list[str]] = None,
        db: Optional[AsyncSession] = None,
    ) -> CheckResultSummary:
        """
        执行合规性检查

        Args:
            context: 检查上下文（包含报告数据等）
            rule_ids: 可选，指定要检查的规则ID列表；None表示检查所有启用的规则
            db: 可选，数据库会话用于查询规则

        Returns:
            检查结果摘要
        """
        start_time = time.time()
        all_issues: list[ValidationIssue] = []

        try:
            # 获取要执行的规则
            rules = await self._get_rules(rule_ids, context, db)
            total_rules = len(rules)

            self.logger.info(f"开始执行 {total_rules} 条规则的检查")

            # 逐条执行规则
            for rule in rules:
                try:
                    issues = await self._execute_rule(context, rule)
                    all_issues.extend(issues)

                    # 如果设置了遇到失败就停止
                    if context.stop_on_first_fail and issues:
                        failed_issues = [i for i in issues if i.check_result == CheckResult.FAIL]
                        if failed_issues:
                            self.logger.info(f"遇到失败规则 {rule.get('rule_id')}，停止执行")
                            break

                except Exception as e:
                    self.logger.exception(f"执行规则 {rule.get('rule_id')} 时出错")
                    all_issues.append(ValidationIssue(
                        rule_id=rule.get("rule_id", ""),
                        rule_name=rule.get("name", ""),
                        severity=SeverityLevel.WARNING,
                        check_result=CheckResult.ERROR,
                        message=f"规则执行异常: {str(e)}",
                        details={"exception": str(e)}
                    ))

        except Exception as e:
            self.logger.exception("执行合规性检查时出错")
            raise

        # 计算结果摘要
        duration_ms = (time.time() - start_time) * 1000

        # 统计各类结果
        passed = len([i for i in all_issues if i.check_result == CheckResult.PASS])
        failed = len([i for i in all_issues if i.check_result == CheckResult.FAIL])
        warnings = len([i for i in all_issues if i.check_result == CheckResult.WARNING])
        errors = len([i for i in all_issues if i.check_result == CheckResult.ERROR])
        skipped = len([i for i in all_issues if i.check_result == CheckResult.SKIP])

        # 对于没有问题的规则（PASS），需要计算通过数
        passed = max(0, total_rules - failed - errors - skipped)

        # 记录执行日志（如果有数据库会话）
        if db is not None and (failed > 0 or warnings > 0):
            await self._log_execution(db, all_issues, context)

        return CheckResultSummary(
            total_rules=total_rules,
            passed=passed,
            failed=failed,
            warnings=warnings,
            errors=errors,
            skipped=skipped,
            duration_ms=duration_ms,
            issues=all_issues
        )

    async def _get_rules(
        self,
        rule_ids: Optional[list[str]],
        context: CheckContext,
        db: Optional[AsyncSession]
    ) -> list[dict]:
        """获取要执行的规则"""
        from ..models import ComplianceRule
        from sqlalchemy import select

        if db is None:
            # 如果没有数据库会话，返回内存中的种子数据
            return self._get_rules_from_seed(rule_ids, context)

        # 从数据库查询规则
        stmt = select(ComplianceRule).where(ComplianceRule.enabled == True)

        if rule_ids:
            stmt = stmt.where(ComplianceRule.rule_id.in_(rule_ids))

        # 根据上下文筛选匹配的规则
        if context.industry:
            stmt = stmt.where(ComplianceRule.industry == context.industry)

        if context.report_type:
            # 报告类型筛选（使用 PostgreSQL 数组包含）
            from sqlalchemy.dialects.postgresql import ARRAY
            stmt = stmt.where(ComplianceRule.report_types.contains([context.report_type]))

        result = await db.execute(stmt)
        rules = result.scalars().all()

        return [self._rule_to_dict(rule) for rule in rules]

    def _get_rules_from_seed(
        self,
        rule_ids: Optional[list[str]],
        context: CheckContext
    ) -> list[dict]:
        """从种子数据获取规则"""
        from ..seed_loader import get_seed_loader

        loader = get_seed_loader()
        rules = loader.rules

        # 过滤
        filtered_rules = []
        for rule in rules:
            # 如果指定了规则ID，只保留这些规则
            if rule_ids and rule.rule_id not in rule_ids:
                continue

            # 行业匹配
            if context.industry and rule.industry != context.industry:
                continue

            # 报告类型匹配
            if context.report_type and context.report_type not in rule.report_types:
                continue

            filtered_rules.append(rule.model_dump())

        return filtered_rules

    def _rule_to_dict(self, rule) -> dict:
        """将规则模型转换为字典"""
        return {
            "id": str(rule.id),
            "rule_id": rule.rule_id,
            "name": rule.name,
            "type": rule.type,
            "type_name": rule.type_name,
            "severity": rule.severity,
            "severity_name": rule.severity_name,
            "enabled": rule.enabled,
            "description": rule.description,
            "industry": rule.industry,
            "industry_name": rule.industry_name,
            "report_types": rule.report_types,
            "applicable_regions": rule.applicable_regions,
            "national_level": rule.national_level,
            "source_sections": rule.source_sections,
            "target_sections": rule.target_sections,
            "validation_config": rule.validation_config,
            "error_message": rule.error_message,
            "auto_fix_suggestion": rule.auto_fix_suggestion,
        }

    async def _execute_rule(
        self,
        context: CheckContext,
        rule: dict
    ) -> list[ValidationIssue]:
        """执行单条规则"""
        rule_type = rule.get("type", "")
        validator_class = ValidatorRegistry.get_validator(rule_type)

        if validator_class is None:
            self.logger.warning(f"未找到规则类型对应的验证器: {rule_type}")
            return []

        # 创建验证器实例
        validator = validator_class()

        # 执行验证
        try:
            issues = validator.validate(context, rule)

            # 为没有问题的规则添加 PASS 状态
            if not issues:
                issues.append(ValidationIssue(
                    rule_id=rule.get("rule_id", ""),
                    rule_name=rule.get("name", ""),
                    severity=SeverityLevel.INFO,
                    check_result=CheckResult.PASS,
                    message="检查通过"
                ))

            return issues

        except Exception as e:
            self.logger.exception(f"验证器执行失败: {e}")
            return [ValidationIssue(
                rule_id=rule.get("rule_id", ""),
                rule_name=rule.get("name", ""),
                severity=SeverityLevel.WARNING,
                check_result=CheckResult.ERROR,
                message=f"验证器执行失败: {str(e)}",
                details={"exception": str(e)}
            )]

    async def _log_execution(
        self,
        db: AsyncSession,
        issues: list[ValidationIssue],
        context: CheckContext,
    ) -> None:
        """记录执行日志"""
        try:
            from ..models import ComplianceRule, ComplianceRuleLog
            from sqlalchemy import select

            for issue in issues:
                # 跳过 PASS 状态
                if issue.check_result == CheckResult.PASS:
                    continue

                # 查找规则
                stmt = select(ComplianceRule).where(
                    ComplianceRule.rule_id == issue.rule_id
                )
                result = await db.execute(stmt)
                rule = result.scalar_one_or_none()

                if not rule:
                    self.logger.warning(f"找不到规则: {issue.rule_id}")
                    continue

                # 创建日志记录
                log_entry = ComplianceRuleLog(
                    rule_id=rule.id,
                    thread_id=context.thread_id,
                    document_id=None,
                    check_result=issue.check_result.value,
                    check_details={
                        "severity": issue.severity.value,
                        "message": issue.message,
                        "field_name": issue.field_name,
                        "suggestion": issue.suggestion,
                        "details": issue.details,
                    },
                    error_info=issue.message if issue.check_result == CheckResult.ERROR else None,
                    executed_by=context.user_id,
                )

                db.add(log_entry)

            await db.commit()
            self.logger.info(f"记录了 {len([i for i in issues if i.check_result != CheckResult.PASS])} 条执行日志")

        except Exception as e:
            self.logger.exception(f"记录执行日志失败: {e}")


# 全局引擎实例
_engine: Optional[ComplianceEngine] = None


def get_engine() -> ComplianceEngine:
    """获取规则执行引擎单例"""
    global _engine
    if _engine is None:
        _engine = ComplianceEngine()
    return _engine