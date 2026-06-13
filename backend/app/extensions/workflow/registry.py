"""Extensible workflow node registry.

Modules register node executors via the @register_node decorator.
Temporal workflows dispatch to executors by node type at runtime.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ── Types ──


@dataclass
class SignalDef:
    """A signal that a node can receive."""
    name: str
    description: str = ""
    payload_schema: dict | None = None


@dataclass
class WorkflowContext:
    """Context passed to node executors during execution."""
    project_id: str
    workflow_id: str | None = None
    config: dict = field(default_factory=dict)


@dataclass
class NodeResult:
    """Result returned by a node executor's on_enter."""
    status: str  # "completed" | "waiting" | "failed"
    output: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class SignalResult:
    """Result returned by a node executor's on_signal."""
    status: str  # "continue" | "rollback" | "retry"
    output: dict = field(default_factory=dict)


# ── Protocol ──


class IWorkflowNodeExecutor(Protocol):
    """Contract for any business module to hook into the workflow engine."""

    node_type: str
    display_name: str
    display_category: str
    config_schema: dict
    signals: list[SignalDef]

    async def on_enter(self, node: dict, ctx: WorkflowContext) -> NodeResult:
        """Called when the workflow activates this node."""
        ...

    async def on_signal(self, node: dict, signal_name: str, payload: dict, ctx: WorkflowContext) -> SignalResult:
        """Called when a signal arrives for this node."""
        ...

    def validate(self, config: dict) -> list[str]:
        """Validate node config; return list of error messages (empty = valid)."""
        ...


# ── Registry ──


class _NodeRegistry:
    """Global registry of workflow node executors."""

    def __init__(self):
        self._executors: dict[str, IWorkflowNodeExecutor] = {}

    def register(self, executor: IWorkflowNodeExecutor):
        if executor.node_type in self._executors:
            logger.warning(
                "Node type %r re-registered; overwriting previous executor",
                executor.node_type,
            )
        self._executors[executor.node_type] = executor
        logger.info("Registered node type: %s (%s)", executor.node_type, executor.display_name)

    def get(self, node_type: str) -> IWorkflowNodeExecutor | None:
        return self._executors.get(node_type)

    def list_all(self) -> list[IWorkflowNodeExecutor]:
        return list(self._executors.values())

    def list_by_category(self, category: str) -> list[IWorkflowNodeExecutor]:
        return [e for e in self._executors.values() if e.display_category == category]

    @property
    def categories(self) -> list[str]:
        return sorted({e.display_category for e in self._executors.values()})


# Singleton
node_registry = _NodeRegistry()


# ── Decorator ──


def register_node(cls):
    """Class decorator: register a node executor in the global registry."""
    instance = cls()
    node_registry.register(instance)
    return cls
