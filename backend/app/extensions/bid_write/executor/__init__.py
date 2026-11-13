"""断言执行器(批二十 M1,EAI-CUSTOM 2026-11-13)——bid_write P0 四技能生成产物
校验核。公开面:load_registry(注册表加载)/run_assertions(执行,Task 2)/
RunReport 序列化(Task 4)。执行语义与门禁裁决=spec
docs/superpowers/specs/2026-11-13-bid-write-p0-skills-spec.md §8;无通用 DSL,
每条断言一 Python 校验函数按 assertion_id 注册(validators/)。"""

from app.extensions.bid_write.executor.loader import RegistryError, load_registry
from app.extensions.bid_write.executor.models import (
    AssertionDef,
    AssertionResult,
    CtxMissing,
    Outcome,
    RegistrySnapshot,
    SkillRun,
)

__all__ = [
    "AssertionDef",
    "AssertionResult",
    "CtxMissing",
    "Outcome",
    "RegistryError",
    "RegistrySnapshot",
    "SkillRun",
    "load_registry",
]
