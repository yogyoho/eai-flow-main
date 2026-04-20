"""
规则执行日志服务

负责记录和管理规则执行的日志。
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .core import ValidationIssue, CheckResult

logger = logging.getLogger(__name__)


class RuleExecutionLogger:
    """
    规则执行日志记录器

    将规则执行结果记录到数据库。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_execution(
        self,
        rule_id: UUID,
        thread_id: Optional[UUID] = None,
        document_id: Optional[str] = None,
        check_result: str = "pass",
        check_details: Optional[dict] = None,
        error_info: Optional[str] = None,
        executed_by: Optional[UUID] = None,
    ) -> "ComplianceRuleLog":
        """
        记录单条规则执行结果

        Args:
            rule_id: 规则ID
            thread_id: 会话ID（可选）
            document_id: 文档ID（可选）
            check_result: 检查结果 (pass/fail/warning/error/skip)
            check_details: 检查详情（可选）
            error_info: 错误信息（可选）
            executed_by: 执行用户ID（可选）

        Returns:
            ComplianceRuleLog: 创建的日志记录
        """
        from ..models import ComplianceRuleLog

        log_entry = ComplianceRuleLog(
            rule_id=rule_id,
            thread_id=thread_id,
            document_id=document_id,
            check_result=check_result,
            check_details=check_details,
            error_info=error_info,
            executed_by=executed_by,
        )

        self.db.add(log_entry)
        await self.db.commit()
        await self.db.refresh(log_entry)

        logger.info(f"记录规则执行日志: rule_id={rule_id}, result={check_result}")
        return log_entry

    async def log_issues(
        self,
        issues: list[ValidationIssue],
        thread_id: Optional[UUID] = None,
        document_id: Optional[str] = None,
        executed_by: Optional[UUID] = None,
    ) -> int:
        """
        批量记录验证问题

        Args:
            issues: 验证问题列表
            thread_id: 会话ID
            document_id: 文档ID
            executed_by: 执行用户ID

        Returns:
            int: 记录的日志数量
        """
        from sqlalchemy import select
        from ..models import ComplianceRule, ComplianceRuleLog

        count = 0

        for issue in issues:
            # 查找规则ID
            stmt = select(ComplianceRule).where(
                ComplianceRule.rule_id == issue.rule_id
            )
            result = await self.db.execute(stmt)
            rule = result.scalar_one_or_none()

            if not rule:
                logger.warning(f"找不到规则: {issue.rule_id}")
                continue

            # 记录日志
            log_entry = ComplianceRuleLog(
                rule_id=rule.id,
                thread_id=thread_id,
                document_id=document_id,
                check_result=issue.check_result.value,
                check_details={
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "field_name": issue.field_name,
                    "source_value": str(issue.source_value) if issue.source_value else None,
                    "target_value": str(issue.target_value) if issue.target_value else None,
                    "location": issue.location,
                    "suggestion": issue.suggestion,
                    "details": issue.details,
                },
                error_info=issue.message if issue.check_result == CheckResult.ERROR else None,
                executed_by=executed_by,
            )

            self.db.add(log_entry)
            count += 1

        if count > 0:
            await self.db.commit()
            logger.info(f"批量记录 {count} 条规则执行日志")

        return count

    async def get_rule_logs(
        self,
        rule_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list["ComplianceRuleLog"]:
        """
        获取规则执行日志

        Args:
            rule_id: 规则ID
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            list[ComplianceRuleLog]: 日志列表
        """
        from sqlalchemy import select, desc
        from ..models import ComplianceRuleLog

        stmt = (
            select(ComplianceRuleLog)
            .where(ComplianceRuleLog.rule_id == rule_id)
            .order_by(desc(ComplianceRuleLog.executed_at))
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_rule_statistics(
        self,
        rule_id: UUID,
    ) -> dict:
        """
        获取规则执行统计

        Args:
            rule_id: 规则ID

        Returns:
            dict: 统计数据
        """
        from sqlalchemy import select, func, and_
        from ..models import ComplianceRuleLog

        # 总执行次数
        total_stmt = select(func.count()).where(
            ComplianceRuleLog.rule_id == rule_id
        )
        total_result = await self.db.execute(total_stmt)
        total = total_result.scalar() or 0

        # 按结果分组统计
        from sqlalchemy.dialects.postgresql import array

        stats = {
            "total_executions": total,
            "pass_count": 0,
            "fail_count": 0,
            "warning_count": 0,
            "error_count": 0,
            "skip_count": 0,
            "last_executed_at": None,
            "last_failed_at": None,
        }

        if total == 0:
            return stats

        # 获取各类结果数量
        for result_type in ["pass", "fail", "warning", "error", "skip"]:
            count_stmt = select(func.count()).where(
                and_(
                    ComplianceRuleLog.rule_id == rule_id,
                    ComplianceRuleLog.check_result == result_type,
                )
            )
            result = await self.db.execute(count_stmt)
            count = result.scalar() or 0

            key = f"{result_type}_count"
            if key in stats:
                stats[key] = count

        # 获取最近执行时间
        latest_stmt = (
            select(ComplianceRuleLog.executed_at)
            .where(ComplianceRuleLog.rule_id == rule_id)
            .order_by(desc(ComplianceRuleLog.executed_at))
            .limit(1)
        )
        latest_result = await self.db.execute(latest_stmt)
        latest = latest_result.scalar_one_or_none()
        if latest:
            stats["last_executed_at"] = latest.isoformat() if isinstance(latest, datetime) else str(latest)

        # 获取最近失败时间
        failed_stmt = (
            select(ComplianceRuleLog.executed_at)
            .where(
                and_(
                    ComplianceRuleLog.rule_id == rule_id,
                    ComplianceRuleLog.check_result.in_(["fail", "warning"]),
                )
            )
            .order_by(desc(ComplianceRuleLog.executed_at))
            .limit(1)
        )
        failed_result = await self.db.execute(failed_stmt)
        failed = failed_result.scalar_one_or_none()
        if failed:
            stats["last_failed_at"] = failed.isoformat() if isinstance(failed, datetime) else str(failed)

        return stats

    async def get_trigger_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        industry: Optional[str] = None,
    ) -> dict:
        """
        获取触发统计

        Args:
            start_date: 统计起始日期
            end_date: 统计结束日期
            industry: 行业筛选

        Returns:
            dict: 触发统计数据
        """
        from sqlalchemy import select, func, and_
        from ..models import ComplianceRule, ComplianceRuleLog

        # 基础查询
        conditions = []
        if start_date:
            conditions.append(ComplianceRuleLog.executed_at >= start_date)
        if end_date:
            conditions.append(ComplianceRuleLog.executed_at <= end_date)

        # 总触发次数
        total_stmt = select(func.count()).where(*conditions) if conditions else select(func.count())
        total_result = await self.db.execute(total_stmt)
        total_triggers = total_result.scalar() or 0

        # 失败/警告次数
        blocked_stmt = (
            select(func.count())
            .where(
                and_(
                    *conditions,
                    ComplianceRuleLog.check_result.in_(["fail", "warning"]),
                )
            ) if conditions else
            select(func.count()).where(
                ComplianceRuleLog.check_result.in_(["fail", "warning"])
            )
        )
        blocked_result = await self.db.execute(blocked_stmt)
        blocked_triggers = blocked_result.scalar() or 0

        # 按规则分组统计
        by_rule_stmt = (
            select(
                ComplianceRuleLog.rule_id,
                func.count().label("trigger_count"),
                func.sum(
                    func.cast(
                        ComplianceRuleLog.check_result.in_(["fail", "warning"]),
                        func.Integer,
                    )
                ).label("block_count"),
            )
            .group_by(ComplianceRuleLog.rule_id)
            .order_by(func.count().desc())
            .limit(20)
        )

        if conditions:
            by_rule_stmt = by_rule_stmt.where(and_(*conditions))

        by_rule_result = await self.db.execute(by_rule_stmt)
        by_rule_rows = by_rule_result.all()

        # 获取规则名称
        top_rules = []
        for row in by_rule_rows:
            rule_stmt = select(ComplianceRule).where(ComplianceRule.id == row.rule_id)
            rule_result = await self.db.execute(rule_stmt)
            rule = rule_result.scalar_one_or_none()

            top_rules.append({
                "rule_id": rule.rule_id if rule else str(row.rule_id),
                "rule_name": rule.name if rule else "未知规则",
                "trigger_count": row.trigger_count,
                "block_count": row.block_count or 0,
            })

        return {
            "total_triggers": total_triggers,
            "blocked_triggers": blocked_triggers,
            "pass_rate": (
                (total_triggers - blocked_triggers) / total_triggers * 100
                if total_triggers > 0 else 100
            ),
            "top_rules": top_rules,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }


# 类型注解引用
ComplianceRuleLog = "ComplianceRuleLog"