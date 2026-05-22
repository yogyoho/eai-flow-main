"""In-memory service for report project management.

Uses a module-level dict so data survives across requests within the same
process.  Will be replaced with SQLAlchemy + PostgreSQL when the schema
is finalized.
"""

import uuid
from datetime import datetime, timezone

from .schemas import (
    MilestoneOut,
    OutlineNode,
    ProjectMemberOut,
    ProjectOut,
)

# ── In-memory store ──

_projects: dict[str, dict] = {}
_outlines: dict[str, dict] = {}  # key = outline_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_outlines(project_id: str, report_type: str) -> list[dict]:
    chapter_map: dict[str, list[str]] = {
        "environmental_impact": [
            "概述", "环境现状调查与评价", "环境影响预测与评价",
            "环境保护措施及其技术经济论证", "环境影响经济损益分析", "环境管理与监测计划",
        ],
        "geological_survey": [
            "概述", "地质概况", "勘查方法及工作量", "勘查成果", "结论与建议",
        ],
        "feasibility_study": [
            "总论", "市场分析与预测", "建设规模与产品方案",
            "技术方案", "投资估算与资金筹措", "财务评价", "结论与建议",
        ],
        "safety_assessment": [
            "概述", "危险有害因素辨识与分析", "评价单元划分与评价方法选择",
            "定性定量评价", "安全对策措施与建议",
        ],
        "energy_assessment": [
            "概述", "项目概况", "能源供应状况分析", "项目建设方案的节能分析", "节能措施评估",
        ],
    }
    chapters = chapter_map.get(report_type, ["概述"])
    result: list[dict] = []
    for i, title in enumerate(chapters):
        oid = str(uuid.uuid4())
        result.append({
            "id": oid,
            "project_id": project_id,
            "parent_id": None,
            "title": f"第{ _num_cn(i + 1) }章 {title}",
            "order": i,
            "status": "not_started",
            "assignee_id": None,
            "assignee_name": None,
            "word_count_target": 3000,
            "word_count_current": 0,
            "description": "",
        })
        _outlines[oid] = result[-1]
    return result


def _num_cn(n: int) -> str:
    chars = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    if n <= 10:
        return chars[n]
    if n < 20:
        return "十" + (chars[n % 10] if n % 10 else "")
    return str(n)


def _default_milestones(project_id: str) -> list[dict]:
    names = ["大纲确认", "初稿完成", "内审完成", "外审完成", "定稿签发"]
    result: list[dict] = []
    for i, name in enumerate(names):
        result.append({
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "name": name,
            "due_date": "",
            "completed_at": None,
            "status": "pending",
        })
    return result


def _build_outline_tree(project_id: str) -> dict | None:
    nodes = [o for o in _outlines.values() if o["project_id"] == project_id]
    if not nodes:
        return None
    nodes.sort(key=lambda x: x["order"])
    root = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "parent_id": None,
        "title": "报告大纲",
        "order": 0,
        "status": "not_started",
        "assignee_id": None,
        "assignee_name": None,
        "word_count_target": 0,
        "word_count_current": 0,
        "description": "",
        "children": nodes,
    }
    return root


def _project_to_out(p: dict) -> ProjectOut:
    pid = p["id"]
    return ProjectOut(
        id=pid,
        name=p["name"],
        report_type=p["report_type"],
        client=p["client"],
        target_standard=p.get("target_standard", ""),
        status=p.get("status", "planning"),
        template_id=p.get("template_id"),
        compliance_rule_set_id=p.get("compliance_rule_set_id"),
        law_ids=p.get("law_ids", []),
        members=[
            ProjectMemberOut(
                user_id=m["user_id"],
                username=m.get("username", m["user_id"]),
                role=m["role"],
                chapter_assignments=m.get("chapter_assignments", []),
            )
            for m in p.get("members", [])
        ],
        outline=_build_outline_tree(pid),
        milestones=[
            MilestoneOut(**ms) for ms in p.get("milestones", [])
        ],
        created_by=p.get("created_by", ""),
        created_at=p.get("created_at", ""),
        updated_at=p.get("updated_at", ""),
    )


# ── Public API ──


async def list_projects(
    *,
    status: str | None = None,
    report_type: str | None = None,
    search: str | None = None,
) -> list[ProjectOut]:
    results = list(_projects.values())
    if status:
        results = [p for p in results if p.get("status") == status]
    if report_type:
        results = [p for p in results if p.get("report_type") == report_type]
    if search:
        s = search.lower()
        results = [
            p for p in results
            if s in p.get("name", "").lower() or s in p.get("client", "").lower()
        ]
    results.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return [_project_to_out(p) for p in results]


async def get_project(project_id: str) -> ProjectOut | None:
    p = _projects.get(project_id)
    if not p:
        return None
    return _project_to_out(p)


async def create_project(
    *,
    name: str,
    report_type: str,
    client: str,
    target_standard: str | None = None,
    template_id: str | None = None,
    compliance_rule_set_id: str | None = None,
    law_ids: list[str] | None = None,
    members: list[dict] | None = None,
    created_by: str = "",
) -> ProjectOut:
    pid = str(uuid.uuid4())
    now = _now_iso()
    outlines = _default_outlines(pid, report_type)
    milestones = _default_milestones(pid)
    p = {
        "id": pid,
        "name": name,
        "report_type": report_type,
        "client": client,
        "target_standard": target_standard or "",
        "status": "planning",
        "template_id": template_id,
        "compliance_rule_set_id": compliance_rule_set_id,
        "law_ids": law_ids or [],
        "members": members or [],
        "milestones": milestones,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    _projects[pid] = p
    return _project_to_out(p)


async def update_project(project_id: str, **kwargs) -> ProjectOut | None:
    p = _projects.get(project_id)
    if not p:
        return None
    for k, v in kwargs.items():
        if v is not None:
            p[k] = v
    p["updated_at"] = _now_iso()
    return _project_to_out(p)


async def delete_project(project_id: str) -> bool:
    if project_id not in _projects:
        return False
    del _projects[project_id]
    to_del = [oid for oid, o in _outlines.items() if o["project_id"] == project_id]
    for oid in to_del:
        del _outlines[oid]
    return True


async def list_outlines(project_id: str) -> list[OutlineNode]:
    nodes = [o for o in _outlines.values() if o["project_id"] == project_id]
    nodes.sort(key=lambda x: x["order"])
    return [OutlineNode(**n) for n in nodes]


async def update_outline(outline_id: str, **kwargs) -> OutlineNode | None:
    o = _outlines.get(outline_id)
    if not o:
        return None
    for k, v in kwargs.items():
        if v is not None:
            o[k] = v
    return OutlineNode(**o)


async def add_member(project_id: str, user_id: str, role: str) -> bool:
    p = _projects.get(project_id)
    if not p:
        return False
    members = p.get("members", [])
    if any(m["user_id"] == user_id and m["role"] == role for m in members):
        return True
    members.append({
        "user_id": user_id,
        "username": user_id,
        "role": role,
        "chapter_assignments": [],
    })
    p["members"] = members
    return True


async def remove_member(project_id: str, user_id: str) -> bool:
    p = _projects.get(project_id)
    if not p:
        return False
    p["members"] = [m for m in p.get("members", []) if m["user_id"] != user_id]
    return True


async def list_milestones(project_id: str) -> list[MilestoneOut]:
    p = _projects.get(project_id)
    if not p:
        return []
    return [MilestoneOut(**ms) for ms in p.get("milestones", [])]
