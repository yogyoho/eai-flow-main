"""bid_write API schemas(批十九 T5)——与 bid_review/schemas.py 同构(from_
orm 全开,progress/engine_meta 直透;矩阵行 PATCH 单模型)。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WriteTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    biz_no: str | None = None
    status: str
    progress: dict = Field(default_factory=dict)
    error: str | None = None
    project_name: str | None = None
    lot_name: str | None = None
    tender_no: str | None = None
    created_at: datetime | None = None
    engine_meta: dict = Field(default_factory=dict)


class MatrixRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clause_id: str
    kind: str
    source_path: str
    requirement: str
    star: bool
    strategy: str
    target_section: str
    evidence_refs: list = Field(default_factory=list)
    status: str
    conf: float | None = None
    verified: bool = False
    note: str = ""


class MatrixRowPatch(BaseModel):
    """行级人工卡点(F1):strategy 推进 + 确认/解阻;star 行 negative 须 note
    (routers 校验 422)。status 合法值=draft|confirmed|blocked(解阻=确认)。"""

    strategy: str | None = None
    status: str | None = None
    target_section: str | None = None
    note: str | None = None
    evidence_refs: list[Any] | None = None
