# EAI-CUSTOM: 投标方案审查扩展包(方案 A 双件套:engine + workbench)。
"""bid_review 子系统(投标方案审查)——engine+workbench,方案 A 双件套。

表创建机制:包导入即把五张模型注册进共享 ``app.extensions.database`` Base,
gateway 启动序 init_db(create_all)自动建表(仓库惯例,同 eia_samples /
spare_parts 的包 __init__ 自注册机制;无需 alembic)。
"""

from app.extensions.bid_review.models import (  # noqa: F401
    BaselinePackage,
    ReviewFeedback,
    ReviewIssue,
    ReviewTask,
    RulePackMeta,
)

__all__ = [
    "BaselinePackage",
    "ReviewFeedback",
    "ReviewIssue",
    "ReviewTask",
    "RulePackMeta",
]
