"""Temporal activities for the workflow execution engine."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from ..database import session_scope
from ..engine import commands
from ..models import FlowInstance


@activity.defn
async def probe_activity(message: str) -> str:
    """Small side-effect-free activity used by the worker smoke test."""

    return f"probe:{message}"


@activity.defn
async def get_instance_status_activity(instance_id: int) -> dict[str, Any]:
    async with session_scope() as session:
        instance = await session.get(FlowInstance, instance_id)
        if instance is None or instance.del_flag != "0":
            return {
                "instance_id": instance_id,
                "terminal": True,
                "flow_status": None,
                "missing": True,
            }
        return {
            "instance_id": instance.id,
            "terminal": instance.flow_status in commands.TERMINAL_FLOW_STATUSES,
            "flow_status": instance.flow_status,
            "node_code": instance.node_code,
        }


@activity.defn
async def apply_command_activity(command_id: int) -> dict[str, Any]:
    """Apply one durable command transactionally and return its outcome."""

    async with session_scope() as session:
        command = await commands.apply_command(session, command_id)
        return commands.command_result(command)
