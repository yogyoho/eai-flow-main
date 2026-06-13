"""DynamicGraphWorkflow — a Temporal workflow that walks a DAG of nodes.

The graph definition (``graph_json``) follows the React Flow format:

{
  "nodes": [{"id": "...", "type": "subflow|review|condition|merge|ai_generate|task", "data": {...}}],
  "edges": [{"source": "...", "target": "..."}]
}

The workflow resolves a topological ordering at runtime, executes
activities for each node type, and uses Temporal signals / conditions
to coordinate human-in-the-loop steps (phase completion, reviews).

Legacy node types (phase, manual_edit, sub_workflow, notify) are
normalised at runtime via ``_normalise_node_type``.
"""

import logging
from datetime import timedelta

from temporalio import workflow

# ── Legacy node type normalisation ──
_LEGACY_TYPE_MAP: dict[str, str] = {
    "phase": "subflow",
    "manual_edit": "task",
    "sub_workflow": "subflow",
    "notify": "notify",  # deprecated standalone — kept for backward compat
}


def _normalise_node_type(raw_type: str) -> str:
    """Return canonical node type, mapping legacy names to their successors."""
    return _LEGACY_TYPE_MAP.get(raw_type, raw_type)

with workflow.unsafe.imports_passed_through():
    from .activities import (
        advance_phase as _advance_phase,
        create_review_assignments as _create_review_assignments,
        evaluate_condition as _evaluate_condition,
        init_phase as _init_phase,
        init_task as _init_task,
        notify_phase_start as _notify_phase_start,
        notify_review_pending as _notify_review_pending,
        notify_workflow_complete as _notify_workflow_complete,
        parse_sources as _parse_sources,
        start_ai_writing as _start_ai_writing,
        store_sources as _store_sources,
        check_phase_completion as _check_phase_completion,
        check_reviews_complete as _check_reviews_complete,
        gather_phase_context as _gather_phase_context,
        handle_rejection as _handle_rejection,
    )
    from .signals import SIGNAL_AI_COMPLETE, SIGNAL_PHASE_COMPLETE, SIGNAL_REVIEW_ACTION

logger = logging.getLogger(__name__)

# Maximum wall-clock time a phase can wait for external completion.
PHASE_COMPLETION_TIMEOUT = timedelta(days=30)

# Maximum wall-clock time a review gate can wait for all reviewers.
REVIEW_COMPLETION_TIMEOUT = timedelta(days=30)


