"""Built-in system node types: start, end."""
from __future__ import annotations

from app.extensions.workflow.registry import (
    IWorkflowNodeExecutor,
    NodeResult,
    SignalDef,
    SignalResult,
    WorkflowContext,
    register_node,
)


@register_node
class StartNodeExecutor:
    """Explicit workflow start gate — validates entry conditions."""

    node_type = "system:start"
    display_name = "项目启动"
    display_category = "系统"
    config_schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "default": "项目启动"},
            "entry_conditions": {
                "type": "object",
                "properties": {
                    "template_bound": {"type": "boolean", "default": True},
                    "team_size_min": {"type": "integer", "default": 2},
                    "required_roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["owner"],
                    },
                },
            },
            "trigger": {
                "type": "string",
                "enum": ["manual", "auto_on_create", "scheduled"],
                "default": "manual",
            },
        },
    }
    signals: list[SignalDef] = []

    async def on_enter(self, node: dict, ctx: WorkflowContext) -> NodeResult:
        """Validate entry conditions and pass."""
        conditions = (node.get("data") or {}).get("entry_conditions", {})
        errors: list[str] = []

        if conditions.get("template_bound"):
            from app.extensions.database import get_db_context
            from app.extensions.models import ReportProject
            import uuid

            async with get_db_context() as db:
                project = await db.get(ReportProject, uuid.UUID(ctx.project_id))
                if project and not project.template_id:
                    errors.append("项目未绑定报告模板")
                if project and conditions.get("team_size_min"):
                    from app.extensions.models import ProjectMember
                    from sqlalchemy import func, select as sa_select

                    count_result = await db.execute(
                        sa_select(func.count()).where(
                            ProjectMember.project_id == uuid.UUID(ctx.project_id)
                        )
                    )
                    member_count = count_result.scalar()
                    if member_count < conditions["team_size_min"]:
                        errors.append(
                            f"团队成员不足（需要 {conditions['team_size_min']} 人，当前 {member_count} 人）"
                        )

        if errors:
            return NodeResult(status="failed", error="; ".join(errors))

        return NodeResult(status="completed", output={"conditions_met": True})

    async def on_signal(self, node: dict, signal_name: str, payload: dict, ctx: WorkflowContext) -> SignalResult:
        return SignalResult(status="continue")

    def validate(self, config: dict) -> list[str]:
        errors: list[str] = []
        conditions = config.get("entry_conditions", {})
        if "team_size_min" in conditions and not isinstance(conditions["team_size_min"], int):
            errors.append("entry_conditions.team_size_min must be an integer")
        return errors


@register_node
class EndNodeExecutor:
    """Explicit workflow end gate — executes completion actions."""

    node_type = "system:end"
    display_name = "项目完成"
    display_category = "系统"
    config_schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "default": "项目完成"},
            "completion_actions": {
                "type": "object",
                "properties": {
                    "set_project_status": {"type": "string", "default": "completed"},
                    "merge_documents": {"type": "boolean", "default": True},
                    "notify_roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["owner"],
                    },
                    "archive_to_docspace": {"type": "boolean", "default": True},
                },
            },
        },
    }
    signals: list[SignalDef] = []

    async def on_enter(self, node: dict, ctx: WorkflowContext) -> NodeResult:
        """Execute completion actions and mark project completed."""
        data = node.get("data") or {}
        actions = data.get("completion_actions", {})

        from app.extensions.database import get_db_context
        from app.extensions.models import ReportProject
        import uuid

        new_status = actions.get("set_project_status", "completed")

        async with get_db_context() as db:
            project = await db.get(ReportProject, uuid.UUID(ctx.project_id))
            if project:
                project.status = new_status
                await db.commit()

        return NodeResult(
            status="completed",
            output={"project_status": new_status},
        )

    async def on_signal(self, node: dict, signal_name: str, payload: dict, ctx: WorkflowContext) -> SignalResult:
        return SignalResult(status="continue")

    def validate(self, config: dict) -> list[str]:
        return []
