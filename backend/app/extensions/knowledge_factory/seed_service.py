"""种子数据导入服务 - 将种子数据导入数据库"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.knowledge_factory.models import ComplianceRule
from app.extensions.knowledge_factory.seed_loader import (
    SeedLoaderService,
    get_seed_loader,
)

logger = logging.getLogger(__name__)


class SeedImportResult:
    """种子数据导入结果"""

    def __init__(
        self,
        total: int = 0,
        created: int = 0,
        updated: int = 0,
        skipped: int = 0,
        errors: int = 0,
        error_messages: list[str] | None = None,
    ):
        self.total = total
        self.created = created
        self.updated = updated
        self.skipped = skipped
        self.errors = errors
        self.error_messages = error_messages or []

    @property
    def success(self) -> bool:
        return self.errors == 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
            "error_messages": self.error_messages,
            "success": self.success,
        }


class SeedImportService:
    """种子数据导入服务"""

    def __init__(self, seed_loader: SeedLoaderService | None = None):
        """
        初始化种子数据导入服务

        Args:
            seed_loader: 种子数据加载器实例
        """
        self.seed_loader = seed_loader or get_seed_loader()

    async def import_to_database(
        self,
        session: AsyncSession,
        force_update: bool = False,
        skip_existing: bool = True,
    ) -> SeedImportResult:
        """
        将种子数据导入数据库

        Args:
            session: 数据库会话
            force_update: 是否强制更新已存在的记录
            skip_existing: 是否跳过已存在的记录

        Returns:
            SeedImportResult: 导入结果
        """
        result = SeedImportResult()

        try:
            seed_data = self.seed_loader.load_seed_data()
            import_data = self.seed_loader.to_import_data()
            result.total = len(import_data)

            logger.info(f"开始导入 {result.total} 条种子数据...")

            for rule_data in import_data:
                try:
                    await self._import_single_rule(
                        session=session,
                        rule_data=rule_data,
                        force_update=force_update,
                        skip_existing=skip_existing,
                        result=result,
                    )
                except Exception as e:
                    await session.rollback()
                    result.errors += 1
                    result.error_messages.append(f"导入规则 {rule_data.get('rule_id', 'unknown')} 失败: {str(e)}")
                    logger.error(f"导入规则失败: {e}")

            await session.commit()

            logger.info(f"种子数据导入完成: 总数={result.total}, 新增={result.created}, 更新={result.updated}, 跳过={result.skipped}, 错误={result.errors}")

        except Exception as e:
            await session.rollback()
            result.errors += 1
            result.error_messages.append(f"导入过程发生错误: {str(e)}")
            logger.error(f"导入种子数据失败: {e}")

        return result

    async def _import_single_rule(
        self,
        session: AsyncSession,
        rule_data: dict,
        force_update: bool,
        skip_existing: bool,
        result: SeedImportResult,
    ) -> None:
        """导入单条规则"""
        rule_id = rule_data["rule_id"]

        stmt = select(ComplianceRule).where(ComplianceRule.rule_id == rule_id)
        existing_rule = await session.scalar(stmt)

        if existing_rule:
            if skip_existing and not force_update:
                result.skipped += 1
                logger.debug(f"跳过已存在的规则: {rule_id}")
                return

            for key, value in rule_data.items():
                if hasattr(existing_rule, key):
                    setattr(existing_rule, key, value)

            result.updated += 1
            logger.debug(f"更新规则: {rule_id}")
        else:
            new_rule = ComplianceRule(**rule_data)
            session.add(new_rule)
            result.created += 1
            logger.debug(f"创建规则: {rule_id}")

    async def check_seed_status(self, session: AsyncSession) -> dict:
        """
        检查种子数据导入状态

        Args:
            session: 数据库会话

        Returns:
            状态信息字典
        """
        seed_loader = get_seed_loader()
        seed_data = seed_loader.load_seed_data()

        stmt = select(ComplianceRule)
        all_rules = await session.scalars(stmt)
        all_rules_list = list(all_rules)

        existing_rule_ids = {rule.rule_id for rule in all_rules_list}
        seed_rule_ids = {rule.rule_id for rule in seed_data.rules}

        return {
            "seed_version": seed_data.version,
            "seed_total": len(seed_data.rules),
            "db_total": len(all_rules_list),
            "db_enabled": len([r for r in all_rules_list if r.enabled]),
            "db_disabled": len([r for r in all_rules_list if not r.enabled]),
            "in_seed_not_in_db": list(seed_rule_ids - existing_rule_ids),
            "in_db_not_in_seed": list(existing_rule_ids - seed_rule_ids),
            "up_to_date": existing_rule_ids == seed_rule_ids,
        }

    async def clear_seed_data(self, session: AsyncSession) -> int:
        """
        清除所有由种子数据创建的规则

        Args:
            session: 数据库会话

        Returns:
            删除的记录数
        """
        stmt = select(ComplianceRule).where(ComplianceRule.seed_version.isnot(None))
        rules = await session.scalars(stmt)
        rules_list = list(rules)

        for rule in rules_list:
            await session.delete(rule)

        await session.commit()

        logger.info(f"已清除 {len(rules_list)} 条种子数据规则")
        return len(rules_list)

    async def get_rule_statistics(self, session: AsyncSession) -> dict:
        """
        获取规则统计信息

        Args:
            session: 数据库会话

        Returns:
            统计信息字典
        """
        stmt = select(ComplianceRule)
        all_rules = await session.scalars(stmt)
        all_rules_list = list(all_rules)

        type_stats = {}
        severity_stats = {}
        industry_stats = {}

        for rule in all_rules_list:
            type_stats[rule.type] = type_stats.get(rule.type, 0) + 1
            severity_stats[rule.severity] = severity_stats.get(rule.severity, 0) + 1
            industry_stats[rule.industry] = industry_stats.get(rule.industry, 0) + 1

        return {
            "total": len(all_rules_list),
            "enabled": len([r for r in all_rules_list if r.enabled]),
            "disabled": len([r for r in all_rules_list if not r.enabled]),
            "from_seed": len([r for r in all_rules_list if r.seed_version]),
            "type_distribution": type_stats,
            "severity_distribution": severity_stats,
            "industry_distribution": industry_stats,
        }


async def import_seed_data(
    session: AsyncSession,
    force_update: bool = False,
    skip_existing: bool = True,
) -> SeedImportResult:
    """
    便捷函数：导入种子数据

    Args:
        session: 数据库会话
        force_update: 是否强制更新
        skip_existing: 是否跳过已存在

    Returns:
        SeedImportResult: 导入结果
    """
    service = SeedImportService()
    return await service.import_to_database(
        session=session,
        force_update=force_update,
        skip_existing=skip_existing,
    )
