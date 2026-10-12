"""Translation extension (EAI-CUSTOM).

EN/FR 文档翻译入库与知识资产化（合资铁矿一期，设计
docs/designs/2026-10-11-jv-mining-translation-kb.md APPROVED v6+R7）。

三闸门最小闭环：入库主干（MinIO 原件 + chunk 血统）/ 翻译 worker（占位符数值
保护 + 三轴机检）/ 评测夹具 / 打标 stub / MCP 工具。本包与 knowledge 扩展的
唯一耦合点是上传链钩子（knowledge 侧按 KB 开关入队，见 eng-review D15/D17）。

结构决议（eng-review 2026-10-11）:
  D15 独立扩展包（contract_price 模式）；D16 worker=2 槽位 + to_thread +
  信号量≤2，gateway 内嵌（D18），boot 时 running→pending 重置。
"""

from app.extensions.translation.models import (  # noqa: F401
    STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    TranslationTask,
    validate_transition,
)
from app.extensions.translation.routers import router  # noqa: F401

__all__ = [
    "STATES",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "TranslationTask",
    "router",
    "validate_transition",
]
