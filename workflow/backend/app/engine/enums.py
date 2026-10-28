"""Enum values copied from warm-flow (integer/string keys are wire-compatible)."""

from __future__ import annotations

from enum import IntEnum


class NodeType(IntEnum):
    START = 0
    BETWEEN = 1
    END = 2
    SERIAL = 3
    PARALLEL = 4
    INCLUSIVE = 5


NODE_TYPE_VALUE = {
    0: "start",
    1: "between",
    2: "end",
    3: "serial",
    4: "parallel",
    5: "inclusive",
}
NODE_TYPE_KEY = {value: key for key, value in NODE_TYPE_VALUE.items()}


class FlowStatus:
    TO_BE_SUBMIT = "0"
    APPROVAL = "1"
    PASS = "2"
    AUTO_PASS = "3"
    TERMINATE = "4"
    NULLIFY = "5"
    CANCEL = "6"
    RETRIEVE = "7"
    FINISHED = "8"
    REJECT = "9"
    INVALID = "10"
    TASK_BACK = "11"
    RE_START = "12"
    PENDING = "13"


FLOW_STATUS_LABELS = {
    "0": "待提交",
    "1": "审批中",
    "2": "审批通过",
    "3": "自动完成",
    "4": "已终止",
    "5": "已作废",
    "6": "已撤销",
    "7": "已取回",
    "8": "已完成",
    "9": "已退回",
    "10": "已失效",
    "11": "已拿回",
    "12": "已重启",
    "13": "暂存",
}

FLOW_STATUS_TONE = {
    "0": "slate",
    "1": "amber",
    "2": "emerald",
    "3": "emerald",
    "4": "rose",
    "5": "rose",
    "6": "rose",
    "7": "amber",
    "8": "emerald",
    "9": "rose",
    "10": "slate",
    "11": "amber",
    "12": "blue",
    "13": "slate",
}


class PublishStatus(IntEnum):
    UNPUBLISHED = 0
    PUBLISHED = 1
    EXPIRED = 9


class ActivityStatus(IntEnum):
    SUSPENDED = 0
    ACTIVITY = 1


class SkipType:
    PASS = "PASS"
    REJECT = "REJECT"
    NONE = "NONE"


class CooperateType(IntEnum):
    APPROVAL = 1
    TRANSFER = 2
    DEPUTE = 3
    COUNTERSIGN = 4
    VOTE = 5
    ADD_SIGNATURE = 6
    REDUCTION_SIGNATURE = 7


COOPERATE_LABELS = {
    0: "审批",
    1: "审批",
    2: "转办",
    3: "委派",
    4: "会签",
    5: "票签",
    6: "加签",
    7: "减签",
}


class UserType:
    APPROVAL = "1"
    TRANSFER = "2"
    DEPUTE = "3"


class ChartStatus(IntEnum):
    NOT_DONE = 0
    TO_DO = 1
    DONE = 2


CHART_COLORS = {
    "CLASSICS": ["56,161,105", "245,158,11", "107,114,128"],
}


class ModelValue:
    CLASSICS = "CLASSICS"


def is_start(node_type: int | None) -> bool:
    return node_type == NodeType.START


def is_between(node_type: int | None) -> bool:
    return node_type == NodeType.BETWEEN


def is_end(node_type: int | None) -> bool:
    return node_type == NodeType.END


def is_gateway(node_type: int | None) -> bool:
    return node_type in (NodeType.SERIAL, NodeType.PARALLEL, NodeType.INCLUSIVE)
