from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SeedRuleData(BaseModel):
    """种子规则数据模型"""
    rule_id: str
    name: str
    type: str
    type_name: str = ""
    severity: str
    severity_name: str = ""
    enabled: bool = True
    description: str = ""
    industry: str = ""
    industry_name: str = ""
    report_types: list[str] = Field(default_factory=list)
    applicable_regions: list[str] = Field(default_factory=list)
    national_level: bool = True
    source_sections: list[str] = Field(default_factory=list)
    target_sections: list[str] = Field(default_factory=list)
    validation_config: dict = Field(default_factory=dict)
    error_message: str = ""
    auto_fix_suggestion: str = ""


class SeedDataManifest(BaseModel):
    """种子数据清单"""
    version: str
    description: str
    industries: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    rules: list[SeedRuleData] = Field(default_factory=list)


class SeedLoaderService:
    """种子数据加载服务"""

    def __init__(self, seed_file_path: Optional[str] = None):
        """
        初始化种子数据加载服务
        
        Args:
            seed_file_path: 种子数据文件路径，默认使用项目中的文件
        """
        if seed_file_path:
            self.seed_file_path = Path(seed_file_path)
        else:
            # 实际文件在 data 子目录
            self.seed_file_path = Path(__file__).parent / "data" / "compliance_rules_seed.json"
        
        self._seed_data: Optional[SeedDataManifest] = None

    def load_seed_data(self) -> SeedDataManifest:
        """
        加载种子数据文件
        
        Returns:
            SeedDataManifest: 种子数据清单
            
        Raises:
            FileNotFoundError: 种子数据文件不存在
            json.JSONDecodeError: JSON解析失败
        """
        if not self.seed_file_path.exists():
            raise FileNotFoundError(f"种子数据文件不存在: {self.seed_file_path}")
        
        logger.info(f"正在加载种子数据: {self.seed_file_path}")
        
        with open(self.seed_file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        self._seed_data = SeedDataManifest(**raw_data)
        
        logger.info(
            f"种子数据加载成功: 版本={self._seed_data.version}, "
            f"规则数量={len(self._seed_data.rules)}"
        )
        
        return self._seed_data

    @property
    def seed_data(self) -> Optional[SeedDataManifest]:
        """获取已加载的种子数据"""
        if self._seed_data is None:
            self.load_seed_data()
        return self._seed_data

    @property
    def rules(self) -> list[SeedRuleData]:
        """获取所有种子规则"""
        return self.seed_data.rules

    @property
    def version(self) -> str:
        """获取种子数据版本"""
        return self.seed_data.version

    def get_rules_by_type(self, rule_type: str) -> list[SeedRuleData]:
        """
        按规则类型筛选规则
        
        Args:
            rule_type: 规则类型，如 'standard_check'
            
        Returns:
            符合条件的规则列表
        """
        return [r for r in self.rules if r.type == rule_type]

    def get_rules_by_severity(self, severity: str) -> list[SeedRuleData]:
        """
        按严重级别筛选规则
        
        Args:
            severity: 严重级别，如 'critical'
            
        Returns:
            符合条件的规则列表
        """
        return [r for r in self.rules if r.severity == severity]

    def get_rules_by_industry(self, industry: str) -> list[SeedRuleData]:
        """
        按行业筛选规则
        
        Args:
            industry: 行业代码
            
        Returns:
            符合条件的规则列表
        """
        return [r for r in self.rules if r.industry == industry]

    def get_rules_by_report_type(self, report_type: str) -> list[SeedRuleData]:
        """
        按报告类型筛选规则
        
        Args:
            report_type: 报告类型，如 'coal_mining_planning_eia'
            
        Returns:
            符合条件的规则列表
        """
        return [r for r in self.rules if report_type in r.report_types]

    def get_enabled_rules(self) -> list[SeedRuleData]:
        """获取所有启用的规则"""
        return [r for r in self.rules if r.enabled]

    def get_rule_by_id(self, rule_id: str) -> Optional[SeedRuleData]:
        """
        根据规则ID获取规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            规则数据或None
        """
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def get_statistics(self) -> dict:
        """
        获取种子数据统计信息
        
        Returns:
            统计信息字典
        """
        rules = self.rules
        
        type_stats = {}
        for rule in rules:
            type_stats[rule.type] = type_stats.get(rule.type, 0) + 1
        
        severity_stats = {}
        for rule in rules:
            severity_stats[rule.severity] = severity_stats.get(rule.severity, 0) + 1
        
        report_type_stats = {}
        for rule in rules:
            for rt in rule.report_types:
                report_type_stats[rt] = report_type_stats.get(rt, 0) + 1
        
        industry_stats = {}
        for rule in rules:
            industry_stats[rule.industry] = industry_stats.get(rule.industry, 0) + 1
        
        return {
            "version": self.version,
            "total_rules": len(rules),
            "enabled_rules": len(self.get_enabled_rules()),
            "disabled_rules": len(rules) - len(self.get_enabled_rules()),
            "type_distribution": type_stats,
            "severity_distribution": severity_stats,
            "report_type_distribution": report_type_stats,
            "industry_distribution": industry_stats,
            "sources": self.seed_data.sources,
        }

    def to_import_data(self) -> list[dict]:
        """
        转换为导入数据格式
        
        Returns:
            可直接用于数据库导入的规则数据列表
        """
        import_data = []
        
        for rule in self.rules:
            now = datetime.now()
            rule_dict = {
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
                "seed_version": self.version,
                "created_at": now,
                "updated_at": now,
            }
            import_data.append(rule_dict)
        
        return import_data


# 全局单例
_seed_loader: Optional[SeedLoaderService] = None


def get_seed_loader() -> SeedLoaderService:
    """
    获取种子数据加载器单例
    
    Returns:
        SeedLoaderService实例
    """
    global _seed_loader
    if _seed_loader is None:
        _seed_loader = SeedLoaderService()
    return _seed_loader


def load_seed_data() -> SeedDataManifest:
    """
    便捷函数：加载种子数据
    
    Returns:
        SeedDataManifest: 种子数据清单
    """
    return get_seed_loader().load_seed_data()
