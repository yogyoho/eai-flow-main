from collections import defaultdict


def validate_dag(graph: dict) -> dict:
    """Validate a DAG graph_json structure. Returns {valid, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        return {"valid": False, "errors": ["Graph is empty — must have at least one node"], "warnings": []}

    node_ids = {n["id"] for n in nodes}

    # Check edge references
    for edge in edges:
        if edge["source"] not in node_ids:
            errors.append(f"Edge references unknown source node '{edge['source']}'")
        if edge["target"] not in node_ids:
            errors.append(f"Edge references unknown target node '{edge['target']}'")

    # Cycle detection (DFS)
    adjacency = defaultdict(list)
    for edge in edges:
        if edge["source"] in node_ids and edge["target"] in node_ids:
            adjacency[edge["source"]].append(edge["target"])

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}

    def has_cycle(node_id: str) -> bool:
        color[node_id] = GRAY
        for neighbor in adjacency[node_id]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and has_cycle(neighbor):
                return True
        color[node_id] = BLACK
        return False

    for nid in node_ids:
        if color[nid] == WHITE:
            if has_cycle(nid):
                errors.append("Graph contains a cycle")
                break

    # Disconnected node detection
    sources = {e["source"] for e in edges}
    targets = {e["target"] for e in edges}
    connected = sources | targets
    for node in nodes:
        if node["id"] not in connected and len(nodes) > 1:
            warnings.append(f"Node '{node['id']}' ({node.get('data', {}).get('label', '')}) is disconnected")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def topological_sort(graph: dict) -> list[str]:
    """Return nodes in topological order."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    adjacency = defaultdict(list)
    in_degree = defaultdict(int)
    node_ids = [n["id"] for n in nodes]

    for nid in node_ids:
        in_degree[nid] = 0

    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])
        in_degree[edge["target"]] += 1

    queue = [nid for nid in node_ids if in_degree[nid] == 0]
    result = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result
