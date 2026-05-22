"""In-memory service for approval workflow management."""

import uuid
from datetime import datetime, timezone

# ── In-memory store ──

_workflows: dict[str, dict] = {}
_records: dict[str, dict] = {}
_submissions: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init_default_workflows() -> None:
    if _workflows:
        return

    report_types = {
        "environmental_impact": "环境影响评价审批流程",
        "geological_survey": "地质勘查审批流程",
        "feasibility_study": "可行性研究审批流程",
        "safety_assessment": "安全评价审批流程",
        "energy_assessment": "节能评估审批流程",
    }
    for rt, name in report_types.items():
        wid = str(uuid.uuid4())
        steps = [
            {
                "id": str(uuid.uuid4()),
                "workflow_id": wid,
                "order": i,
                "name": n,
                "required_role": r,
                "can_reject": True,
                "parallel": False,
            }
            for i, (n, r) in enumerate(
                [
                    ("内部审核", "reviewer"),
                    ("技术审查", "approver"),
                    ("批准签发", "issuer"),
                ]
            )
        ]
        _workflows[rt] = {
            "id": wid,
            "name": name,
            "report_type": rt,
            "steps": steps,
            "is_default": True,
        }


async def get_workflow(report_type: str) -> dict | None:
    _init_default_workflows()
    return _workflows.get(report_type)


async def submit_for_approval(
    *,
    project_id: str,
    chapter_ids: list[str] | None = None,
    submitted_by: str = "",
) -> dict:
    sid = str(uuid.uuid4())
    sub = {
        "id": sid,
        "project_id": project_id,
        "chapter_ids": chapter_ids or [],
        "submitted_by": submitted_by,
        "submitted_at": _now_iso(),
        "status": "pending",
    }
    _submissions[sid] = sub
    return sub


async def create_action(
    *,
    project_id: str,
    step_id: str,
    chapter_id: str | None = None,
    action: str = "approve",
    comment: str | None = None,
    reviewer_id: str = "",
    reviewer_name: str = "",
) -> dict:
    rid = str(uuid.uuid4())
    rec = {
        "id": rid,
        "project_id": project_id,
        "step_id": step_id,
        "chapter_id": chapter_id,
        "reviewer_id": reviewer_id,
        "reviewer_name": reviewer_name,
        "action": action,
        "comment": comment or "",
        "acted_at": _now_iso(),
    }
    _records[rid] = rec
    return rec


async def list_records(project_id: str) -> list[dict]:
    return [
        r for r in _records.values() if r["project_id"] == project_id
    ]
