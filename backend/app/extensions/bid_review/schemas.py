"""bid_review Pydantic 请求/响应模型(照 contract_price/schemas.py 惯例)。

A8(评审修正):输出层 verdict 为 emission-only —— 引擎产出阶段的取值由
issue-schema.json 把关;人工复核回写值(false_positive 等)仅落库,不经本层
schema 校验(故 IssueOut.verdict 保持普通 str,不做枚举收窄)。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TaskCreate(BaseModel):
    mode: str = "quick"  # quick|deep


class TaskOut(ORMBase):
    id: str
    owner_id: str
    status: str
    mode: str
    progress: dict
    error: str | None = None
    engine_meta: dict
    prev_task_id: str | None = None
    created_at: datetime


class IssueOut(ORMBase):
    id: str
    task_id: str
    rule_id: str
    layer: str
    severity: str
    verdict: str  # emission-only(A8)
    clause_id: str | None = None
    message: str
    fix: str = ""
    evidence: list
    dedup_key: str
    need_human: bool = False
    confidence: float = 1.0
    created_at: datetime


class BaselineOut(ORMBase):
    id: str
    task_id: str
    kind: str
    payload: dict
    confirmed: bool = False
    created_at: datetime


class FeedbackIn(BaseModel):
    action: str  # confirm|false_positive|severity_change
    new_severity: str | None = None
    note: str = ""
