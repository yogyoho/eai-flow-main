"""Cross-context todo aggregation — no new table, pure query views."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class TodoTask:
    task_id: str
    task_type: str  # writing | review | approval
    title: str
    project_name: str
    task_status: str
    project_id: str
    context: dict = field(default_factory=dict)
    action_label: str = ""
    action_route: str = ""
    is_overdue: bool = False
    due_label: str = ""


@dataclass
class TodoSummary:
    total: int = 0
    writing: int = 0
    review: int = 0
    approval: int = 0
    overdue: int = 0

    @classmethod
    def from_tasks(cls, tasks: list[TodoTask]) -> "TodoSummary":
        return cls(
            total=len(tasks),
            writing=sum(1 for t in tasks if t.task_type == "writing"),
            review=sum(1 for t in tasks if t.task_type == "review"),
            approval=sum(1 for t in tasks if t.task_type == "approval"),
            overdue=sum(1 for t in tasks if t.is_overdue),
        )


def group_by_type(tasks: list[TodoTask]) -> dict[str, list[TodoTask]]:
    grouped: dict[str, list[TodoTask]] = {}
    for task in tasks:
        grouped.setdefault(task.task_type, []).append(task)
    return grouped


async def aggregate_todos(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID | None = None,
) -> list[TodoTask]:
    """Aggregate todos from Writing, Review, and Approval contexts via UNION query."""
    query = text("""
        SELECT
            ch.id::text AS task_id,
            'writing' AS task_type,
            ch.title,
            p.name AS project_name,
            ch.status AS task_status,
            p.id::text AS project_id,
            jsonb_build_object(
                'phase_node', COALESCE(ch.phase_node, ''),
                'chapter_id', ch.id::text,
                'word_count_target', ch.word_count_target,
                'word_count_current', ch.word_count_current
            ) AS context,
            CASE ch.status
                WHEN 'error' THEN '重试生成'
                WHEN 'draft' THEN '继续编辑'
                ELSE '开始撰写'
            END AS action_label,
            '/projects/' || p.id::text || '/edit?chapter=' || ch.id::text AS action_route,
            false AS is_overdue,
            '' AS due_label
        FROM project_chapters ch
        JOIN report_projects p ON p.id = ch.project_id
        WHERE ch.assigned_to = :user_id
          AND ch.status IN ('pending', 'draft', 'error')
          AND (:project_id IS NULL OR p.id = :project_id)

        UNION ALL

        SELECT
            ra.id::text AS task_id,
            'review' AS task_type,
            '审核: ' || ra.phase_node AS title,
            p.name AS project_name,
            ra.status AS task_status,
            p.id::text AS project_id,
            jsonb_build_object(
                'phase_node', ra.phase_node,
                'reviewer_role', ra.reviewer_role
            ) AS context,
            '提交审核意见' AS action_label,
            '/projects/' || p.id::text || '/review?node=' || ra.phase_node AS action_route,
            (ra.deadline_at IS NOT NULL AND ra.deadline_at < now()) AS is_overdue,
            CASE
                WHEN ra.deadline_at IS NULL THEN ''
                WHEN ra.deadline_at < now() THEN '已超时'
                ELSE ''
            END AS due_label
        FROM review_assignments ra
        JOIN report_projects p ON p.id = ra.project_id
        WHERE ra.reviewer_id = :user_id
          AND ra.status = 'pending'
          AND (:project_id IS NULL OR p.id = :project_id)

        UNION ALL

        SELECT
            ra.id::text AS task_id,
            'approval' AS task_type,
            '最终审批: ' || p.name AS title,
            p.name AS project_name,
            'pending' AS task_status,
            p.id::text AS project_id,
            jsonb_build_object('reviewer_role', ra.reviewer_role) AS context,
            '签字审批' AS action_label,
            '/projects/' || p.id::text || '/approval' AS action_route,
            false AS is_overdue,
            '' AS due_label
        FROM review_assignments ra
        JOIN report_projects p ON p.id = ra.project_id
        WHERE ra.reviewer_id = :user_id
          AND ra.status = 'pending'
          AND ra.reviewer_role = 'approver'
          AND (:project_id IS NULL OR p.id = :project_id)

        ORDER BY
            CASE task_status WHEN 'error' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
            is_overdue DESC
    """)

    result = await db.execute(query, {"user_id": user_id, "project_id": project_id})
    rows = result.all()
    return [
        TodoTask(
            task_id=row.task_id,
            task_type=row.task_type,
            title=row.title,
            project_name=row.project_name,
            task_status=row.task_status,
            project_id=row.project_id,
            context=row.context or {},
            action_label=row.action_label,
            action_route=row.action_route,
            is_overdue=row.is_overdue,
            due_label=row.due_label or "",
        )
        for row in rows
    ]
