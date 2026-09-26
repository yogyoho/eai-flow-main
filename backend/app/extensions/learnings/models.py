"""learnings 扩展数据模型 — agent_learnings + learning_sweep_receipts.

EAI-CUSTOM: 自进化循环 P1(设计 docs/designs/self-improving-loop-port.md, D12/D13 定稿)。
- (user_id, pattern_key) 唯一 = mint-or-fold 锚(每用户每 key 一行, recurrence 折叠计数)
- 幂等唯一归 learning_sweep_receipts(扫过的 run 永不重扫); evidence 无 hash 字段
  (相同文本 hash 相同会与 recurrence 计数互斥, 见 eng-review OV3)
- gateway 不得 import 本模块(表由 MCP 子进程 create_all, 零触碰约束)
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


def _new_id() -> str:
    return str(uuid4())


class AgentLearning(Base):
    """一条结构化教训(每用户每 pattern_key 一行)."""

    __tablename__ = "agent_learnings"
    __table_args__ = (UniqueConstraint("user_id", "pattern_key", name="uq_agent_learning_user_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # error|correction|knowledge_gap|best_practice|feature_request
    area: Mapped[str] = mapped_column(String(30))
    symptom: Mapped[str] = mapped_column(String(60))
    pattern_key: Mapped[str] = mapped_column(String(100))  # area.symptom, 服务端 canonicalize
    summary: Mapped[str] = mapped_column(String(200))
    details: Mapped[str] = mapped_column(Text, default="")
    suggested_action: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|resolved|dismissed|promoted_to_skill
    recurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    distinct_thread_count: Mapped[int] = mapped_column(Integer, default=1)
    # 实现细节: 逗号连接的 thread 短 id 集合(截断 ~1000 字符), 用于折叠时重算 distinct_thread_count
    source_thread_ids: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(10), default="agent")  # agent|sweep
    source_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promoted_skill: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pattern_key": self.pattern_key,
            "kind": self.kind,
            "summary": self.summary,
            "status": self.status,
            "recurrence_count": self.recurrence_count,
            "distinct_thread_count": self.distinct_thread_count,
            "first_seen_at": str(self.first_seen_at),
            "last_seen_at": str(self.last_seen_at),
            "suggested_action": self.suggested_action,
            "promoted_skill": self.promoted_skill,
        }


class LearningSweepReceipt(Base):
    """sweep 幂等凭据(D12: 唯一归它——扫过的 run 永不重扫)."""

    __tablename__ = "learning_sweep_receipts"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    swept_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    captures: Mapped[int] = mapped_column(Integer, default=0)
