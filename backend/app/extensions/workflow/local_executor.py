"""LocalWorkflowRunner — in-process DAG executor (no Temporal required).

Used as a fallback when Temporal server is unavailable. Tracks workflow
state via the project's ``current_phase_node`` field in the database.
Each node type is handled synchronously within the process.
"""

import logging
import uuid

logger = logging.getLogger(__name__)

#: How long to wait for human action (phase complete, review) before timing out.
HUMAN_WAIT_TIMEOUT_SECONDS = 30 * 24 * 3600  # 30 days

# ── Legacy node type normalisation ──
# Old graphs may contain deprecated node types.  Map them to their
# modern equivalents so the executor treats them identically.
_LEGACY_TYPE_MAP: dict[str, str] = {
    "phase": "subflow",
    "manual_edit": "task",
    "sub_workflow": "subflow",
}


def _normalise_node_type(raw_type: str) -> str:
    """Return canonical node type, mapping legacy names to their successors."""
    return _LEGACY_TYPE_MAP.get(raw_type, raw_type)


class LocalWorkflowRunner:
    """Walk a DAG workflow graph in-process.

    Usage::

        runner = LocalWorkflowRunner()
        result = await runner.run(graph_json, project_id)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, graph: dict, project_id: str) -> dict:
        """Execute *graph* for *project_id*. Returns completion dict."""
        version = graph.get("version", 1)
        if version == 2:
            return await self._run_v2(graph, project_id)
        return await self._run_v1(graph, project_id)

    async def advance_to_next(self, project_id: str) -> dict | None:
        """After a human action (phase_complete / review_action), advance the
        workflow to the next node. Returns the next node dict or None if done."""
        from app.extensions.database import get_db_context
        from app.extensions.models import ReportProject
        from app.extensions.workflow.models import WorkflowDefinition

        async with get_db_context() as db:
            project = await db.get(ReportProject, uuid.UUID(project_id))
            if not project or not project.workflow_id:
                return None

            wf = await db.get(WorkflowDefinition, project.workflow_id)
            if not wf:
                return None

            graph = wf.graph_json
            version = graph.get("version", 1)

        if version == 2:
            return await self._advance_v2(graph, project_id)
        return await self._advance_v1(graph, project_id)

    # ------------------------------------------------------------------
    # V2 two-layer execution
    # ------------------------------------------------------------------

    async def _run_v2(self, graph: dict, project_id: str) -> dict:
        """V2: walk phase graph, execute each phase's tasks."""
        phase_graph = graph.get("mainGraph", {})
        task_graphs = graph.get("taskGraphs", {})
        phase_nodes = phase_graph.get("nodes", [])
        phase_edges = phase_graph.get("edges", [])

        if not phase_nodes:
            return {"status": "empty_graph", "completed": [], "results": {}}

        # Build adjacency
        downstream: dict[str, list[str]] = {n["id"]: [] for n in phase_nodes}
        upstream: dict[str, list[str]] = {n["id"]: [] for n in phase_nodes}
        for e in phase_edges:
            s, t = e.get("source", ""), e.get("target", "")
            if s and t:
                downstream.setdefault(s, []).append(t)
                upstream.setdefault(t, []).append(s)

        start_phases = [nid for nid, preds in upstream.items() if not preds]
        phase_map = {n["id"]: n for n in phase_nodes}

        results: dict[str, dict] = {}
        completed: set[str] = set()

        ready = list(start_phases)
        processed: set[str] = set()

        while ready:
            pid = ready.pop(0)
            if pid in processed:
                continue
            processed.add(pid)

            node = phase_map.get(pid)
            if not node:
                continue

            node_type = _normalise_node_type(node.get("type", "subflow"))
            node_data = node.get("data", {})

            try:
                if node_type == "condition":
                    _branch = await self._evaluate_condition(pid, project_id, node_data)
                    condition_result = await self._execute_activity(
                        "evaluate_condition", pid, project_id,
                        condition_expr=node_data.get("expression"),
                    )
                    results[pid] = condition_result
                elif node_type == "task":
                    await self._execute_activity("init_task", pid, project_id, config=node_data)
                    await self._execute_activity("notify_phase_start", pid, project_id)
                    results[pid] = {"status": "awaiting_human_action"}
                elif node_type == "review":
                    reviewers = [
                        b["value"] for b in node_data.get("reviewers", [])
                        if b.get("type") == "user"
                    ]
                    await self._execute_activity("create_review_assignments", pid, project_id, reviewers=reviewers or None)
                    await self._execute_activity("notify_review_pending", pid, project_id)
                    results[pid] = {"status": "awaiting_review"}
                elif node_type == "ai_generate":
                    await self._execute_activity(
                        "start_ai_writing", pid, project_id,
                        chapter_id=node_data.get("chapterId"),
                    )
                    results[pid] = {"status": "ai_completed"}
                elif node_type == "subflow":
                    # Subflow (formerly phase): init and execute inner tasks
                    await self._execute_activity("init_phase", pid, project_id, config=node_data)
                    await self._execute_activity("notify_phase_start", pid, project_id)

                    # Execute tasks inside this subflow
                    tg = task_graphs.get(pid)
                    if tg:
                        task_result = await self._execute_task_graph(
                            pid, project_id, tg, results, completed,
                        )
                        results[pid] = task_result

                    await self._execute_activity("advance_phase", pid, project_id)
                elif node_type == "merge":
                    # Merge: just mark completed
                    pass
                elif node_type == "notify":
                    # Standalone notify is deprecated — notifications are now
                    # an attribute on other nodes.  Fire for backward compat.
                    await self._execute_activity("notify_phase_start", pid, project_id)
                    results[pid] = {"status": "completed"}
                else:
                    logger.info("Unknown node type '%s' for node %s — skipping", node_type, pid)
                    results[pid] = {"status": "skipped", "reason": f"unknown type: {node_type}"}
            except Exception:
                logger.exception("Error in phase %s", pid)
                results[pid] = {"status": "error"}

            completed.add(pid)

            for down_id in downstream.get(pid, []):
                if down_id in processed:
                    continue
                if all(p in completed for p in upstream.get(down_id, [])):
                    ready.append(down_id)

        from .temporal.activities import notify_workflow_complete as _notify_wf_complete
        await _notify_wf_complete(project_id)
        return {"status": "completed", "completed": list(completed), "results": results}

    async def _execute_task_graph(
        self, phase_id: str, project_id: str, tg: dict,
        results: dict, completed: set[str],
    ) -> dict:
        """Execute the task DAG inside a phase."""
        task_nodes = tg.get("nodes", [])
        task_edges = tg.get("edges", [])
        if not task_nodes:
            return {"status": "no_tasks"}

        downstream: dict[str, list[str]] = {n["id"]: [] for n in task_nodes}
        upstream: dict[str, list[str]] = {n["id"]: [] for n in task_nodes}
        rejected_target: dict[str, str] = {}
        for e in task_edges:
            s, t = e.get("source", ""), e.get("target", "")
            if s and t:
                downstream.setdefault(s, []).append(t)
                upstream.setdefault(t, []).append(s)
            if e.get("label") == "rejected":
                rejected_target[e["source"]] = e["target"]

        first_tasks = [nid for nid, preds in upstream.items() if not preds]
        task_map = {n["id"]: n for n in task_nodes}
        task_results: dict[str, dict] = {}
        task_completed: set[str] = set()

        ready = list(first_tasks)
        processed: set[str] = set()
        max_iter = 20
        iteration = 0

        while ready and iteration < max_iter:
            iteration += 1
            tid = ready.pop(0)
            if tid in processed:
                continue

            task = task_map.get(tid)
            if not task:
                continue

            task_type = _normalise_node_type(task.get("type", ""))
            task_data = task.get("data", {})
            rollback_to = None

            try:
                if task_type == "ai_generate":
                    await self._execute_activity(
                        "start_ai_writing", tid, project_id,
                        chapter_id=task_data.get("chapterId"),
                    )
                    task_completed.add(tid)
                elif task_type == "review":
                    reviewers = [
                        b["value"] for b in task_data.get("reviewers", [])
                        if b.get("type") == "user"
                    ]
                    await self._execute_activity(
                        "create_review_assignments", tid, project_id, reviewers=reviewers or None,
                    )
                    await self._execute_activity("notify_review_pending", tid, project_id)
                    # Wait for human action — in local mode, this returns after signal
                    # (the caller should re-invoke run/advance after the human acts)
                    task_completed.add(tid)
                    task_results[tid] = {"status": "awaiting_review"}
                elif task_type == "manual_edit":
                    # Manual edit — waits for human action
                    task_completed.add(tid)
                    task_results[tid] = {"status": "awaiting_edit"}
                elif task_type == "notify":
                    await self._execute_activity("notify_phase_start", tid, project_id)
                    task_completed.add(tid)
                elif task_type == "merge":
                    preds = upstream.get(tid, [])
                    if all(p in task_completed for p in preds):
                        task_completed.add(tid)
                else:
                    task_completed.add(tid)

                processed.add(tid)

                if rollback_to:
                    processed.discard(rollback_to)
                    task_completed.discard(rollback_to)
                    ready = [rollback_to]
                    continue

            except Exception:
                logger.exception("Error in task %s of phase %s", tid, phase_id)
                task_results[tid] = {"status": "error"}
                task_completed.add(tid)
                processed.add(tid)

            for down_id in downstream.get(tid, []):
                if down_id in processed:
                    continue
                if all(p in task_completed for p in upstream.get(down_id, [])):
                    ready.append(down_id)

        if iteration >= max_iter:
            logger.warning("Phase %s hit max iterations", phase_id)

        return {"status": "ok", "task_results": task_results}

    # ------------------------------------------------------------------
    # V1 flat execution (simplified)
    # ------------------------------------------------------------------

    async def _run_v1(self, graph: dict, project_id: str) -> dict:
        """V1 flat DAG — simple topological walk."""
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])

        if not nodes:
            return {"status": "empty_graph", "completed": [], "results": {}}

        downstream: dict[str, list[str]] = {n["id"]: [] for n in nodes}
        upstream: dict[str, list[str]] = {n["id"]: [] for n in nodes}
        for e in edges:
            s, t = e.get("source", ""), e.get("target", "")
            if s and t:
                downstream.setdefault(s, []).append(t)
                upstream.setdefault(t, []).append(s)

        start_nodes = [nid for nid, preds in upstream.items() if not preds]
        node_map = {n["id"]: n for n in nodes}
        results: dict[str, dict] = {}
        completed: set[str] = set()
        ready = list(start_nodes)
        processed: set[str] = set()

        while ready:
            nid = ready.pop(0)
            if nid in processed:
                continue
            processed.add(nid)
            node = node_map.get(nid)
            if not node:
                continue

            ntype = _normalise_node_type(node.get("type", "subflow"))
            ndata = node.get("data", {})
            try:
                if ntype == "subflow":
                    await self._execute_activity("init_phase", nid, project_id, config=ndata)
                    await self._execute_activity("notify_phase_start", nid, project_id)
                elif ntype == "task":
                    await self._execute_activity("init_task", nid, project_id, config=ndata)
                    await self._execute_activity("notify_phase_start", nid, project_id)
                elif ntype == "ai_generate":
                    await self._execute_activity("start_ai_writing", nid, project_id)
                elif ntype == "review":
                    await self._execute_activity("create_review_assignments", nid, project_id)
                    await self._execute_activity("notify_review_pending", nid, project_id)
                else:
                    logger.info("V1: Unknown node type '%s' for node %s — skipping", ntype, nid)
                results[nid] = {"status": "completed"}
            except Exception:
                logger.exception("Error in node %s", nid)
                results[nid] = {"status": "error"}
            completed.add(nid)

            for down_id in downstream.get(nid, []):
                if down_id in processed:
                    continue
                if all(p in completed for p in upstream.get(down_id, [])):
                    ready.append(down_id)

        from .temporal.activities import notify_workflow_complete as _notify_wf_complete
        await _notify_wf_complete(project_id)
        return {"status": "completed", "completed": list(completed), "results": results}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _execute_activity(self, name: str, node_id: str, project_id: str, **kwargs) -> dict:
        """Execute a workflow activity by dispatching to the activity module."""
        from .temporal.activities import (
            advance_phase,
            create_review_assignments,
            evaluate_condition,
            init_phase,
            init_task,
            notify_phase_start,
            notify_review_pending,
            start_ai_writing,
        )

        mapping = {
            "advance_phase": advance_phase,
            "create_review_assignments": create_review_assignments,
            "evaluate_condition": evaluate_condition,
            "init_phase": init_phase,
            "init_task": init_task,
            "notify_phase_start": notify_phase_start,
            "notify_review_pending": notify_review_pending,
            "start_ai_writing": start_ai_writing,
        }

        fn = mapping.get(name)
        if not fn:
            logger.warning("Unknown activity: %s", name)
            return {"status": "unknown_activity", "name": name}

        return await fn(node_id, project_id, **kwargs)

    async def _evaluate_condition(self, node_id: str, project_id: str, node_data: dict) -> str:
        """Evaluate a condition node locally."""
        from .temporal.activities import evaluate_condition

        result = await evaluate_condition(
            node_id, project_id,
            condition_expr=node_data.get("expression"),
        )
        return result.get("branch", "true")

    async def _advance_v2(self, graph: dict, project_id: str) -> dict | None:
        """Advance v2 workflow by one step after human action."""
        # Find current phase and advance
        from app.extensions.database import get_db_context
        from app.extensions.models import ReportProject

        async with get_db_context() as db:
            project = await db.get(ReportProject, uuid.UUID(project_id))
            if not project:
                return None
            current = project.current_phase_node
            if not current:
                # Workflow not yet started — run from beginning
                return await self._run_v2(graph, project_id)

        # Re-run from current context — picks up where it left off
        return await self._run_v2(graph, project_id)

    async def _advance_v1(self, graph: dict, project_id: str) -> dict | None:
        """Advance v1 workflow by one step."""
        from app.extensions.database import get_db_context
        from app.extensions.models import ReportProject

        async with get_db_context() as db:
            project = await db.get(ReportProject, uuid.UUID(project_id))
            if not project or not project.current_phase_node:
                return await self._run_v1(graph, project_id)

        return await self._run_v1(graph, project_id)


# Singleton
_local_runner: LocalWorkflowRunner | None = None


def get_local_runner() -> LocalWorkflowRunner:
    """Get or create the singleton local workflow runner."""
    global _local_runner
    if _local_runner is None:
        _local_runner = LocalWorkflowRunner()
    return _local_runner
