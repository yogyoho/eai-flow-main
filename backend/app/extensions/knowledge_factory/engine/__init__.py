"""
规则执行引擎

提供统一的合规性检查框架。

主要组件：
- core: 核心类和接口定义
- validators: 内置验证器实现
- service: 规则执行服务
- execution_logger: 执行日志记录
"""

from .core import (
    BaseValidator,
    CheckContext,
    CheckResult,
    CheckResultSummary,
    SeverityLevel,
    ValidationIssue,
    ValidatorRegistry,
    register_validator,
)

from .service import ComplianceEngine, get_engine
from .execution_logger import RuleExecutionLogger

__all__ = [
    "BaseValidator",
    "CheckContext",
    "CheckResult",
    "CheckResultSummary",
    "SeverityLevel",
    "ValidationIssue",
    "ValidatorRegistry",
    "register_validator",
    "ComplianceEngine",
    "get_engine",
    "RuleExecutionLogger",
]