"""End-to-end sales → workflow platform → Temporal integration smoke test.

Run against a local sales API (AUTH_MODE=local) and the workflow backend::

    python tests/integration_workflow_platform.py

The script creates fresh customer/opportunity data, exercises R4/R6/reject/
permission/idempotency/cancel cases, and inspects workflow commands/runtime/
outbox rows in PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[3]
SALES_BASE = os.getenv("SALES_BASE", "http://127.0.0.1:3104/api/v1")
WORKFLOW_BASE = os.getenv("WORKFLOW_BASE", "http://127.0.0.1:8020/api/workflow")
WORKFLOW_DB_URL = os.getenv(
    "WORKFLOW_DB_URL",
    "postgresql+asyncpg://business:business123@127.0.0.1:5433/workflow",
)


def _env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


_ENV = _env_file()
JWT_SECRET = os.getenv("JWT_SECRET_KEY") or _ENV.get("JWT_SECRET_KEY", "change-me-in-production")
INTERNAL_TOKEN = os.getenv("WORKFLOW_INTERNAL_TOKEN") or _ENV.get("WORKFLOW_INTERNAL_TOKEN", "")


def _token(user: str, role: str, *, admin: bool = False) -> str:
    region = "NORTH" if role in {"sales_rep", "regional_manager"} else "DEFAULT"
    return jwt.encode(
        {
            "sub": user,
            "username": user,
            "full_name": user,
            "role_code": role,
            "sales_role": role,
            "permissions": ["*"] if admin else [],
            "is_admin": admin,
            "region_code": region,
            "dept_id": "dept-north" if role == "regional_manager" else "",
        },
        JWT_SECRET,
        algorithm="HS256",
    )


DEMO_REP = _token("demo-rep", "sales_rep")
MANAGER = _token("demo-manager", "regional_manager")
DIRECTOR = _token("demo-director", "sales_director")
COMPLIANCE = _token("demo-compliance", "compliance_officer")
ADMIN = _token("qa-admin", "sales_admin", admin=True)

client = httpx.Client(timeout=60)
FAILURES: list[str] = []


def call(method: str, path: str, token: str, *, json: dict[str, Any] | None = None, expected: int = 200) -> Any:
    response = client.request(
        method,
        SALES_BASE + path,
        headers={"Authorization": f"Bearer {token}"},
        json=json,
    )
    if response.status_code != expected:
        raise AssertionError(f"{method} {path}: expected {expected}, got {response.status_code}: {response.text}")
    return response.json() if response.content else {}


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS {name}")
    else:
        FAILURES.append(f"{name}: {detail}")
        print(f"FAIL {name}: {detail}")


def create_customer_and_opportunity(*, related_party: bool = False) -> str:
    suffix = uuid.uuid4().hex[:8]
    options = call("GET", "/master-data/options", ADMIN)
    group = next((item for item in options["groups"] if item["name"] == "QA 新客户集团"), None)
    if group is None:
        raise AssertionError("QA 新客户集团 not found")
    customer = call(
        "POST",
        "/master-data/customers",
        ADMIN,
        json={
            "name": f"流程集成客户-{suffix}",
            "group_id": group["id"],
            "region_code": "NORTH",
            "related_party_status": "yes" if related_party else "no",
        },
        expected=201,
    )
    opportunity = call(
        "POST",
        "/opportunities",
        ADMIN,
        json={
            "name": f"流程集成商机-{suffix}",
            "customer_id": customer["id"],
            "product_line": "智能综采",
            "amount": 1200000,
            "region_code": "NORTH",
            "owner_id": "demo-rep",
        },
        expected=201,
    )
    return opportunity["id"]


def submit(opportunity_id: str, gate: str, reason: str) -> str:
    result = call(
        "POST",
        f"/opportunities/{opportunity_id}/approvals",
        DEMO_REP,
        json={"gate_code": gate, "reason": reason},
        expected=201,
    )
    return result["id"]


def detail(request_id: str, token: str = DEMO_REP) -> dict[str, Any]:
    return call("GET", f"/approvals/{request_id}", token)


def decide(request_id: str, token: str, action: str, comment: str, key: str | None = None) -> Any:
    return call(
        "POST",
        f"/approvals/{request_id}/decision",
        token,
        json={
            "action": action,
            "comment": comment,
            "idempotency_key": key or uuid.uuid4().hex,
        },
        expected=202,
    )


def mine(token: str) -> list[dict[str, Any]]:
    return call("GET", "/approvals?mine=1&limit=100", token)["items"]


def workflow_detail(instance_id: int) -> dict[str, Any]:
    headers = {
        "X-Workflow-Internal-Token": INTERNAL_TOKEN,
        "X-User-Id": "qa-admin",
        "X-User-Name": "qa-admin",
        "X-User-Roles": "sales_admin",
        "X-User-Dept": "qa",
        "X-Tenant-Id": "000000",
    }
    response = client.get(f"{WORKFLOW_BASE}/instances/{instance_id}", headers=headers)
    if response.status_code != 200:
        raise AssertionError(f"workflow instance read failed: {response.status_code} {response.text}")
    return response.json()


async def workflow_rows(instance_id: int) -> dict[str, Any]:
    engine = create_async_engine(WORKFLOW_DB_URL)
    try:
        async with engine.connect() as connection:
            commands = (
                await connection.execute(
                    text("select command_type, status from flow_command where instance_id = :id order by id"),
                    {"id": instance_id},
                )
            ).all()
            runtime = (
                await connection.execute(
                    text("select status from flow_instance_runtime where instance_id = :id"),
                    {"id": instance_id},
                )
            ).first()
            outbox = (
                await connection.execute(
                    text("select count(*) from flow_outbox where instance_id = :id"),
                    {"id": instance_id},
                )
            ).scalar_one()
        return {
            "commands": [(row[0], row[1]) for row in commands],
            "runtime": runtime[0] if runtime else None,
            "outbox": int(outbox),
        }
    finally:
        await engine.dispose()


def assert_workflow(instance_id: int, expected_commands: list[str], *, ordered: bool = True) -> None:
    rows = asyncio.run(workflow_rows(instance_id))
    types = [item[0] for item in rows["commands"]]
    actual = types if ordered else sorted(types)
    expected = expected_commands if ordered else sorted(expected_commands)
    check(f"workflow commands {expected_commands}", actual == expected, str(types))
    check(
        "workflow commands applied",
        all(item[1] == "APPLIED" for item in rows["commands"]),
        str(rows["commands"]),
    )
    check("workflow runtime completed", rows["runtime"] == "COMPLETED", str(rows))
    check("workflow outbox exists", rows["outbox"] >= len(expected_commands), str(rows))


def test_r4_happy_path() -> None:
    print("\n== TC-01 R4 两级审批通过 ==")
    opportunity_id = create_customer_and_opportunity()
    request_id = submit(opportunity_id, "R4", "新客户无示范面，申请例外")
    request = detail(request_id)
    check("R4 created running", request["status"] == "running", str(request["status"]))
    check("R4 platform instance bound", bool(request.get("platform_instance_id")), str(request))
    check("R4 step1 active", request["steps"][0]["status"] == "active", str(request["steps"]))
    check("R4 applicant can view", request["requested_by"] == "demo-rep", str(request["requested_by"]))

    manager_items = mine(MANAGER)
    check("manager discovers R4", any(item["id"] == request_id for item in manager_items), "manager list")
    director_before = mine(DIRECTOR)
    check("director not yet tasked", all(item["id"] != request_id for item in director_before), "director list")

    idem = uuid.uuid4().hex
    decide(request_id, MANAGER, "approve", "区域经理同意", idem)
    after_first = detail(request_id)
    check("R4 step1 approved", after_first["steps"][0]["status"] == "approved", str(after_first["steps"]))
    check("R4 step2 active", after_first["steps"][1]["status"] == "active", str(after_first["steps"]))
    check("R4 current step 2", after_first["current_step"] == 2, str(after_first["current_step"]))

    # Same idempotency key must not create a second decision.
    decide(request_id, MANAGER, "approve", "区域经理同意", idem)
    after_dup = detail(request_id)
    check("R4 duplicate decision ignored", len(after_dup["actions"]) == 1, str(after_dup["actions"]))
    check("R4 duplicate current step 2", after_dup["current_step"] == 2, str(after_dup["current_step"]))

    director_items = mine(DIRECTOR)
    check("director discovers R4 step2", any(item["id"] == request_id for item in director_items), "director list")
    decide(request_id, DIRECTOR, "approve", "总监批准")
    done = detail(request_id)
    check("R4 approved", done["status"] == "approved", str(done["status"]))
    check("R4 two actions", len(done["actions"]) == 2, str(done["actions"]))
    check("R4 completed", bool(done.get("completed_at")), str(done.get("completed_at")))

    instance = workflow_detail(done["platform_instance_id"])
    check("workflow instance completed", str(instance["instance"]["flow_status"]) == "8", str(instance["instance"]))
    check("workflow step1+2 history", len(instance["history"]) >= 3, str(instance["history"]))
    assert_workflow(done["platform_instance_id"], ["START", "APPROVE", "APPROVE"])


def test_r6_three_steps() -> None:
    print("\n== TC-02 R6 三级合规审批 ==")
    opportunity_id = create_customer_and_opportunity(related_party=True)
    request_id = submit(opportunity_id, "R6", "关联方交易合规审查")
    decide(request_id, MANAGER, "approve", "区域经理同意")
    decide(request_id, DIRECTOR, "approve", "总监同意")
    before_compliance = detail(request_id)
    check("R6 step3 active", before_compliance["steps"][2]["status"] == "active", str(before_compliance["steps"]))
    compliance_items = mine(COMPLIANCE)
    check("compliance discovers R6", any(item["id"] == request_id for item in compliance_items), "compliance list")
    decide(request_id, COMPLIANCE, "approve", "合规通过")
    done = detail(request_id)
    check("R6 approved", done["status"] == "approved", str(done["status"]))
    assert_workflow(done["platform_instance_id"], ["START", "APPROVE", "APPROVE", "APPROVE"])


def test_reject_and_permission() -> None:
    print("\n== TC-03/TC-04 驳回与越权 ==")
    opportunity_id = create_customer_and_opportunity()
    request_id = submit(opportunity_id, "R4", "需要区域经理审批")
    forbidden = client.post(
        f"{SALES_BASE}/approvals/{request_id}/decision",
        headers={"Authorization": f"Bearer {DIRECTOR}"},
        json={"action": "approve", "comment": "越权", "idempotency_key": uuid.uuid4().hex},
    )
    check("director cannot approve step1", forbidden.status_code == 403, f"{forbidden.status_code} {forbidden.text}")
    still = detail(request_id)
    check("R4 still step1 active", still["steps"][0]["status"] == "active", str(still["steps"]))

    decide(request_id, MANAGER, "reject", "资料不完整")
    rejected = detail(request_id)
    check("R4 rejected", rejected["status"] == "rejected", str(rejected["status"]))
    check("R4 step2 skipped", rejected["steps"][1]["status"] == "skipped", str(rejected["steps"]))
    assert_workflow(rejected["platform_instance_id"], ["START", "REJECT"])


def test_return_and_resubmit() -> None:
    print("\n== TC-09 资料不完整退回申请人并重新提交 ==")
    opportunity_id = create_customer_and_opportunity()
    request_id = submit(opportunity_id, "R4", "资料不完整，待补")
    original = detail(request_id)
    request_no = original["request_no"]
    instance_id = original["platform_instance_id"]

    decide(request_id, MANAGER, "return", "资料不完整，请补充客户资质和例外依据")
    returned = detail(request_id)
    check("R4 returned", returned["status"] == "returned", str(returned["status"]))
    check("R4 return current step 0", returned["current_step"] == 0, str(returned["current_step"]))
    check("R4 return step1 returned", returned["steps"][0]["status"] == "returned", str(returned["steps"]))
    check("R4 return step2 pending", returned["steps"][1]["status"] == "pending", str(returned["steps"]))
    check("R4 return not completed", returned["completed_at"] is None, str(returned["completed_at"]))
    check("R4 return keeps request number", returned["request_no"] == request_no, returned["request_no"])

    instance = workflow_detail(instance_id)
    check("workflow returned status", str(instance["instance"]["flow_status"]) == "9", str(instance["instance"]))
    check("workflow returned to start", instance["instance"]["node_code"] == "start", str(instance["instance"]))
    check(
        "workflow applicant start task",
        any(
            task["node_code"] == "start" and "demo-rep" in (task.get("assignees") or [])
            for task in instance["tasks"]
        ),
        str(instance["tasks"]),
    )
    check(
        "workflow return history targets start",
        any(
            str(row.get("skip_type")) == "REJECT" and row.get("target_node_code") == "start"
            for row in instance["history"]
        ),
        str(instance["history"]),
    )

    admin_resubmit = client.post(
        f"{SALES_BASE}/approvals/{request_id}/resubmit",
        headers={"Authorization": f"Bearer {ADMIN}"},
        json={
            "reason": "管理员尝试代办",
            "evidence": {"customer_license": "LIC-ADMIN"},
            "comment": "admin attempt",
            "idempotency_key": uuid.uuid4().hex,
        },
    )
    check("R4 admin cannot resubmit", admin_resubmit.status_code == 403, admin_resubmit.text)
    still_returned = detail(request_id)
    check("R4 admin resubmit leaves returned", still_returned["status"] == "returned", str(still_returned))

    resubmitted = call(
        "POST",
        f"/approvals/{request_id}/resubmit",
        DEMO_REP,
        json={
            "reason": "已补充客户资质和例外依据",
            "evidence": {"customer_license": "LIC-2026-001", "exception_basis": "新客户首单"},
            "comment": "已按区域经理意见补充",
            "idempotency_key": uuid.uuid4().hex,
        },
        expected=202,
    )
    check("R4 resubmit same request number", resubmitted["request_no"] == request_no, str(resubmitted))
    running = detail(request_id)
    check("R4 resubmitted running", running["status"] == "running", str(running["status"]))
    check("R4 resubmitted current step 1", running["current_step"] == 1, str(running["current_step"]))
    check("R4 resubmitted step1 active", running["steps"][0]["status"] == "active", str(running["steps"]))
    check("R4 resubmitted step2 pending", running["steps"][1]["status"] == "pending", str(running["steps"]))
    check("R4 resubmitted same instance", running["platform_instance_id"] == instance_id, str(running))
    check("R4 resubmit reason updated", running["reason"] == "已补充客户资质和例外依据", str(running["reason"]))
    check(
        "R4 resubmit evidence updated",
        running["evidence"].get("customer_license") == "LIC-2026-001",
        str(running["evidence"]),
    )

    decide(request_id, MANAGER, "approve", "补充后同意")
    decide(request_id, DIRECTOR, "approve", "补充后批准")
    done = detail(request_id)
    check("R4 resubmitted approved", done["status"] == "approved", str(done["status"]))
    check("R4 resubmitted same request number final", done["request_no"] == request_no, done["request_no"])
    assert_workflow(instance_id, ["START", "RETURN", "APPROVE", "APPROVE", "APPROVE"])


def test_cancel() -> None:
    print("\n== TC-08 申请人撤销 ==")
    opportunity_id = create_customer_and_opportunity()
    request_id = submit(opportunity_id, "R4", "测试撤销")
    call("POST", f"/approvals/{request_id}/cancel", DEMO_REP, json={"reason": "测试撤销"}, expected=202)
    cancelled = detail(request_id)
    check("R4 cancelled", cancelled["status"] == "cancelled", str(cancelled["status"]))
    # The submit->cancel race is valid; command ids are clock-derived, so a host
    # clock regression can order REVOKE before START. Compare the multiset here.
    assert_workflow(cancelled["platform_instance_id"], ["START", "REVOKE"], ordered=False)


def main() -> None:
    health = client.get("http://127.0.0.1:3104/health")
    check("sales API health", health.status_code == 200, health.text)
    test_r4_happy_path()
    test_r6_three_steps()
    test_reject_and_permission()
    test_return_and_resubmit()
    test_cancel()
    print("\n== SUMMARY ==")
    if FAILURES:
        for item in FAILURES:
            print("FAILED:", item)
        raise SystemExit(1)
    print("ALL INTEGRATION CHECKS PASSED")


if __name__ == "__main__":
    main()
