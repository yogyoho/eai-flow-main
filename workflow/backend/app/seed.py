"""Idempotent demo data: forms + three runnable process definitions."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import FlowDefinition, FlowForm
from .utils import next_id, to_json, utcnow

DEMO_FORMS = [
    {
        "form_code": "leave_form",
        "form_name": "请假申请单",
        "form_type": 0,
        "schema": {
            "fields": [
                {"key": "days", "label": "请假天数", "type": "number", "required": True},
                {"key": "reason", "label": "请假事由", "type": "textarea", "required": True},
                {"key": "startDate", "label": "开始日期", "type": "date", "required": True},
            ]
        },
    },
    {
        "form_code": "expense_form",
        "form_name": "费用报销单",
        "form_type": 0,
        "schema": {
            "fields": [
                {"key": "amount", "label": "报销金额", "type": "number", "required": True},
                {
                    "key": "category",
                    "label": "费用类别",
                    "type": "select",
                    "options": ["差旅", "招待", "办公"],
                    "required": True,
                },
                {"key": "remark", "label": "备注", "type": "textarea", "required": False},
            ]
        },
    },
]


LEAVE_FLOW = {
    "flowCode": "leave",
    "flowName": "员工请假流程",
    "modelValue": "CLASSICS",
    "category": "人事",
    "formCustom": "Y",
    "formPath": "leave_form:1",
    "nodeList": [
        {
            "nodeType": 0,
            "nodeCode": "start",
            "nodeName": "发起申请",
            "coordinate": "160,200|160,245",
            "nodeRatio": "0",
            "skipList": [
                {
                    "nowNodeCode": "start",
                    "nextNodeCode": "dept",
                    "skipName": "提交",
                    "skipType": "PASS",
                    "coordinate": "260,220;380,220|320,200",
                }
            ],
        },
        {
            "nodeType": 1,
            "nodeCode": "dept",
            "nodeName": "部门负责人审批",
            "permissionFlag": "role:manager@@u1001",
            "coordinate": "480,200|480,245",
            "nodeRatio": "0",
            "formCustom": "Y",
            "formPath": "leave_form:1",
            "skipList": [
                {
                    "nowNodeCode": "dept",
                    "nextNodeCode": "director",
                    "skipName": "通过",
                    "skipType": "PASS",
                    "coordinate": "580,220;700,220|640,200",
                }
            ],
        },
        {
            "nodeType": 1,
            "nodeCode": "director",
            "nodeName": "分管领导审批",
            "permissionFlag": "u1002",
            "coordinate": "800,200|800,245",
            "nodeRatio": "0",
            "skipList": [
                {
                    "nowNodeCode": "director",
                    "nextNodeCode": "end",
                    "skipName": "通过",
                    "skipType": "PASS",
                    "coordinate": "900,220;1020,220|960,200",
                },
                {
                    "nowNodeCode": "director",
                    "nextNodeCode": "dept",
                    "skipName": "退回",
                    "skipType": "REJECT",
                    "coordinate": "800,160;480,160|640,140",
                },
            ],
        },
        {
            "nodeType": 2,
            "nodeCode": "end",
            "nodeName": "流程结束",
            "coordinate": "1120,200|1120,245",
            "nodeRatio": "0",
            "skipList": [],
        },
    ],
}


EXPENSE_FLOW = {
    "flowCode": "expense",
    "flowName": "费用报销流程",
    "modelValue": "CLASSICS",
    "category": "财务",
    "formCustom": "Y",
    "formPath": "expense_form:1",
    "nodeList": [
        {
            "nodeType": 0,
            "nodeCode": "start",
            "nodeName": "发起报销",
            "coordinate": "160,220|160,265",
            "skipList": [
                {
                    "nowNodeCode": "start",
                    "nextNodeCode": "amount_gateway",
                    "skipName": "提交",
                    "skipType": "PASS",
                    "coordinate": "260,240;360,240|310,220",
                }
            ],
        },
        {
            "nodeType": 3,
            "nodeCode": "amount_gateway",
            "nodeName": "金额判断",
            "coordinate": "460,220|460,265",
            "skipList": [
                {
                    "nowNodeCode": "amount_gateway",
                    "nextNodeCode": "finance",
                    "skipName": "≤ 5000",
                    "skipType": "PASS",
                    "skipCondition": "le@@amount|5000",
                    "coordinate": "560,200;680,160|590,175",
                },
                {
                    "nowNodeCode": "amount_gateway",
                    "nextNodeCode": "director_expense",
                    "skipName": "> 5000",
                    "skipType": "PASS",
                    "skipCondition": "gt@@amount|5000",
                    "coordinate": "560,240;680,280|590,290",
                },
            ],
        },
        {
            "nodeType": 1,
            "nodeCode": "finance",
            "nodeName": "财务审核",
            "permissionFlag": "u1003",
            "coordinate": "780,150|780,195",
            "formCustom": "Y",
            "formPath": "expense_form:1",
            "skipList": [
                {
                    "nowNodeCode": "finance",
                    "nextNodeCode": "end",
                    "skipName": "通过",
                    "skipType": "PASS",
                    "coordinate": "880,170;1000,220|930,185",
                },
                {
                    "nowNodeCode": "finance",
                    "nextNodeCode": "director_expense",
                    "skipName": "退回",
                    "skipType": "REJECT",
                    "coordinate": "780,130;780,290|730,210",
                },
            ],
        },
        {
            "nodeType": 1,
            "nodeCode": "director_expense",
            "nodeName": "总监审批",
            "permissionFlag": "u1002",
            "coordinate": "780,290|780,335",
            "formCustom": "Y",
            "formPath": "expense_form:1",
            "skipList": [
                {
                    "nowNodeCode": "director_expense",
                    "nextNodeCode": "finance",
                    "skipName": "通过",
                    "skipType": "PASS",
                    "coordinate": "800,310;800,195|840,250",
                }
            ],
        },
        {
            "nodeType": 2,
            "nodeCode": "end",
            "nodeName": "流程结束",
            "coordinate": "1100,220|1100,265",
        },
    ],
}


PURCHASE_FLOW = {
    "flowCode": "purchase",
    "flowName": "采购申请流程（会签）",
    "modelValue": "CLASSICS",
    "category": "采购",
    "nodeList": [
        {
            "nodeType": 0,
            "nodeCode": "start",
            "nodeName": "提交采购申请",
            "coordinate": "160,200|160,245",
            "skipList": [
                {
                    "nowNodeCode": "start",
                    "nextNodeCode": "review",
                    "skipName": "提交",
                    "skipType": "PASS",
                    "coordinate": "260,220;380,220|320,200",
                }
            ],
        },
        {
            "nodeType": 1,
            "nodeCode": "review",
            "nodeName": "采购委员会会签",
            "permissionFlag": "u1001@@u1002@@u1003",
            "nodeRatio": "100",
            "coordinate": "480,200|480,245",
            "skipList": [
                {
                    "nowNodeCode": "review",
                    "nextNodeCode": "finance",
                    "skipName": "会签通过",
                    "skipType": "PASS",
                    "coordinate": "580,220;700,220|640,200",
                }
            ],
        },
        {
            "nodeType": 1,
            "nodeCode": "finance",
            "nodeName": "采购财务复核",
            "permissionFlag": "u1003",
            "coordinate": "800,200|800,245",
            "skipList": [
                {
                    "nowNodeCode": "finance",
                    "nextNodeCode": "end",
                    "skipName": "通过",
                    "skipType": "PASS",
                    "coordinate": "900,220;1020,220|960,200",
                },
                {
                    "nowNodeCode": "finance",
                    "nextNodeCode": "review",
                    "skipName": "退回会签",
                    "skipType": "REJECT",
                    "coordinate": "880,160;480,160|680,140",
                },
            ],
        },
        {
            "nodeType": 2,
            "nodeCode": "end",
            "nodeName": "流程结束",
            "coordinate": "1120,200|1120,245",
        },
    ],
}


async def seed_demo_data(session: AsyncSession) -> None:
    existing = (
        await session.execute(select(func.count()).select_from(FlowDefinition).where(FlowDefinition.del_flag == "0"))
    ).scalar_one()
    if existing:
        return

    now = utcnow()
    for form in DEMO_FORMS:
        session.add(
            FlowForm(
                id=next_id(),
                form_code=form["form_code"],
                form_name=form["form_name"],
                version="1",
                is_publish=1,
                form_type=form["form_type"],
                form_content=to_json(form["schema"]),
                form_path=f"{form['form_code']}:1",
                create_time=now,
                create_by="system",
                update_time=now,
                update_by="system",
                tenant_id="000000",
            )
        )
    await session.commit()

    from .engine.definition import publish_definition, save_def_json

    for flow in (LEAVE_FLOW, EXPENSE_FLOW, PURCHASE_FLOW):
        saved = await save_def_json(session, flow, actor="system")
        await publish_definition(session, int(saved["id"]), actor="system")
