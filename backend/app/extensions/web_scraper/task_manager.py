"""Async task state management for web scraping."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScrapTask:
    """Scrape task."""

    task_id: str
    url: str
    prompt: str
    provider: str = "browser_use_local"
    schema_name: str | None = None
    proxy_enabled: bool = False
    auth_enabled: bool = False
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    structured_data: dict | None = None
    error: str | None = None
    provider_used: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskManager:
    """Task manager."""

    MAX_TASKS = 100

    def __init__(self):
        self._tasks: dict[str, ScrapTask] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def create(self, **kwargs) -> tuple[str, ScrapTask]:
        """Create a new task."""
        self._cleanup()

        task_id = str(uuid4())[:8]
        task = ScrapTask(task_id=task_id, **kwargs)
        self._tasks[task_id] = task
        self._queues[task_id] = asyncio.Queue(maxsize=100)
        self._locks[task_id] = asyncio.Lock()

        logger.info(f"Created scrape task: {task_id}, URL: {kwargs.get('url', '')}")
        return task_id, task

    async def emit(self, task_id: str, event: dict) -> None:
        """Send event to task queue."""
        if task_id in self._queues:
            await self._queues[task_id].put(event)

    async def stream(self, task_id: str) -> AsyncGenerator[str, None]:
        """Stream task events (SSE format)."""
        if task_id not in self._queues:
            return

        queue = self._queues[task_id]
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=60)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                if event.get("type") in ("result", "error"):
                    break

            except TimeoutError:
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
            except Exception as e:
                logger.error(f"SSE stream error: {e}")
                break

    def get(self, task_id: str) -> ScrapTask | None:
        """Get a task."""
        return self._tasks.get(task_id)

    async def update(self, task_id: str, **kwargs) -> None:
        """Update task status."""
        if task_id not in self._tasks:
            return

        async with self._locks.get(task_id, asyncio.Lock()):
            task = self._tasks[task_id]
            for key, value in kwargs.items():
                setattr(task, key, value)

            if kwargs.get("status") == TaskStatus.RUNNING and not task.started_at:
                task.started_at = datetime.utcnow()
            elif kwargs.get("status") in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.completed_at = datetime.utcnow()

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task."""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        if task.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ):
            return False

        await self.update(task_id, status=TaskStatus.CANCELLED)
        await self.emit(
            task_id,
            {
                "type": "cancelled",
                "level": "warning",
                "message": "Task cancelled by user",
            },
        )
        return True

    def list_tasks(self, limit: int = 20) -> list[dict]:
        """List recent tasks."""
        tasks = sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )[:limit]

        return [
            {
                "task_id": t.task_id,
                "url": t.url,
                "status": t.status.value,
                "provider": t.provider,
                "schema_name": t.schema_name,
                "created_at": t.created_at.isoformat(),
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ]

    def _cleanup(self) -> None:
        """Clean up tasks older than 24 hours."""
        now = datetime.utcnow()
        to_delete = [tid for tid, task in self._tasks.items() if (now - task.created_at).total_seconds() > 86400]
        for tid in to_delete:
            del self._tasks[tid]
            self._queues.pop(tid, None)
            self._locks.pop(tid, None)

        while len(self._tasks) > self.MAX_TASKS:
            oldest = min(self._tasks.items(), key=lambda x: x[1].created_at)
            tid = oldest[0]
            del self._tasks[tid]
            self._queues.pop(tid, None)
            self._locks.pop(tid, None)


task_manager = TaskManager()
