"""断言执行器数据面(批二十 M1,EAI-CUSTOM 2026-11-13)——AssertionDef/Outcome/
AssertionResult dataclasses + SkillRun ORM 表。表经 routers import 注册共享 Base
metadata(bug-4303 律:勿自建 DeclarativeBase,gateway init_db create_all 承接)。
JSON 报告=导出物非真相源,真相=本表行(spec §8 skill_run 落库裁决)。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.bid_write.contracts import DEGRADE_LEVELS
from app.extensions.bid_write.models import _id, _now
from app.extensions.database import Base

# 等级执行序:D0=0 < D1=1 < D2=2 < D3=3(spec §8 排序键)
LEVEL_RANK: dict[str, int] = {lvl: i for i, lvl in enumerate(DEGRADE_LEVELS)}

# 结果状态词汇(status)
ST_PASS = "PASS"
ST_FAIL = "FAIL"
ST_ERROR = "ERROR"
ST_SKIPPED = "SKIPPED"

# skipped_reason 词汇
SKIP_SHORT_CIRCUIT = "short_circuit"  # 同技能 D0 失败短路
SKIP_NO_SIGNAL = "no_signal"  # yaml expr 特免降级(PS-006 限价未确认 / PS-010 历史价缺失)


@dataclass(frozen=True)
class AssertionDef:
    """注册表单条(p0.yaml assertions[] 行的不可变投影)。expr=判定语义注释,
    校验器实现的验收基准(无 DSL,spec §8)。"""

    id: str
    skill: str
    name: str
    level: str
    blocks_export: bool
    rule_ref: str | None
    expr: str
    human_action: str | None
    delegates_to: str | None = None


@dataclass(frozen=True)
class RegistrySnapshot:
    """load_registry() 产物:断言序 + levels 行为表(blk/render/todo/pre_review_state/
    retry 五维,执行器按表分派不靠约定)+ schema 版本。"""

    assertions: tuple[AssertionDef, ...]
    levels: dict[str, dict]
    schema_version: str

    def by_id(self) -> dict[str, AssertionDef]:
        return {a.id: a for a in self.assertions}


class CtxMissing(Exception):
    """上下文键缺失→runner 转 ERROR E-CTX-MISSING(spec §8:不得静默通过)。"""

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"E-CTX-MISSING: {key}")


@dataclass
class Outcome:
    """校验函数回传;level=None=沿用 static 级(词级升级/特免时置 final 级)。
    deterministic=None=继承 True;相似度/重放注入面断言置 False(spec §8 单独统计)。"""

    status: str  # PASS|FAIL
    level: str | None = None
    message: str = ""
    note: str | None = None
    deterministic: bool | None = None


@dataclass
class AssertionResult:
    """报告单条(final level 已定;blocks_export 由 levels 表 blk 列按 final 级分派)。"""

    assertion_id: str
    skill: str
    name: str
    status: str
    level: str
    blocks_export: bool
    deterministic: bool
    message: str = ""
    human_action: str | None = None
    rule_ref: str | None = None
    note: str | None = None
    skipped_reason: str | None = None
    source_id: str | None = None  # delegates 镜像源(仅 AI-009 类条目)


class SkillRun(Base):
    """断言执行记录(批二十 M1;runner 纯函数零 IO,落库由调用方 crud.record_skill_run)。"""

    __tablename__ = "bid_write_skill_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("bid_write_tasks.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    skills: Mapped[str] = mapped_column(String(40), default="ALL")  # "AI" / "BL,PS,RT,AI"
    schema_version: Mapped[str] = mapped_column(String(12), default="")
    verdict: Mapped[dict] = mapped_column(JSON, default=dict)  # report.to_dict() 全量
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
