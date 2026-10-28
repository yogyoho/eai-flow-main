"""Demo directory data used by the handler picker (no user table in this subsystem)."""

from __future__ import annotations

DEMO_USERS: list[dict] = [
    {
        "storageId": "u1001",
        "handlerCode": "u1001",
        "handlerName": "张三",
        "groupName": "研发部",
        "type": "用户",
        "roles": ["manager", "employee"],
        "dept": "d01",
    },
    {
        "storageId": "u1002",
        "handlerCode": "u1002",
        "handlerName": "李四",
        "groupName": "总经办",
        "type": "用户",
        "roles": ["director"],
        "dept": "d02",
    },
    {
        "storageId": "u1003",
        "handlerCode": "u1003",
        "handlerName": "王五",
        "groupName": "财务部",
        "type": "用户",
        "roles": ["finance"],
        "dept": "d03",
    },
    {
        "storageId": "u1004",
        "handlerCode": "u1004",
        "handlerName": "赵六",
        "groupName": "研发部",
        "type": "用户",
        "roles": ["employee"],
        "dept": "d01",
    },
]

DEMO_ROLES = [
    {
        "storageId": "role:manager",
        "handlerCode": "role:manager",
        "handlerName": "部门负责人",
        "groupName": "角色",
        "type": "角色",
    },
    {
        "storageId": "role:director",
        "handlerCode": "role:director",
        "handlerName": "分管领导",
        "groupName": "角色",
        "type": "角色",
    },
    {
        "storageId": "role:finance",
        "handlerCode": "role:finance",
        "handlerName": "财务审核",
        "groupName": "角色",
        "type": "角色",
    },
    {
        "storageId": "role:employee",
        "handlerCode": "role:employee",
        "handlerName": "普通员工",
        "groupName": "角色",
        "type": "角色",
    },
]

DEMO_DEPTS = [
    {"storageId": "dept:d01", "handlerCode": "dept:d01", "handlerName": "研发部", "groupName": "部门", "type": "部门"},
    {"storageId": "dept:d02", "handlerCode": "dept:d02", "handlerName": "总经办", "groupName": "部门", "type": "部门"},
    {"storageId": "dept:d03", "handlerCode": "dept:d03", "handlerName": "财务部", "groupName": "部门", "type": "部门"},
]

ALL_HANDLERS = DEMO_USERS + DEMO_ROLES + DEMO_DEPTS


def find_handler(storage_id: str) -> dict | None:
    return next((item for item in ALL_HANDLERS if item["storageId"] == storage_id), None)
