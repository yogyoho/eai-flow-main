"""RenderStrategies — consume entities by placement.kind, place DXF geometry.

The bridge between paradigm-agnostic entities and paradigm-specific renderers
is ``entity.placement.kind``. Each strategy consumes the kinds it knows and
skips (with a reason) the rest — never raises on an unknown kind/type.

Layout strategy (M1): point (symbol), polyline (linear feature ±width),
region (closed ±hatch). Schematic strategy (P&ID nodes/edges) is M2.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# The contracted primitive vocabulary. validate.py flags symbols using ops
# outside this set so a typo'd op never silently renders nothing.
KNOWN_OPS = {"line", "polyline", "circle", "arc", "text", "hatch", "insert"}


@dataclass
class RenderReport:
    placed: int = 0
    skipped: list[dict] = field(default_factory=list)
    bounds: dict | None = None

    def skip(self, entity_id, reason: str) -> None:
        self.skipped.append({"id": entity_id, "reason": reason})


def render_layout(msp, entities: list[dict], symbols, layers: dict) -> RenderReport:
    """Layout strategy: place each entity by placement.kind."""
    report = RenderReport()
    for entity in entities or []:
        eid = entity.get("id", "?")
        placement = entity.get("placement") or {}
        kind = placement.get("kind")
        layer = entity.get("layer") or "0"
        if kind == "point":
            _place_point(msp, entity, placement, symbols, report)
        elif kind == "polyline":
            _place_polyline(msp, placement, layer, report, eid)
        elif kind == "region":
            _place_region(msp, placement, layer, report, eid)
        else:
            report.skip(eid, f"unknown placement.kind: {kind!r}")
    return report


def _place_point(msp, entity, placement, symbols, report: RenderReport) -> None:
    eid = entity.get("id", "?")
    spec = symbols.resolve(entity.get("type", ""))
    if spec is None:
        report.skip(eid, f"unknown symbol type: {entity.get('type')!r}")
        return
    at = placement.get("at", [0, 0])
    layer = entity.get("layer") or spec.default_layer
    dx = float(at[0]) - spec.insertion_base[0]
    dy = float(at[1]) - spec.insertion_base[1]
    rotate = math.radians(placement.get("rotate", 0) or 0)
    scale = float(placement.get("scale", 1.0) or 1.0)
    for prim in spec.primitives:
        _draw_primitive(msp, prim, dx, dy, layer, scale, rotate)
    report.placed += 1


def _place_polyline(msp, placement, layer, report: RenderReport, eid) -> None:
    coords = placement.get("coords", [])
    if len(coords) < 2:
        report.skip(eid, "polyline needs ≥2 coords")
        return
    pts = [(float(x), float(y)) for x, y in coords]
    poly = msp.add_lwpolyline(pts, dxfattribs={"layer": layer}, close=False)
    width = placement.get("width_mm") or placement.get("width")
    if width:
        # ponytail: thick-band representation of a corridor at width. True
        # parallel double-line boundary needs a shapely offset (deferred; not
        # in requirements yet). Upgrade path: add shapely, offset ±width/2.
        poly.const_width = float(width)
    report.placed += 1


def _place_region(msp, placement, layer, report: RenderReport, eid) -> None:
    coords = placement.get("coords", [])
    if len(coords) < 3:
        report.skip(eid, "region needs ≥3 coords")
        return
    pts = [(float(x), float(y)) for x, y in coords]
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer}, close=True)
    pattern = placement.get("hatch_pattern") or placement.get("hatch")
    if pattern and str(pattern).lower() != "none":
        _add_hatch(msp, pts, str(pattern), {"layer": layer})
    report.placed += 1


def _tx(x, y, dx, dy, scale, rotate):
    """Scale about origin, rotate about origin, then translate by (dx,dy)."""
    sx, sy = x * scale, y * scale
    rx = sx * math.cos(rotate) - sy * math.sin(rotate)
    ry = sx * math.sin(rotate) + sy * math.cos(rotate)
    return rx + dx, ry + dy


def _draw_primitive(msp, prim: dict, dx, dy, layer, scale, rotate) -> None:
    op = prim.get("op")
    dxf = {"layer": layer}
    if op == "line":
        x1, y1 = _tx(prim["x1"], prim["y1"], dx, dy, scale, rotate)
        x2, y2 = _tx(prim["x2"], prim["y2"], dx, dy, scale, rotate)
        msp.add_line((x1, y1), (x2, y2), dxfattribs=dxf)
    elif op == "polyline":
        pts = [_tx(px, py, dx, dy, scale, rotate) for px, py in prim["points"]]
        msp.add_lwpolyline(pts, dxfattribs=dxf, close=prim.get("closed", False))
    elif op == "circle":
        cx, cy = _tx(prim["cx"], prim["cy"], dx, dy, scale, rotate)
        msp.add_circle((cx, cy), prim["r"] * scale, dxfattribs=dxf)
    elif op == "arc":
        cx, cy = _tx(prim["cx"], prim["cy"], dx, dy, scale, rotate)
        ang = math.degrees(rotate)
        msp.add_arc((cx, cy), prim["r"] * scale, start_angle=prim["start_angle"] + ang, end_angle=prim["end_angle"] + ang, dxfattribs=dxf)
    elif op == "text":
        x, y = _tx(prim["x"], prim["y"], dx, dy, scale, rotate)
        t = msp.add_text(str(prim.get("string", "")), dxfattribs={**dxf, "height": float(prim.get("height", 50)) * scale})
        t.set_placement((x, y))
    elif op == "hatch":
        boundary = [_tx(px, py, dx, dy, scale, rotate) for px, py in prim["boundary"]]
        _add_hatch(msp, boundary, prim.get("pattern", "SOLID"), dxf)
    elif op == "insert":
        # Nested symbol composition — needs the SymbolLib to resolve recursively.
        # No M1 symbol nests; deferred (TODO M2 once a symbol actually composes).
        pass
    # Unknown ops are NOT silent: validate.py flags them via KNOWN_OPS at compose time.


def _add_hatch(msp, boundary_points, pattern: str, dxf: dict) -> None:
    # ezdxf 1.4: set_pattern_fill assigns a named pattern (ANSI31 etc. loaded by
    # new_doc's setup=True); set_solid_fill for SOLID. Patterns live in the doc's
    # ACAD_PATTERNS table — unknown names render empty, so validate is the safety net.
    hatch = msp.add_hatch(dxfattribs=dxf)
    hatch.paths.add_polyline_path(boundary_points, is_closed=True)
    if pattern.upper() == "SOLID":
        hatch.set_solid_fill()
    else:
        hatch.set_pattern_fill(pattern, scale=1.0)


# ── Schematic strategy (M2 — P&ID nodes + edges) ──────────────────────────


def render_schematic(msp, entities: list[dict], symbols, layers: dict) -> RenderReport:
    """Schematic strategy: place nodes (recording their port world-positions),
    then route edges between node ports. Paradigm-pure: layout kinds (point/
    polyline/region) are skipped — a mixed-paradigm drawing is a future concern.

    Two passes so an edge may reference a node declared later in the entity list.
    """
    report = RenderReport()
    node_ports: dict[str, dict] = {}
    for entity in entities or []:
        if (entity.get("placement") or {}).get("kind") == "node":
            _place_node(msp, entity, symbols, report, node_ports)
    for entity in entities or []:
        kind = (entity.get("placement") or {}).get("kind")
        if kind == "edge":
            _place_edge(msp, entity, node_ports, report)
        elif kind == "node":
            pass  # placed in pass 1
        elif kind in ("point", "polyline", "region"):
            report.skip(entity.get("id", "?"), f"schematic strategy does not handle layout kind {kind!r}")
        elif kind:
            report.skip(entity.get("id", "?"), f"unknown placement.kind: {kind!r}")
    return report


def _place_node(msp, entity, symbols, report: RenderReport, node_ports: dict) -> None:
    eid = entity.get("id", "?")
    spec = symbols.resolve(entity.get("type", ""))
    if spec is None:
        report.skip(eid, f"unknown symbol type: {entity.get('type')!r}")
        return
    placement = entity.get("placement") or {}
    at = placement.get("at", [0, 0])
    layer = entity.get("layer") or spec.default_layer
    dx = float(at[0]) - spec.insertion_base[0]
    dy = float(at[1]) - spec.insertion_base[1]
    rotate = math.radians(placement.get("rotate", 0) or 0)
    scale = float(placement.get("scale", 1.0) or 1.0)
    for prim in spec.primitives:
        _draw_primitive(msp, prim, dx, dy, layer, scale, rotate)
    # Equipment tag at the symbol's label anchor (P&ID equipment labels).
    label = (entity.get("attrs") or {}).get("label")
    if label and spec.label_anchor:
        lx, ly = _tx(spec.label_anchor[0], spec.label_anchor[1], dx, dy, scale, rotate)
        t = msp.add_text(str(label), dxfattribs={"layer": "标注", "height": 80 * scale})
        t.set_placement((lx, ly))
    # Record node center + each port's world position for edge routing.
    ports = {"__center__": _tx(0, 0, dx, dy, scale, rotate)}
    for p in spec.ports:
        ports[p["id"]] = _tx(p["at"][0], p["at"][1], dx, dy, scale, rotate)
    node_ports[eid] = ports
    report.placed += 1


def _resolve_endpoint(ep, node_ports: dict):
    """Resolve an edge endpoint to a world (x, y). Accepts a literal [x,y] coord
    or {node, port?} (falls back to the node center when port is omitted/unknown)."""
    if isinstance(ep, (list, tuple)) and len(ep) >= 2:
        return (float(ep[0]), float(ep[1]))
    if isinstance(ep, dict):
        ports = node_ports.get(ep.get("node"))
        if ports:
            pid = ep.get("port")
            if pid and pid in ports:
                return ports[pid]
            return ports.get("__center__")
    return None


def _place_edge(msp, entity, node_ports: dict, report: RenderReport) -> None:
    eid = entity.get("id", "?")
    placement = entity.get("placement") or {}
    start = _resolve_endpoint(placement.get("from"), node_ports)
    end = _resolve_endpoint(placement.get("to"), node_ports)
    if start is None or end is None:
        report.skip(eid, f"edge endpoint unresolved (from={placement.get('from')!r} to={placement.get('to')!r})")
        return
    layer = entity.get("layer") or "管道"
    route = (placement.get("route") or "ortho").lower()
    waypoints = placement.get("waypoints") or []
    pts = _route_points(start, end, route, waypoints)
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer}, close=False)
    report.placed += 1


def _route_points(start, end, route: str, waypoints):
    """Connector routing. manual=through waypoints; direct=straight; ortho
    (default)=horizontal-then-vertical L-route between the two port endpoints.

    ponytail: this is a minimal orthogonal router — no overlap avoidance, no
    port-direction awareness. Real P&ID routing (avoid equipment, respect port
    facing, route shared line bundles) is a later upgrade; this proves the edge
    abstraction renders a routed connector between node ports.
    """
    if route == "manual" and waypoints:
        return [start, *[(float(w[0]), float(w[1])) for w in waypoints], end]
    if route == "direct":
        return [start, end]
    sx, sy = start
    ex, ey = end
    if abs(ex - sx) < 1 or abs(ey - sy) < 1:
        return [start, end]  # already axis-aligned
    return [start, (ex, sy), end]  # L-route: across then up/down


# Strategy registry. The composer reads the strategy name from the pack's
# drawing_type declaration. isometric (化工管段图) is a future addition.
STRATEGIES = {"layout": render_layout, "schematic": render_schematic}
