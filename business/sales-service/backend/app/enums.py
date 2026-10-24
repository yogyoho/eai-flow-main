"""Domain constants shared by API, rules and Temporal activities."""

from __future__ import annotations

STAGES = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]

STAGE_LABELS = {
    "S1": "线索",
    "S2": "初步接触",
    "S3": "需求确认",
    "S4": "技术方案 / 示范",
    "S5": "投标立项",
    "S6": "报价审批",
    "S7": "投标",
    "S8": "中标 / 失标",
    "S9": "合同生效",
}

STAGE_BASE_PROBABILITY = {
    "S1": 10,
    "S2": 20,
    "S3": 35,
    "S4": 50,
    "S5": 60,
    "S6": 70,
    "S7": 80,
    "S8": 90,
    "S9": 100,
}

STAGE_SLA_DAYS = {
    "S1": None,
    "S2": 30,
    "S3": 30,
    "S4": 35,
    "S5": 15,
    "S6": 10,
    "S7": 15,
    "S8": None,
    "S9": None,
}

SEVERITY_SLA_HOURS = {
    "blocker": 4,
    "high": 24,
    "medium": 72,
    "low": 168,
}

TODO_TYPES = {"rule_event", "approval", "arbitration", "data_fix"}
SEVERITIES = {"blocker", "high", "medium", "low"}
TODO_STATUSES = {"open", "in_progress", "resolved", "cancelled"}
APPROVAL_STATUSES = {"pending_start", "running", "approved", "rejected", "returned", "cancelled", "expired", "failed"}
APPROVAL_ACTIONS = {"approve", "reject", "return", "cancel", "delegate"}
GATE_STATUSES = {"pass", "warn", "block", "not_configured"}
SALES_ROLES = {"sales_admin", "sales_director", "regional_manager", "sales_rep", "data_steward", "compliance_officer", "bid_manager"}

# Permission defaults are used only when EAI has not yet assigned the sales
# module to an existing role (pilot bootstrap). Authorization still comes from
# EAI once the permissions are mapped.
SALES_PERMISSIONS = [
    "sales.workbench.read",
    "sales.opportunity.read",
    "sales.opportunity.create",
    "sales.opportunity.update",
    "sales.opportunity.transition",
    "sales.opportunity.rollback",
    "sales.opportunity.probability_override",
    "sales.opportunity.duplicate_resolve",
    "sales.opportunity.export",
    "sales.todo.read",
    "sales.todo.assign",
    "sales.todo.resolve",
    "sales.todo.batch",
    "sales.todo.export",
    "sales.masterdata.read",
    "sales.masterdata.import",
    "sales.rule.read",
    "sales.rule.manage",
    "sales.approval.read",
    "sales.approval.request",
    "sales.approval.decide",
    "sales.approval.cancel",
    "sales.approval.manage",
    "sales.audit.read",
]

