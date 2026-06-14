"""Regression tests for v2 graph_json (mainGraph) handling.

DF-5 root cause: the Temporal workflow ``run()`` and several readers called
``graph.get("nodes")`` on the v2 structure, where nodes live under
``mainGraph``. They saw an empty graph and the workflow completed without
executing any node. These tests lock the unwrap behaviour.
"""

from app.extensions.workflow.service import topological_sort


def _v2_graph():
    """The on-disk v2 shape: nodes/edges nested under mainGraph."""
    return {
        "version": 2,
        "mainGraph": {
            "nodes": [
                {"id": "t1-ai", "type": "ai_generate", "data": {}},
                {"id": "t2-edit", "type": "task", "data": {}},
                {"id": "t3-submit", "type": "task", "data": {}},
                {"id": "t4-review", "type": "review", "data": {}},
            ],
            "edges": [
                {"source": "t1-ai", "target": "t2-edit"},
                {"source": "t2-edit", "target": "t3-submit"},
                {"source": "t3-submit", "target": "t4-review"},
            ],
        },
        "subGraphs": {},
    }


def test_topological_sort_unwraps_main_graph():
    """v2 graph_json must be unwrapped so all nodes are visible (DF-5)."""
    order = topological_sort(_v2_graph())
    assert set(order) == {"t1-ai", "t2-edit", "t3-submit", "t4-review"}
    # start node (no upstream) must come first
    assert order[0] == "t1-ai"
    # edges respected: t1-ai before t2-edit before t3-submit before t4-review
    assert order.index("t1-ai") < order.index("t2-edit")
    assert order.index("t2-edit") < order.index("t3-submit")
    assert order.index("t3-submit") < order.index("t4-review")


def test_topological_sort_handles_flat_v1_graph():
    """Backward compat: flat v1 graphs (nodes at top level) still work."""
    flat = {
        "nodes": [{"id": "a", "type": "task"}, {"id": "b", "type": "task"}],
        "edges": [{"source": "a", "target": "b"}],
    }
    assert topological_sort(flat) == ["a", "b"]


def test_v2_graph_without_maingraph_does_not_crash():
    """A graph with neither mainGraph nor nodes yields an empty order."""
    assert topological_sort({"version": 2, "subGraphs": {}}) == []


def _walk_graph(graph: dict) -> list[str]:
    """Mirror of DynamicGraphWorkflow.run()'s forward walk (minus the activities).

    Used to lock the rollback-edge handling: a ``label="rejected"`` edge is a
    conditional rollback path, NOT a forward dependency. Counting it as upstream
    creates a review→edit cycle that deadlocks the walk.
    """
    mg = graph.get("mainGraph", graph)
    nodes = mg.get("nodes", [])
    edges = mg.get("edges", [])
    downstream = {n["id"]: [] for n in nodes}
    upstream = {n["id"]: [] for n in nodes}
    for e in edges:
        if e.get("label") == "rejected":
            continue
        s, t = e.get("source"), e.get("target")
        if s and t:
            downstream.setdefault(s, []).append(t)
            upstream.setdefault(t, []).append(s)
    ready = [n for n, p in upstream.items() if not p]
    processed: set[str] = set()
    completed: set[str] = set()
    order: list[str] = []
    while ready:
        nid = ready.pop(0)
        if nid in processed:
            continue
        processed.add(nid)
        completed.add(nid)
        order.append(nid)
        for dn in downstream.get(nid, []):
            if dn in processed:
                continue
            if all(p in completed for p in upstream.get(dn, [])):
                ready.append(dn)
    return order


def test_walk_ignores_rejected_rollback_edge():
    """A rejected rollback edge (review→edit) must not deadlock the forward walk.

    Regression for the DF-5/DF-6 downstream deadlock: before the fix, t2-edit had
    upstream [t1-ai, t4-review] and waited forever for t4-review, so the workflow
    stopped after t1-ai.
    """
    graph = {
        "version": 2,
        "mainGraph": {
            "nodes": [
                {"id": "t1-ai", "type": "ai_generate"},
                {"id": "t2-edit", "type": "task"},
                {"id": "t3-submit", "type": "task"},
                {"id": "t4-review", "type": "review"},
            ],
            "edges": [
                {"source": "t1-ai", "target": "t2-edit"},
                {"source": "t2-edit", "target": "t3-submit"},
                {"source": "t3-submit", "target": "t4-review"},
                {"source": "t4-review", "target": "t2-edit", "label": "rejected"},
            ],
        },
    }
    order = _walk_graph(graph)
    # All four forward nodes are reached despite the review→edit rollback cycle.
    assert order == ["t1-ai", "t2-edit", "t3-submit", "t4-review"]
