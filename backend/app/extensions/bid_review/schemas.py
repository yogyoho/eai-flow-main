"""bid_review Pydantic 请求/响应模型(照 contract_price/schemas.py 惯例)。

A8(评审修正):输出层 verdict 为 emission-only —— 引擎产出阶段的取值由
issue-schema.json 把关;人工复核回写值(false_positive 等)仅落库,不经本层
schema 校验(故 IssueOut.verdict 保持普通 str,不做枚举收窄)。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


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
    # micro-A 2026-10-29:每任务问题计数,仅 GET /tasks 列表聚合填充(routers.list_tasks);
    # 单任务端点(created/detail/confirm)不查 issues,None=未统计——禁伪零,未统计不得
    # 冒充 0。口径:fatal_unhandled=fatal 且未被人工判误报(verdict≠false_positive,
    # need_human 的 fatal 条目计入,与 TasksView 行级致命数同口径);need_human_count=
    # need_human 旗标计数(工作台待人工格口径),误报回流后自然回落。
    fatal_unhandled: int | None = None
    need_human_count: int | None = None
    # ── B1 扩展(EAI-CUSTOM 2026-10-31,spec §5 B1/裁定12)──────────────
    # biz_no/项目/标段/编号为 task 列直出;done_at=完成时刻(set_status 落);
    # main_unhandled/created_by_name 仅 list_tasks 聚合填充,单任务端点 None=未统计
    # (micro-A 伪零纪律同款)。created_by_name=users join COALESCE(full_name, username)。
    biz_no: str | None = None
    project_name: str | None = None
    lot_name: str | None = None
    tender_no: str | None = None
    updated_at: datetime | None = None
    done_at: datetime | None = None
    main_unhandled: int | None = None
    created_by_name: str | None = None


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
    # EAI-CUSTOM(L2 P2):附件实体键(落库);grouped_into/related_issues 为投影现算
    # (list_task_issues 跨层去重,先例=deviations/checklist 不落库),旧网关缺省。
    entity_keys: list = []
    grouped_into: str | None = None
    related_issues: list = []
    # B2 复核落库投影(EAI-CUSTOM 2026-10-31 Plan9 spec §4.6):该 issue 最新一条
    # 复核反馈动作映射的复核态,unresolved|maintained|false_positive|severity_changed|
    # deferred;无反馈=unresolved。verdict 表达不了 maintained/severity_changed
    # (confirm/severity_change 不改 verdict),故单独投影。
    review_state: str = "unresolved"
    created_at: datetime

    @field_validator("entity_keys", mode="before")
    @classmethod
    def _entity_keys_null_to_empty(cls, v):
        # EAI-CUSTOM(Minor-4,spec 2026-11-04):跑过中间提交 bfde4add6 裸 ALTER 的
        # 环境存量行 entity_keys=NULL(IF NOT EXISTS no-op 补不上 DEFAULT)→
        # model_validate ValidationError → issues 端点 500;读路径 None→[] 兜底
        # (写侧 crud/worker 本就 or [] 兜底,此处补齐读侧)。部署即愈,零运维。
        return [] if v is None else v


class BaselineOut(ORMBase):
    id: str
    task_id: str
    kind: str
    payload: dict
    confirmed: bool = False
    created_at: datetime


class FeedbackIn(BaseModel):
    action: str  # confirm|false_positive|severity_change|need_human(EAI-CUSTOM 2026-10-30 待人工)
    new_severity: str | None = None
    note: str = ""


class AdjudicateIn(BaseModel):
    """冲突裁定请求体(EAI-CUSTOM 2026-10-30 二期 spec §1.3):从多候选中人工裁决
    基准值;path/value 合法性在 routers 校验(422),note 可选复核备注。"""

    path: str
    value: object = None  # JSON 安全类型闸在端点做(BaseModel 不预设 union 丢 list/dict)
    note: str = ""
