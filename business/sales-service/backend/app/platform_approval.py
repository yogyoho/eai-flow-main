"""Bridge from sales approvals to the standalone workflow platform.

The sales database remains the business fact store. The workflow platform owns
the Temporal orchestration and the authoritative node/task state. This module
projects platform tasks/history back into sales ``approval_steps`` and
``approval_actions`` so the existing marketing approval UI keeps working.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.approval_access import step_actionable
from app.auth import Identity
from app.config import get_settings
from app.domain import utc_now
from app.errors import SalesError, bad_request, forbidden, unavailable
from app.models import ApprovalAction, ApprovalRequest, ApprovalStep

logger = logging.getLogger(__name__)
settings = get_settings()

FLOW_BY_TEMPLATE = {
    "R4_EXCEPTION": "sales_r4_exception",
    "R6_RELATED_PARTY": "sales_r6_related_party",
    "DUPLICATE_MERGE": "sales_duplicate_merge",
}

_STEP_RE = re.compile(r"^step_(\d+)$")


def _step_no(node_code: str | None) -> int | None:
    match = _STEP_RE.match(node_code or "")
    return int(match.group(1)) if match else None


def _headers(identity: Identity | None) -> dict[str, str]:
    roles = []
    if identity is not None:
        for value in (identity.sales_role, identity.role_code):
            if value and value not in roles:
                roles.append(value)
        user_id = identity.user_id
        # HTTP headers must stay ASCII; the platform only uses the name for display.
        name = identity.username or identity.user_id
        dept = identity.dept_id or ""
    else:
        user_id = "sales-service"
        name = "Sales Service"
        roles = ["sales_service"]
        dept = ""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-User-Id": user_id,
        "X-User-Name": name,
        "X-User-Roles": ",".join(roles),
        "X-User-Dept": dept,
        "X-Tenant-Id": "000000",
    }
    if settings.workflow_platform_internal_token:
        headers["X-Workflow-Internal-Token"] = settings.workflow_platform_internal_token
    return headers


def _error(response: httpx.Response) -> SalesError:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    detail = payload.get("detail") if isinstance(payload, dict) else None
    message = str(detail or f"workflow 平台返回 {response.status_code}")
    if response.status_code in (401, 403):
        return forbidden(message, "SALES-403-WORKFLOW_PLATFORM")
    if response.status_code == 404:
        return SalesError(message, "SALES-404-WORKFLOW_PLATFORM", 404)
    if response.status_code >= 500:
        return unavailable("workflow 平台暂不可用", "SALES-503-WORKFLOW_PLATFORM")
    return SalesError(message, "SALES-400-WORKFLOW_PLATFORM", response.status_code)


async def _request(
    method: str,
    path: str,
    *,
    identity: Identity | None = None,
    headers: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not settings.workflow_platform_enabled:
        raise unavailable("workflow 平台未启用", "SALES-503-WORKFLOW_PLATFORM_DISABLED")
    merged = _headers(identity)
    if headers:
        merged.update(headers)
    url = settings.workflow_platform_base_url.rstrip("/") + path
    try:
        async with httpx.AsyncClient(timeout=settings.workflow_platform_timeout_seconds) as client:
            response = await client.request(method, url, headers=merged, json=json)
    except httpx.HTTPError as exc:
        logger.warning("workflow platform request failed: %s %s: %s", method, path, exc)
        raise unavailable("无法连接 workflow 平台", "SALES-503-WORKFLOW_PLATFORM") from exc
    if response.status_code >= 400:
        raise _error(response)
    if response.status_code == 204:
        return {}
    try:
        value = response.json()
    except ValueError as exc:
        raise SalesError("workflow 平台响应格式错误", "SALES-502-WORKFLOW_PLATFORM", 502) from exc
    return value if isinstance(value, dict) else {"value": value}


async def start_instance(
    request: ApprovalRequest,
    identity: Identity,
    *,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    flow_code = FLOW_BY_TEMPLATE.get(request.definition_code)
    if not flow_code:
        raise bad_request(f"未映射 workflow 流程：{request.definition_code}", "SALES-400-WORKFLOW_FLOW")
    payload = await _request(
        "POST",
        "/instances",
        identity=identity,
        headers={"Idempotency-Key": f"sales-start:{request.id}"},
        json={
            "flow_code": flow_code,
            "business_id": str(request.id),
            "handler": identity.user_id,
            "variables": {
                "request_id": str(request.id),
                "request_no": request.request_no,
                "gate_code": request.gate_code,
                "reason": request.reason or "",
                "opportunity_id": str(request.opportunity_id),
                "opportunity_no": (request.payload_json or {}).get("opportunity_no"),
                "opportunity_name": (request.payload_json or {}).get("opportunity_name"),
                "amount": (request.payload_json or {}).get("amount"),
                "requested_by": request.requested_by,
                "steps": steps,
            },
            "ext": "sales-service",
        },
    )
    return payload


async def get_instance(instance_id: int) -> dict[str, Any]:
    return await _request("GET", f"/instances/{instance_id}")


async def execute_task(
    task_id: int,
    *,
    action: str,
    comment: str | None,
    identity: Identity,
    idempotency_key: str,
    delegate_to: str | None = None,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"Idempotency-Key": f"sales:{idempotency_key}"[:200]}
    body = {"message": comment or "", "variables": variables or {}}
    if action == "approve":
        return await _request(
            "POST",
            f"/tasks/{task_id}/approve",
            identity=identity,
            headers=headers,
            json=body,
        )
    if action == "reject":
        return await _request(
            "POST",
            f"/tasks/{task_id}/reject",
            identity=identity,
            headers=headers,
            json={**body, "node_code": "end"},
        )
    if action == "return":
        return await _request(
            "POST",
            f"/tasks/{task_id}/return-to-applicant",
            identity=identity,
            headers=headers,
            json=body,
        )
    if action == "delegate":
        if not delegate_to:
            raise bad_request("转办必须指定接收人", "SALES-400-DELEGATE_TARGET")
        return await _request(
            "POST",
            f"/tasks/{task_id}/transfer",
            identity=identity,
            headers=headers,
            json={"handler": "", "add_handlers": [delegate_to], "message": comment or ""},
        )
    raise bad_request("未知审批动作", "SALES-400-ACTION")


async def cancel_instance(instance_id: int, *, reason: str, identity: Identity) -> dict[str, Any]:
    return await _request(
        "POST",
        f"/instances/{instance_id}/revoke",
        identity=identity,
        json={"message": reason},
    )


def _is_return_history(history: dict[str, Any]) -> bool:
    if str(history.get("skip_type") or "") != "REJECT":
        return False
    targets = {value for value in str(history.get("target_node_code") or "").split(",") if value}
    if "start" in targets:
        return True
    return "发起" in str(history.get("target_node_name") or "")


def _history_action(history: dict[str, Any]) -> str | None:
    skip_type = str(history.get("skip_type") or "")
    if skip_type == "PASS":
        return "approve"
    if skip_type == "REJECT":
        return "return" if _is_return_history(history) else "reject"
    return None


async def _upsert_action(
    db: AsyncSession,
    request: ApprovalRequest,
    step: ApprovalStep,
    history: dict[str, Any],
) -> None:
    action = _history_action(history)
    if action is None:
        return
    key = f"platform-his:{history.get('id')}"
    existing = (await db.execute(select(ApprovalAction).where(ApprovalAction.idempotency_key == key))).scalar_one_or_none()
    if existing is not None:
        return
    # The sales decision endpoint writes the user idempotency-key action before
    # syncing history. Do not duplicate that row as a platform-history action.
    same = (
        await db.execute(
            select(ApprovalAction)
            .where(
                ApprovalAction.request_id == request.id,
                ApprovalAction.step_no == step.step_no,
                ApprovalAction.action == action,
                ApprovalAction.actor_id == str(history.get("approver") or ""),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if same is not None:
        return
    db.add(
        ApprovalAction(
            request_id=request.id,
            step_no=step.step_no,
            action=action,
            actor_id=str(history.get("approver") or "workflow-platform"),
            actor_role=None,
            comment=history.get("message"),
            idempotency_key=key,
        )
    )


def _history_time(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return utc_now()


async def sync_request(db: AsyncSession, request: ApprovalRequest) -> ApprovalRequest:
    """Project the workflow-platform instance onto the sales read model."""

    if request.engine != "workflow_platform" or not request.platform_instance_id:
        return request
    detail = await get_instance(request.platform_instance_id)
    instance = detail.get("instance") or {}
    tasks = detail.get("tasks") or []
    history = detail.get("history") or []

    task_by_step: dict[int, dict[str, Any]] = {}
    for task in tasks:
        step_no = _step_no(task.get("node_code"))
        if step_no:
            task_by_step[step_no] = task
    history_by_step: dict[int, list[dict[str, Any]]] = {}
    for his in history:
        step_no = _step_no(his.get("node_code"))
        if step_no:
            history_by_step.setdefault(step_no, []).append(his)

    terminal_flow = str(instance.get("flow_status") or "")
    terminal = terminal_flow in {"4", "5", "6", "8"}
    active_step = None
    active_step_no = min(task_by_step) if task_by_step and not terminal else None
    latest_history_step = None
    if terminal:
        latest_history = max(
            (his for his in history if _step_no(his.get("node_code"))),
            key=lambda item: int(item.get("id") or 0),
            default=None,
        )
        if latest_history is not None:
            latest_history_step = _step_no(latest_history.get("node_code"))
    last_decision = None
    for step in request.steps:
        history_rows = history_by_step.get(step.step_no, [])
        task = task_by_step.get(step.step_no)
        if task:
            step.platform_task_id = int(task["id"])
        if task and not terminal:
            # A live task is authoritative. A step can have history from an
            # earlier approval cycle (return/resubmit), but it is active now.
            step.status = "active"
            step.decision = None
            step.comment = None
            step.decided_at = None
            active_step = step.step_no
            continue
        if terminal and latest_history_step is not None and step.step_no > latest_history_step:
            # Ignore stale history from a previous return/resubmit cycle.
            step.status = "skipped"
            step.decision = None
            step.comment = None
            step.decided_at = None
            step.platform_task_id = None
            continue
        if active_step_no is not None and step.step_no > active_step_no and not terminal:
            # Steps after the active node belong to the current cycle's future.
            # Clear projections from a previous return/resubmit cycle.
            step.status = "pending"
            step.decision = None
            step.comment = None
            step.decided_at = None
            step.platform_task_id = None
            continue
        if history_rows:
            latest = max(history_rows, key=lambda item: int(item.get("id") or 0))
            skip_type = str(latest.get("skip_type") or "")
            if skip_type in {"PASS", "REJECT"}:
                returned = _is_return_history(latest)
                step.status = "approved" if skip_type == "PASS" else ("returned" if returned else "rejected")
                step.decision = "approve" if skip_type == "PASS" else ("return" if returned else "reject")
                step.comment = latest.get("message")
                step.decided_at = _history_time(latest.get("update_time") or latest.get("create_time"))
                step.platform_task_id = int(latest.get("task_id") or step.platform_task_id or 0) or step.platform_task_id
                last_decision = "RETURN" if returned else skip_type
                await _upsert_action(db, request, step, latest)
        elif terminal and step.status in {"pending", "active"}:
            step.status = "skipped"

    if terminal_flow == "9":
        # Returned requests wait for the applicant, not an approval step.
        request.current_step = 0
    elif active_step is not None:
        request.current_step = active_step
    else:
        pending = [step.step_no for step in request.steps if step.status == "pending"]
        decided = [step.step_no for step in request.steps if step.status in {"approved", "rejected", "returned"}]
        request.current_step = min(pending) if pending else (max(decided) if decided else request.current_step)

    if terminal_flow == "8":
        request.status = "rejected" if last_decision == "REJECT" else "approved"
    elif terminal_flow == "9":
        request.status = "returned"
    elif terminal_flow in {"4", "5", "6"}:
        request.status = "cancelled"
    else:
        request.status = "running"

    if request.status in {"approved", "rejected", "cancelled"}:
        request.completed_at = request.completed_at or utc_now()
    elif request.status in {"running", "returned"}:
        # A returned request is still open: the applicant must resubmit it.
        request.completed_at = None
    if request.status in {"approved", "rejected", "cancelled", "running", "returned"}:
        request.failure_reason = None
    if request.status == "running" and request.started_at is None:
        request.started_at = utc_now()
    await db.flush()
    return request


async def sync_requests(db: AsyncSession, requests: list[ApprovalRequest]) -> None:
    for request in requests:
        if request.engine == "workflow_platform" and request.platform_instance_id:
            try:
                await sync_request(db, request)
            except SalesError:
                logger.warning("workflow platform sync failed for approval %s", request.id, exc_info=True)


def _current_form(instance: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    def_json = instance.get("def_json") or {}
    forms = def_json.get("formSnapshot") or {}
    if not isinstance(forms, dict):
        return None
    form_path = None
    for task in tasks:
        if task.get("form_path"):
            form_path = str(task["form_path"])
            break
    if not form_path:
        form_path = str(def_json.get("formPath") or "")
    if not form_path and forms:
        return next(iter(forms.values()))
    if form_path in forms:
        return forms[form_path]
    code = form_path.partition(":")[0]
    return next(
        (item for path, item in forms.items() if path == form_path or (code and item.get("formCode") == code)),
        None,
    )


def _capabilities(request: ApprovalRequest, identity: Identity) -> dict[str, Any]:
    active = next((step for step in request.steps if step.status == "active"), None)
    can_decide = bool(request.status == "running" and active and step_actionable(identity, active))
    can_cancel = bool(request.status in {"pending_start", "running"} and (identity.is_admin or request.requested_by == identity.user_id))
    can_resubmit = bool(request.status == "returned" and request.engine == "workflow_platform" and request.requested_by == identity.user_id)
    actions = ["approve", "reject", "return"] if can_decide else []
    if can_decide and active and active.mode not in {"parallel_all", "parallel_any"}:
        actions.append("delegate")
    return {
        "can_decide": can_decide,
        "can_cancel": can_cancel,
        "can_resubmit": can_resubmit,
        "actions": actions,
        "active_step": active.step_no if active else None,
    }


async def workflow_view(
    db: AsyncSession,
    request: ApprovalRequest,
    identity: Identity,
) -> dict[str, Any]:
    """BFF payload for the read-only/action workflow panel."""

    if request.engine != "workflow_platform" or not request.platform_instance_id:
        return {
            "available": False,
            "engine": request.engine,
            "platform_instance_id": None,
            "message": "该审批未使用 workflow 平台",
            "tasks": [],
            "history": [],
            "chart": None,
            "form": None,
            "capabilities": _capabilities(request, identity),
        }
    try:
        detail = await get_instance(request.platform_instance_id)
    except SalesError as exc:
        return {
            "available": False,
            "engine": request.engine,
            "platform_instance_id": request.platform_instance_id,
            "message": exc.detail,
            "tasks": [],
            "history": [],
            "chart": None,
            "form": None,
            "capabilities": _capabilities(request, identity),
        }
    instance = detail.get("instance") or {}
    tasks = detail.get("tasks") or []
    history = detail.get("history") or []
    return {
        "available": True,
        "engine": request.engine,
        "platform_instance_id": request.platform_instance_id,
        "workflow_id": f"flow-instance-{request.platform_instance_id}",
        "instance": instance,
        "tasks": tasks,
        "history": history,
        "chart": detail.get("chart") or instance.get("def_json") or {},
        "form": _current_form(instance, tasks),
        "capabilities": _capabilities(request, identity),
    }
