"""
规则执行引擎 - 核心模块

提供统一的规则验证框架，支持多种验证器类型。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class CheckResult(str, Enum):
    """检查结果枚举"""
    PASS = "pass"           # 通过
    FAIL = "fail"           # 失败
    WARNING = "warning"      # 警告
    ERROR = "error"         # 错误（执行异常）
    SKIP = "skip"           # 跳过（条件不满足）


class SeverityLevel(str, Enum):
    """严重级别"""
    CRITICAL = "critical"    # 严重
    WARNING = "warning"     # 警告
    INFO = "info"           # 提示


@dataclass
class ValidationIssue:
    """验证问题/违规项"""
    rule_id: str                          # 规则ID
    rule_name: str                        # 规则名称
    severity: SeverityLevel               # 严重级别
    check_result: CheckResult             # 检查结果
    message: str                          # 问题描述
    field_name: Optional[str] = None      # 涉及的字段名
    source_value: Optional[Any] = None    # 源值（用于数据一致性检查）
    target_value: Optional[Any] = None    # 目标值
    location: Optional[str] = None        # 位置（章节、段落等）
    suggestion: Optional[str] = None      # 修复建议
    details: dict = field(default_factory=dict)  # 额外详情


@dataclass
class CheckContext:
    """验证执行上下文"""
    # 报告内容（结构化数据）
    report_data: dict                    # 报告结构化数据，如 {"sections": {...}, "tables": {...}}
    # 原始文本内容
    raw_text: Optional[str] = None        # 原始文本（用于正则匹配）
    # 提取的字段值
    extracted_fields: dict = field(default_factory=dict)  # {"SO2排放量": 12.5, "NOx排放量": 8.3}
    # 报告元数据
    report_type: Optional[str] = None     # 报告类型
    industry: Optional[str] = None        # 行业
    region: Optional[str] = None          # 地区
    # 执行参数
    check_all: bool = True               # 是否检查所有规则（false则只检查匹配的）
    stop_on_first_fail: bool = False     # 遇到第一个失败就停止
    # 用户上下文
    user_id: Optional[UUID] = None        # 执行用户ID
    thread_id: Optional[UUID] = None      # 会话ID


@dataclass
class CheckResultSummary:
    """检查结果摘要"""
    total_rules: int                      # 总规则数
    passed: int                           # 通过数
    failed: int                           # 失败数
    warnings: int                         # 警告数
    errors: int                           # 错误数
    skipped: int                          # 跳过数
    duration_ms: float                    # 执行耗时（毫秒）
    issues: list[ValidationIssue] = field(default_factory=list)  # 所有问题列表

    @property
    def success(self) -> bool:
        """是否全部通过"""
        return self.failed == 0 and self.errors == 0

    @property
    def has_critical_issues(self) -> bool:
        """是否有严重问题"""
        return any(i.severity == SeverityLevel.CRITICAL for i in self.issues)


class BaseValidator(ABC):
    """
    验证器基类

    所有具体验证器都应继承此类并实现 validate 方法。
    """

    # 验证器类型标识
    VALIDATOR_TYPE: str = ""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def validate(
        self,
        context: CheckContext,
        rule_config: dict
    ) -> list[ValidationIssue]:
        """
        执行验证

        Args:
            context: 验证执行上下文
            rule_config: 规则配置（包含 validation_config 等）

        Returns:
            验证问题列表（空列表表示通过）
        """
        pass

    def skip(self, message: str = "条件不满足，跳过验证") -> list[ValidationIssue]:
        """返回跳过结果"""
        return []

    def error(self, message: str, details: dict = None) -> list[ValidationIssue]:
        """返回错误结果"""
        return [ValidationIssue(
            rule_id="",
            rule_name="",
            severity=SeverityLevel.WARNING,
            check_result=CheckResult.ERROR,
            message=f"验证执行错误: {message}",
            details=details or {}
        )]


class ValidatorRegistry:
    """
    验证器注册表

    管理所有验证器类型，支持根据规则类型自动选择对应的��证器。
    """

    _validators: dict[str, type[BaseValidator]] = {}
    _instance: Optional["ValidatorRegistry"] = None

    @classmethod
    def get_instance(cls) -> "ValidatorRegistry":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = ValidatorRegistry()
        return cls._instance

    @classmethod
    def register(cls, rule_type: str, validator_class: type[BaseValidator]):
        """注册验证器"""
        cls._validators[rule_type] = validator_class
        logger.info(f"注册验证器: {rule_type} -> {validator_class.__name__}")

    @classmethod
    def get_validator(cls, rule_type: str) -> Optional[type[BaseValidator]]:
        """获取验证器类"""
        return cls._validators.get(rule_type)

    @classmethod
    def list_validators(cls) -> list[str]:
        """列出所有已注册的验证器类型"""
        return list(cls._validators.keys())


def register_validator(rule_type: str):
    """验证器注册装饰器"""
    def decorator(cls: type[BaseValidator]):
        ValidatorRegistry.register(rule_type, cls)
        return cls
    return decorator