@workflow.defn
class DynamicGraphWorkflow:
    """Walk a user-defined DAG of workflow nodes.

    Signal handlers
    ~~~~~~~~~~~~~~~
    * ``phase_complete(node_id, result)`` — mark a phase node as done.
    * ``review_action(node_id, approved, comment)`` — respond to a review gate.
    * ``ai_complete(node_id, result)`` — mark an AI generation node as done.

    The workflow is intentionally tolerant: if a node type is unknown it is
    skipped so that new node types can be added to the frontend without
    requiring a workflow redeployment.
    """

    def __init__(self) -> None:
        # Internal state ------------------------------------------------
        self._phase_results: dict[str, dict] = {}
        self._completed: set[str] = set()
        self._pending_reviews: dict[str, list[bool]] = {}  # node_id -> approvals

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    @workflow.signal(name=SIGNAL_PHASE_COMPLETE)
    def phase_complete(self, node_id: str, result: dict | None = None) -> None:
        """External signal: a phase has been completed by the user."""
        logger.info("signal:phase_complete node_id=%s", node_id)
        self._phase_results[node_id] = result or {}
        self._completed.add(node_id)

    @workflow.signal(name=SIGNAL_REVIEW_ACTION)
    def review_action(self, node_id: str, approved: bool, comment: str = "") -> None:
        """External signal: a reviewer has acted on a review gate."""
        logger.info("signal:review_action node_id=%s approved=%s", node_id, approved)
        self._pending_reviews.setdefault(node_id, []).append(approved)

    @workflow.signal(name=SIGNAL_AI_COMPLETE)
    def ai_complete(self, node_id: str, result: dict | None = None) -> None:
        """External signal: an AI generation step finished."""
        logger.info("signal:ai_complete node_id=%s", node_id)
        self._phase_results[node_id] = result or {}
        self._completed.add(node_id)

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    @workflow.run
    async def run(self, params: dict) -> dict:
        """Execute the workflow defined by *params[\"graph_json\"]*.

        Parameters
        ----------
        params:
            ``graph_json`` (dict) — React Flow graph with ``nodes`` and ``edges``.
            ``project_id`` (str) — Owning project.
        """
        graph: dict = params["graph_json"]
        project_id: str = params.get("project_id", "")

        nodes: list[dict] = graph.get("nodes", [])
        edges: list[dict] = graph.get("edges", [])

        if not nodes:
            return {"status": "empty_graph", "completed": [], "results": {}}

        # ---- build adjacency lists ------------------------------------
        # downstream[node_id] = [target_node_ids...]
        downstream: dict[str, list[str]] = {n["id"]: [] for n in nodes}
        # upstream[node_id] = [source_node_ids...]
        upstream: dict[str, list[str]] = {n["id"]: [] for n in nodes}

        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if src and tgt:
                downstream.setdefault(src, []).append(tgt)
                upstream.setdefault(tgt, []).append(src)

        # ---- find start nodes (no incoming edges) ---------------------
        start_nodes = [nid for nid, preds in upstream.items() if not preds]

        # ---- node lookup ----------------------------------------------
        node_map: dict[str, dict] = {n["id"]: n for n in nodes}

        results: dict[str, dict] = {}
        completed: set[str] = set()

        # ---- process nodes -------------------------------------------
        ready: list[str] = list(start_nodes)
        processed: set[str] = set()

        while ready:
            node_id = ready.pop(0)
            if node_id in processed:
                continue
            processed.add(node_id)

            node = node_map.get(node_id)
            if node is None:
                logger.warning("Node %s referenced in edges but missing from nodes list", node_id)
                continue

            node_type = _normalise_node_type(node.get("type", "subflow"))
            node_data = node.get("data", {})

            logger.info("Processing node %s (type=%s)", node_id, node_type)

            try:
                if node_type == "subflow":
                    await self._execute_phase(
                        node_id=node_id,
                        project_id=project_id,
                        node_data=node_data,
                        results=results,
                        completed=completed,
                    )

                elif node_type == "review":
                    rollback_target = await self._execute_review(
                        node_id=node_id,
                        project_id=project_id,
                        node_data=node_data,
                        results=results,
                        completed=completed,
                        edges=edges,
                        processed=processed,
                    )
                    if rollback_target:
                        # Roll back: re-add the target and reset its processed state
                        processed.discard(rollback_target)
                        completed.discard(rollback_target)
                        ready.append(rollback_target)
                        logger.info("Rolling back to node %s", rollback_target)
                        continue

                elif node_type == "condition":
                    branch = await self._execute_condition(
                        node_id=node_id,
                        project_id=project_id,
                        node_data=node_data,
                        results=results,
                        completed=completed,
                    )
                    # For condition nodes we mark completed but still enqueue
                    # downstream nodes — the activity result includes the branch.
                    completed.add(node_id)

                elif node_type == "merge":
                    await self._execute_merge(
                        node_id=node_id,
                        upstream=upstream,
                        completed=completed,
                    )

                elif node_type == "task":
                    await self._execute_task(
                        node_id=node_id,
                        project_id=project_id,
                        node_data=node_data,
                        results=results,
                        completed=completed,
                    )

                elif node_type == "ai_generate":
                    await self._execute_ai_generate(
                        node_id=node_id,
                        project_id=project_id,
                        node_data=node_data,
                        results=results,
                        completed=completed,
                    )

                elif node_type == "notify":
                    # Deprecated standalone notify — fire notification and move on.
                    logger.info("Node %s is deprecated notify type — firing notification and skipping", node_id)
                    completed.add(node_id)

                else:
                    logger.info("Unknown node type '%s' for node %s — skipping", node_type, node_id)
                    completed.add(node_id)

            except Exception:
                logger.exception("Error processing node %s (type=%s)", node_id, node_type)
                # Record the failure but continue processing other branches.
                results[node_id] = {"status": "error"}
                completed.add(node_id)

            # ---- enqueue newly-ready downstream nodes ----------------
            for down_id in downstream.get(node_id, []):
                if down_id in processed:
                    continue
                # A downstream node is ready when ALL its upstream nodes
                # have completed (or been processed).
                preds = upstream.get(down_id, [])
                if all(p in completed for p in preds):
                    ready.append(down_id)

        # ---- final notification --------------------------------------
        try:
            await workflow.execute_activity(
                _notify_workflow_complete,
                project_id,
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception:
            logger.exception("Failed to send workflow completion notification")

        return {"status": "completed", "completed": list(completed), "results": results}

    # ------------------------------------------------------------------
    # Node-type helpers
    # ------------------------------------------------------------------

    async def _execute_phase(
        self,
        node_id: str,
        project_id: str,
        node_data: dict,
        results: dict,
        completed: set[str],
    ) -> None:
        """Run init_phase + advance_phase, then wait for external completion."""
        # Notify phase start
        try:
            await workflow.execute_activity(
                _notify_phase_start,
                node_id,
                project_id,
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception:
            logger.exception("notify_phase_start failed for %s", node_id)

        # Initialise phase
        init_result = await workflow.execute_activity(
            _init_phase,
            node_id,
            project_id,
            node_data,
            start_to_close_timeout=timedelta(seconds=60),
        )
        results[node_id] = init_result

        # Wait for external phase_complete signal.
        already_completed = node_id in self._completed
        if not already_completed:
            await workflow.wait_condition(
                lambda nid=node_id: nid in self._completed,  # type: ignore[misc]
                timeout=PHASE_COMPLETION_TIMEOUT,
            )

        phase_result = self._phase_results.get(node_id, {})
        results[node_id]["result"] = phase_result

        # Check phase completion: verify all scoped chapters are done
        chapter_range = node_data.get("chapter_range")
        try:
            completion = await workflow.execute_activity(
                _check_phase_completion,
                node_id,
                project_id,
                chapter_range,
                start_to_close_timeout=timedelta(seconds=30),
            )
            results[node_id]["completion_check"] = completion
            if not completion.get("ready", False):
                logger.warning(
                    "Phase %s not ready — %d/%d chapters complete, pending: %s",
                    node_id,
                    completion.get("completed", 0),
                    completion.get("total", 0),
                    completion.get("incomplete_chapters", []),
                )
                # Do NOT advance — leave phase active so users can complete their work
                completed.add(node_id)
                return
        except Exception:
            logger.exception("check_phase_completion failed for %s — proceeding anyway", node_id)

        # Advance phase
        try:
            advance_result = await workflow.execute_activity(
                _advance_phase,
                node_id,
                project_id,
                start_to_close_timeout=timedelta(seconds=60),
            )
            results[node_id].update(advance_result)
        except Exception:
            logger.exception("advance_phase failed for %s", node_id)

        completed.add(node_id)

    async def _execute_task(
        self,
        node_id: str,
        project_id: str,
        node_data: dict,
        results: dict,
        completed: set[str],
    ) -> None:
        """Initialize a task node — assign required roles, notify, then wait for completion."""
        # Notify phase start
        try:
            await workflow.execute_activity(
                _notify_phase_start,
                node_id,
                project_id,
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception:
            logger.exception("notify_phase_start failed for task %s", node_id)

        # Initialize task — auto-assign required roles to project members
        task_result = await workflow.execute_activity(
            _init_task,
            node_id,
            project_id,
            node_data,
            start_to_close_timeout=timedelta(seconds=60),
        )
        results[node_id] = task_result

        # Wait for external phase_complete signal
        already_completed = node_id in self._completed
        if not already_completed:
            await workflow.wait_condition(
                lambda nid=node_id: nid in self._completed,
                timeout=PHASE_COMPLETION_TIMEOUT,
            )

        task_completion = self._phase_results.get(node_id, {})
        results[node_id]["result"] = task_completion

        # Advance to next node
        try:
            advance_result = await workflow.execute_activity(
                _advance_phase,
                node_id,
                project_id,
                start_to_close_timeout=timedelta(seconds=60),
            )
            results[node_id].update(advance_result)
        except Exception:
            logger.exception("advance_phase failed for task %s", node_id)

        completed.add(node_id)

    async def _execute_review(
        self,
        node_id: str,
        project_id: str,
        node_data: dict,
        results: dict,
        completed: set[str],
        edges: list[dict],
        processed: set[str],
    ) -> str | None:
        """Create review assignments, wait for review_action signals.

        Returns the rollback target node ID if rejected, None if approved.
        """
        reviewers = node_data.get("reviewers", None)

        try:
            await workflow.execute_activity(
                _notify_review_pending,
                node_id,
                project_id,
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception:
            logger.exception("notify_review_pending failed for %s", node_id)

        assignment_result = await workflow.execute_activity(
            _create_review_assignments,
            node_id,
            project_id,
            reviewers,
            start_to_close_timeout=timedelta(seconds=60),
        )
        results[node_id] = assignment_result

        # Wait until at least one review action has been received.
        has_reviews = bool(self._pending_reviews.get(node_id))
        if not has_reviews:
            await workflow.wait_condition(
                lambda nid=node_id: bool(self._pending_reviews.get(nid)),  # type: ignore[misc]
                timeout=REVIEW_COMPLETION_TIMEOUT,
            )

        approvals = self._pending_reviews.get(node_id, [])
        all_approved = bool(approvals) and all(approvals)
        results[node_id]["all_approved"] = all_approved
        results[node_id]["approval_count"] = len(approvals)
        completed.add(node_id)

        if not all_approved:
            # Find rejection target from DAG edges with label "rejected"
            for edge in edges:
                if edge.get("source") == node_id and edge.get("label") == "rejected":
                    target = edge["target"]
                    logger.info("Review %s rejected — rolling back to %s", node_id, target)
                    return target
            logger.warning("Review %s rejected but no rollback edge found", node_id)

        return None

    async def _execute_condition(
        self,
        node_id: str,
        project_id: str,
        node_data: dict,
        results: dict,
        completed: set[str],
    ) -> str:
        """Evaluate a condition node and return the chosen branch."""
        condition_expr = node_data.get("condition", None)
        cond_result = await workflow.execute_activity(
            _evaluate_condition,
            node_id,
            project_id,
            condition_expr,
            start_to_close_timeout=timedelta(seconds=60),
        )
        results[node_id] = cond_result
        return cond_result.get("branch", "true")

    async def _execute_merge(
        self,
        node_id: str,
        upstream: dict[str, list[str]],
        completed: set[str],
    ) -> None:
        """Wait for all upstream nodes of a merge node to complete."""
        preds = upstream.get(node_id, [])
        if not preds:
            completed.add(node_id)
            return

        all_done = all(p in completed for p in preds)
        if not all_done:
            await workflow.wait_condition(
                lambda: all(p in completed for p in preds),  # type: ignore[misc]
                timeout=PHASE_COMPLETION_TIMEOUT,
            )
        completed.add(node_id)

    async def _execute_ai_generate(
        self,
        node_id: str,
        project_id: str,
        node_data: dict,
        results: dict,
        completed: set[str],
    ) -> None:
        """Execute AI generation: start writing, parse and store sources."""
        chapter_id = node_data.get("chapter_id")

        ai_result = await workflow.execute_activity(
            _start_ai_writing,
            node_id,
            project_id,
            chapter_id,
            start_to_close_timeout=timedelta(minutes=5),
        )
        results[node_id] = ai_result

        # Parse and store source markers if content is available
        content = ai_result.get("content", "")
        if content and chapter_id:
            parsed = await workflow.execute_activity(
                _parse_sources,
                str(chapter_id),
                content,
                start_to_close_timeout=timedelta(seconds=30),
            )
            if parsed.get("source_count", 0) > 0:
                await workflow.execute_activity(
                    _store_sources,
                    str(chapter_id),
                    parsed["sources"],
                    start_to_close_timeout=timedelta(seconds=30),
                )

        completed.add(node_id)

    async def _execute_sub_workflow(
        self,
        node_id: str,
        project_id: str,
        node_data: dict,
        results: dict,
        completed: set[str],
    ) -> None:
        """Start a child workflow and wait for it to complete.

        The node_data must contain a ``graph_json`` dict with its own
        ``nodes`` and ``edges``.  The child workflow is another instance of
        ``DynamicGraphWorkflow``, executing the sub-graph in isolation.
        Parent context (project_id, upstream results) is forwarded so the
        child can access prior phase outputs.
        """
        sub_graph = node_data.get("graph_json") or node_data.get("graphJson")
        if not sub_graph:
            logger.warning(
                "sub_workflow node %s has no graph_json — skipping", node_id,
            )
            completed.add(node_id)
            return

        child_params: dict = {
            "graph_json": sub_graph,
            "project_id": project_id,
        }

        # Forward parent context so the child workflow can reference
        # upstream results (e.g. chapter content from prior phases).
        upstream_context: dict[str, dict] = {}
        for nid, r in results.items():
            if nid in completed and isinstance(r, dict):
                upstream_context[nid] = r
        if upstream_context:
            child_params["parent_context"] = upstream_context

        logger.info(
            "Starting child workflow for node %s (sub_graph has %d nodes)",
            node_id,
            len(sub_graph.get("nodes", [])),
        )

        child_id = f"{project_id}-{node_id}"
        child_handle = await workflow.start_child_workflow(
            "DynamicGraphWorkflow",
            args=[child_params],
            id=child_id,
            task_queue="project-workflow-queue",
        )

        logger.info("Waiting for child workflow %s to complete", child_id)
        try:
            child_result = await child_handle.result()
            results[node_id] = child_result
            logger.info(
                "Child workflow %s completed with status=%s",
                child_id,
                child_result.get("status", "unknown"),
            )
        except Exception:
            logger.exception("Child workflow %s failed", child_id)
            results[node_id] = {
                "status": "error",
                "error": f"Child workflow {child_id} failed",
            }

        completed.add(node_id)
