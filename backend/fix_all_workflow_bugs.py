"""Apply all workflow fixes at once."""
import re

with open("app/extensions/workflow/temporal/workflows.py", "r") as f:
    content = f.read()

# ---- FIX 1: Auto-detect V2 + V1 fallback in run() ----
old_run = '''        graph: dict = params["graph_json"]
        project_id: str = params.get("project_id", "")

        version = graph.get("version", 1)
        if version == 2:
            return await self._run_v2(graph, project_id)'''

new_run = '''        graph: dict = params["graph_json"]
        project_id: str = params.get("project_id", "")

        logger.warning(
            "WF-START project=%s nodes=%d keys=%s",
            project_id,
            len(graph.get("nodes", graph.get("mainGraph", {}).get("nodes", []))),
            list(graph.keys()),
        )

        version = graph.get("version", 1)
        # Auto-detect V2 format when version is missing but the graph
        # has a nested mainGraph / main_graph key (frontend may save
        # V2-format graphs without an explicit version field).
        if version < 2 and ("mainGraph" in graph or "main_graph" in graph):
            version = 2
        if version == 2:
            # Some V2-format graphs have task-level nodes directly in the
            # phase graph without proper "phase" containers and empty
            # subGraphs. Fall back to V1 processing for these.
            phase_graph = graph.get("mainGraph", graph.get("phaseGraph", {}))
            phase_nodes = phase_graph.get("nodes", [])
            phase_types = {n.get("type", "") for n in phase_nodes}
            sub_graphs = graph.get("subGraphs", graph.get("taskGraphs", {}))
            sub_has_entries = bool(sub_graphs) and any(
                sg.get("nodes") for sg in sub_graphs.values()
                if isinstance(sg, dict)
            )

            if "phase" not in phase_types and not sub_has_entries:
                # Flatten to V1: promote mainGraph nodes & edges to top level
                flat_graph = {
                    "nodes": phase_nodes,
                    "edges": phase_graph.get("edges", []),
                }
                logger.info(
                    "V2 graph has no phase containers and empty subGraphs — "
                    "falling back to V1 processing with %d nodes",
                    len(phase_nodes),
                )
                return await self._run_v1(flat_graph, project_id)

            return await self._run_v2(graph, project_id)'''

content = content.replace(old_run, new_run)

# ---- FIX 2: Add debug logging to _execute_phase ----
old_phase_enter = '''    async def _execute_phase(
        self,
        node_id: str,
        project_id: str,
        node_data: dict,
        results: dict,
        completed: set[str],
    ) -> None:
        """Run init_phase + advance_phase, then wait for external completion."""
        # Notify phase start'''
new_phase_enter = '''    async def _execute_phase(
        self,
        node_id: str,
        project_id: str,
        node_data: dict,
        results: dict,
        completed: set[str],
    ) -> None:
        """Run init_phase + advance_phase, then wait for external completion."""
        logger.warning(
            "_execute_phase ENTER node_id=%s project_id=%s node_data_keys=%s",
            node_id, project_id, list(node_data.keys()) if node_data else [],
        )
        # Notify phase start'''

content = content.replace(old_phase_enter, new_phase_enter)

# Add DONE log after notify_phase_start success
old_notify_done = '''            await workflow.execute_activity(
                _notify_phase_start,
                node_id,
                project_id,
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception:
            logger.exception("notify_phase_start failed for %s", node_id)'''
new_notify_done = '''            await workflow.execute_activity(
                _notify_phase_start,
                args=[node_id, project_id],
                start_to_close_timeout=timedelta(seconds=30),
            )
            logger.warning("_execute_phase notify_phase_start DONE for %s", node_id)
        except Exception:
            logger.exception("notify_phase_start failed for %s", node_id)'''
content = content.replace(old_notify_done, new_notify_done)