ROLE_PERMISSIONS = {
    "sales_admin": set(SALES_PERMISSIONS),
    "sales_director": {
        "sales.workbench.read",
        "sales.opportunity.read",
        "sales.opportunity.create",
        "sales.opportunity.update",
        "sales.opportunity.transition",
        "sales.opportunity.rollback",
        "sales.opportunity.probability_override",
        "sales.opportunity.duplicate_resolve",
        "sales.opportunity.export",
        "sales.todo.read",
        "sales.todo.assign",
        "sales.todo.resolve",
        "sales.todo.batch",
        "sales.todo.export",
        "sales.masterdata.read",
        "sales.masterdata.import",
        "sales.rule.read",
        "sales.rule.manage",
        "sales.approval.read",
        "sales.approval.request",
        "sales.approval.decide",
        "sales.approval.cancel",
        "sales.approval.manage",
        "sales.audit.read",
    },
    "regional_manager": {
        "sales.workbench.read",
        "sales.opportunity.read",
        "sales.opportunity.create",
        "sales.opportunity.update",
        "sales.opportunity.transition",
        "sales.opportunity.rollback",
        "sales.opportunity.probability_override",
        "sales.opportunity.duplicate_resolve",
        "sales.opportunity.export",
        "sales.todo.read",
        "sales.todo.assign",
        "sales.todo.resolve",
        "sales.todo.batch",
        "sales.todo.export",
        "sales.masterdata.read",
        "sales.approval.read",
        "sales.approval.request",
        "sales.approval.decide",
        "sales.approval.cancel",
        "sales.rule.read",
    },
    "sales_rep": {
        "sales.workbench.read",
        "sales.opportunity.read",
        "sales.opportunity.create",
        "sales.opportunity.update",
        "sales.opportunity.transition",
        "sales.opportunity.rollback",
        "sales.opportunity.probability_override",
        "sales.opportunity.export",
        "sales.todo.read",
        "sales.todo.resolve",
        "sales.todo.export",
        "sales.masterdata.read",
        "sales.approval.read",
        "sales.approval.request",
        "sales.approval.cancel",
        "sales.rule.read",
    },
    "data_steward": {
        "sales.workbench.read",
        "sales.opportunity.read",
        "sales.todo.read",
        "sales.todo.resolve",
        "sales.masterdata.read",
        "sales.masterdata.import",
        "sales.rule.read",
    },
    "compliance_officer": {
        "sales.workbench.read",
        "sales.opportunity.read",
        "sales.opportunity.export",
        "sales.todo.read",
        "sales.todo.resolve",
        "sales.masterdata.read",
        "sales.approval.read",
        "sales.approval.decide",
        "sales.rule.read",
        "sales.audit.read",
    },
    "bid_manager": {
        "sales.workbench.read",
        "sales.opportunity.read",
        "sales.opportunity.export",
        "sales.todo.read",
        "sales.todo.resolve",
        "sales.masterdata.read",
        "sales.approval.read",
        "sales.rule.read",
    },
}

ROLE_SCOPE = {
    "sales_admin": "all",
    "sales_director": "all",
    "compliance_officer": "all",
    "regional_manager": "region",
    "data_steward": "region",
    "sales_rep": "self",
    "bid_manager": "self",
}

ROLE_LABELS = {
    "sales_admin": "销售系统管理员",
    "sales_director": "营销中心主任",
    "regional_manager": "大区经理",
    "sales_rep": "客户经理",
    "data_steward": "数据 Steward",
    "compliance_officer": "合规审批人",
    "bid_manager": "投标经理",
}

# Stage fields are validated for the *target* stage. They intentionally only
# cover data that QW2 can actually hold locally.
STAGE_REQUIRED_FIELDS = {
    "S1": ("customer_id", "product_line", "amount", "expected_close_date", "owner_id"),
    "S2": ("customer_id", "product_line", "amount", "expected_close_date", "owner_id"),
    "S3": ("customer_id", "product_line", "amount", "expected_close_date", "owner_id"),
    "S4": ("customer_id", "product_line", "amount", "expected_close_date", "owner_id"),
    "S5": ("customer_id", "product_line", "amount", "expected_close_date", "owner_id"),
    "S6": ("customer_id", "product_line", "amount", "expected_close_date", "owner_id"),
    "S7": ("customer_id", "product_line", "amount", "expected_close_date", "owner_id"),
    "S8": ("customer_id", "product_line", "amount", "expected_close_date", "owner_id"),
    "S9": ("contract_no", "contract_amount", "contract_effective_date"),
}

STAGE_ADVANCE_LABELS = {
    "S1": "来源可追溯",
    "S2": "联系人已关联",
    "S3": "决策链至少 1 人",
    "S4": "方案已启动",
    "S5": "R4 示范面",
    "S6": "R2 报价冲突 / R6 关联方",
    "S7": "资格关闭、双审签",
    "S8": "结果 / 失标原因",
    "S9": "合同字段完整",
}
