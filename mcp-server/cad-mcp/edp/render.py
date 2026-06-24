"""Shared drawing helpers — doc/layers setup, frame + title block, annotations, raster.

Domain-agnostic: every domain's frame/annotation/dimension lands through here.
"""
from __future__ import annotations

# ponytail: headless rasterize path — Agg must be set before pyplot import.
import matplotlib

matplotlib.use("Agg")


def new_doc(layers_spec: dict):
    """New R2010 doc with setup (linetypes/dimstyles) + declared layers created."""
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)
    _ensure_layers(doc, layers_spec)
    return doc, doc.modelspace()


def _ensure_layers(doc, layers_spec: dict) -> None:
    for name, attrs in (layers_spec or {}).items():
        if name in doc.layers:
            continue
        color = int((attrs or {}).get("color", 7))
        doc.layers.add(name, color=color)


def render_annotations(msp, annotations: list[dict]) -> None:
    """Domain-agnostic annotation renderer: dimension/text/leader/elevation/coord."""
    for a in annotations or []:
        kind = a.get("kind")
        if kind == "dimension":
            _annotation_dimension(msp, a)
        elif kind == "text":
            _add_text(msp, a.get("string", ""), a.get("at", [0, 0]), a.get("height", 50), "标注")
        elif kind == "leader_text":
            _annotation_leader(msp, a)
        elif kind in ("elevation", "coord_label"):
            val = a.get("value_m", a.get("value", ""))
            prefix = "±" if kind == "elevation" and float(val or 0) == 0 else ("∨" if kind == "elevation" else "")
            _add_text(msp, f"{prefix}{val}", a.get("at", [0, 0]), a.get("height", 50), "标注")
        # unknown annotation kinds ignored silently (annotations are best-effort)


def _add_text(msp, string, at, height, layer) -> None:
    t = msp.add_text(str(string), dxfattribs={"layer": layer, "height": float(height)})
    t.set_placement((float(at[0]), float(at[1])))


def _annotation_dimension(msp, a) -> None:
    x1, y1 = a["from"]
    x2, y2 = a["to"]
    dx, dy = x2 - x1, y2 - y1
    angle = 0.0 if abs(dx) >= abs(dy) else 90.0
    if angle == 0.0:
        base = ((x1 + x2) / 2.0, min(y1, y2) - 600)
    else:
        base = (max(x1, x2) + 600, (y1 + y2) / 2.0)
    dim = msp.add_linear_dim(base=base, p1=(x1, y1), p2=(x2, y2), angle=angle, dxfattribs={"layer": "标注"})
    dim.render()


def _annotation_leader(msp, a) -> None:
    target = a.get("at", [0, 0])
    text = a.get("text", "")
    elbow = [target[0] + 300, target[1] + 300]
    msp.add_line((target[0], target[1]), tuple(elbow), dxfattribs={"layer": "标注"})
    _add_text(msp, text, [elbow[0] + 50, elbow[1]], a.get("height", 50), "标注")


def render_frame(msp, frame_spec: dict | None, title_block: dict | None) -> None:
    """Draw sheet border + inner frame + title block (GB/T 14689 style).

    Simplified for M1: rectangular border, inner margin frame, and a bottom-right
    title-block grid populated from the intent's title_block values. Real GB/T
    14689 has a richer title block; expand the frame template when needed.
    """
    if not frame_spec:
        return
    w, h = frame_spec["size"]
    inner = float(frame_spec.get("inner_margin", 25))
    layer = "图框"
    _ensure_layer(msp.doc, layer, 7)
    msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], dxfattribs={"layer": layer}, close=True)
    msp.add_lwpolyline([(inner, inner), (w - inner, inner), (w - inner, h - inner), (inner, h - inner)], dxfattribs={"layer": layer}, close=True)
    tb = frame_spec.get("title_block")
    if tb:
        _render_title_block(msp, tb, title_block or {}, w, h, inner, layer)


def _render_title_block(msp, tb, values, sheet_w, sheet_h, inner, layer) -> None:
    bw = float(tb["width"])
    bh = float(tb["height"])
    ox = (sheet_w - inner) - bw  # bottom-right anchor, inside inner frame
    oy = inner
    for cell in tb.get("cells", []):
        cx = ox + float(cell["x"])
        cy = oy + float(cell["y"])
        cw = float(cell["w"])
        ch = float(cell["h"])
        msp.add_lwpolyline([(cx, cy), (cx + cw, cy), (cx + cw, cy + ch), (cx, cy + ch)], dxfattribs={"layer": layer}, close=True)
        val = values.get(cell.get("key"))
        if val:
            _add_text(msp, str(val), [cx + 3, cy + ch * 0.3], min(ch * 0.35, 9.0), layer)
        label = cell.get("label")
        if label:
            _add_text(msp, str(label), [cx + 3, cy + ch * 0.65], min(ch * 0.22, 6.0), layer)


def _ensure_layer(doc, name, color) -> None:
    if name not in doc.layers:
        doc.layers.add(name, color=color)


def rasterize(doc, out_png, dpi: int = 100):
    """Render modelspace to PNG via ezdxf's matplotlib frontend."""
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing.frontend import Frontend
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.properties import RenderContext

    fig, ax = plt.subplots()
    Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(doc.modelspace())
    fig.savefig(str(out_png), dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return str(out_png)