# ---- FIX 3: Fix all remaining execute_activity calls to use args=[] ----
# List of patterns: (old_call_signature, new_args_list)
# Each entry: (unique substring to find, (activity_name, [arg_names...]))
fixes = [
    # V1 final notification
    (
        '            await workflow.execute_activity(\n'
        '                _notify_workflow_complete,\n'
        '                project_id,',
        '            await workflow.execute_activity(\n'
        '                _notify_workflow_complete,\n'
        '                args=[project_id],'
    ),
    # V2 final notification
    (
        '            await workflow.execute_activity(\n'
        '                _notify_workflow_complete, project_id,',
        '            await workflow.execute_activity(\n'
        '                _notify_workflow_complete, args=[project_id],'
    ),
    # notify_review_pending in v2
    (
        '            await workflow.execute_activity(\n'
        '                _notify_review_pending, node_id, project_id,',
        '            await workflow.execute_activity(\n'
        '                _notify_review_pending, args=[node_id, project_id],'
    ),
    # create_review_assignments in v2
    (
        '            await workflow.execute_activity(\n'
        '                _create_review_assignments, node_id, project_id, reviewer_ids,',
        '            await workflow.execute_activity(\n'
        '                _create_review_assignments, args=[node_id, project_id, reviewer_ids],'
    ),
    # notify_phase_start in v2
    (
        '            await workflow.execute_activity(\n'
        '                _notify_phase_start, phase_id, project_id,',
        '            await workflow.execute_activity(\n'
        '                _notify_phase_start, args=[phase_id, project_id],'
    ),
    # init_phase in v2
    (
        '        init_result = await workflow.execute_activity(\n'
        '            _init_phase, phase_id, project_id, node_data,',
        '        init_result = await workflow.execute_activity(\n'
        '            _init_phase, args=[phase_id, project_id, node_data],'
    ),
    # advance_phase in v2 tasks
    (
        '            advance_result = await workflow.execute_activity(\n'
        '                _advance_phase, phase_id, project_id,',
        '            advance_result = await workflow.execute_activity(\n'
        '                _advance_phase, args=[phase_id, project_id],'
    ),
    # notify_phase_start in _execute_phase (V1)
    # Already fixed above

    # init_phase in _execute_phase (V1)
    (
        '        init_result = await workflow.execute_activity(\n'
        '            _init_phase,\n'
        '            node_id,\n'
        '            project_id,\n'
        '            node_data,',
        '        init_result = await workflow.execute_activity(\n'
        '            _init_phase,\n'
        '            args=[node_id, project_id, node_data],'
    ),
    # check_phase_completion in _execute_phase
    (
        '            completion = await workflow.execute_activity(\n'
        '                _check_phase_completion,\n'
        '                node_id,\n'
        '                project_id,\n'
        '                chapter_range,',
        '            completion = await workflow.execute_activity(\n'
        '                _check_phase_completion,\n'
        '                args=[node_id, project_id, chapter_range],'
    ),
    # advance_phase in _execute_phase
    (
        '            advance_result = await workflow.execute_activity(\n'
        '                _advance_phase,\n'
        '                node_id,\n'
        '                project_id,',
        '            advance_result = await workflow.execute_activity(\n'
        '                _advance_phase,\n'
        '                args=[node_id, project_id],'
    ),
    # notify_review_pending in _execute_review
    (
        '            await workflow.execute_activity(\n'
        '                _notify_review_pending,\n'
        '                node_id,\n'
        '                project_id,',
        '            await workflow.execute_activity(\n'
        '                _notify_review_pending,\n'
        '                args=[node_id, project_id],'
    ),
    # create_review_assignments in _execute_review
    (
        '        assignment_result = await workflow.execute_activity(\n'
        '            _create_review_assignments,\n'
        '            node_id,\n'
        '            project_id,\n'
        '            reviewers,',
        '        assignment_result = await workflow.execute_activity(\n'
        '            _create_review_assignments,\n'
        '            args=[node_id, project_id, reviewers],'
    ),
    # evaluate_condition
    (
        '        cond_result = await workflow.execute_activity(\n'
        '            _evaluate_condition,\n'
        '            node_id,\n'
        '            project_id,\n'
        '            condition_expr,',
        '        cond_result = await workflow.execute_activity(\n'
        '            _evaluate_condition,\n'
        '            args=[node_id, project_id, condition_expr],'
    ),
    # start_ai_writing
    (
        '        ai_result = await workflow.execute_activity(\n'
        '            _start_ai_writing,\n'
        '            node_id,\n'
        '            project_id,\n'
        '            chapter_id,',
        '        ai_result = await workflow.execute_activity(\n'
        '            _start_ai_writing,\n'
        '            args=[node_id, project_id, chapter_id],'
    ),
    # parse_sources
    (
        '            parsed = await workflow.execute_activity(\n'
        '                _parse_sources,\n'
        '                str(chapter_id),\n'
        '                content,',
        '            parsed = await workflow.execute_activity(\n'
        '                _parse_sources,\n'
        '                args=[str(chapter_id), content],'
    ),
    # store_sources
    (
        '                await workflow.execute_activity(\n'
        '                    _store_sources,\n'
        '                    str(chapter_id),\n'
        '                    parsed["sources"],',
        '                await workflow.execute_activity(\n'
        '                    _store_sources,\n'
        '                    args=[str(chapter_id), parsed["sources"]],'
    ),
    # notify_phase_start in _execute_phase_tasks
    (
        '            await workflow.execute_activity(\n'
        '                _notify_phase_start, phase_id, project_id,\n'
        '                start_to_close_timeout=timedelta(seconds=30),\n'
        '            )',
        '            await workflow.execute_activity(\n'
        '                _notify_phase_start, args=[phase_id, project_id],\n'
        '                start_to_close_timeout=timedelta(seconds=30),\n'
        '            )'
    ),
]

for old_pattern, new_pattern in fixes:
    if old_pattern in content:
        content = content.replace(old_pattern, new_pattern)
        print(f"Fixed: {old_pattern.split(chr(10))[1].strip()[:60]}...")
    else:
        print(f"NOT FOUND: {old_pattern.split(chr(10))[1].strip()[:60]}...")

with open("app/extensions/workflow/temporal/workflows.py", "w") as f:
    f.write(content)

print("\nAll fixes applied successfully!")
