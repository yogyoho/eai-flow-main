#!/usr/bin/env python3
"""
CAD Comprehension MCP Server.

One tool: analyze_cad(file_path, rasterize=False).
Parses a DXF into structured facts (layers, entity counts, pipe diameters,
hydrant risers, axis dimensions, text samples, extent) and optionally
rasterizes a PNG preview for vision-based symbol recognition.

Pipeline:
  DXF ──ezdxf──▶ structured_facts (JSON)        # deterministic, ~2s
       └─opt──▶ raster PNG (matplotlib)          # ~80s/big drawing, opt-in
                       │
                       ▼
        fire-protection / EIA compliance skills + Office-Word report

Runs as a standalone container, exposed to the deer-flow gateway over MCP
streamable-http (see docker/docker-compose.extensions.yaml `cad` service).
The gateway's MultiServerMCPClient loads it; the agent calls it via function
calling. Output feeds the compliance skills + Word report.

Phase 1: DXF only. DWG must be converted to DXF upstream (AutoCAD DXFOUT) or
via ODA File Converter (not bundled — add when a real DWG-without-DXF arrives).
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

# ponytail: headless backend must be set before pyplot is imported (rasterize path)
import matplotlib

matplotlib.use("Agg")

from mcp.server.fastmcp import FastMCP  # noqa: E402

# mcp 1.28: host/port/path are FastMCP() constructor kwargs (run() only takes
# transport), and the default host is 127.0.0.1 — must override to 0.0.0.0 or
# the server is unreachable from the gateway over the docker network.
mcp = FastMCP(
    "CAD Comprehension",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8003")),
    streamable_http_path=os.getenv("MCP_PATH", "/mcp"),
)

_DN = re.compile(r"\bDN\d+\b")  # pipe diameters, e.g. DN100
_XL = re.compile(r"\bXL-?\s*\d+\b")  # hydrant risers, e.g. XL-1
_MAX_SAMPLES = 25

# Data root mounted into this container (see docker-compose `cad` service).
# The agent is told uploads live at /mnt/user-data/uploads/<name> — a sandbox
# virtual path the MCP tool receives as a literal string. _resolve_path bridges
# the two by searching the data root. Read at call time so tests/env changes apply.
_DEFAULT_DATA_ROOT = "/data"


def _resolve_path(file_path: str) -> Path | None:
    """Resolve an agent-supplied path to a real file in this container.

    Accepts either a literal resolvable path, or a sandbox virtual path of the
    form /mnt/user-data/<sub>/<name> (what UploadsMiddleware tells the agent).
    Virtual paths are thread-scoped and hide the users/{uid}/threads/{tid}
    segment, so we glob-search the data root for the first match.

    ponytail: glob assumes the filename is unique across threads; pass an
    absolute physical path to disambiguate. Upgrade path: carry thread_id via
    MCP context and resolve directly.
    """
    p = Path(file_path)
    if p.exists():
        return p
    if "/mnt/user-data/" in file_path:
        rest = file_path.split("/mnt/user-data/", 1)[1].lstrip("/")
        matches = sorted(Path(os.getenv("CAD_DATA_ROOT", _DEFAULT_DATA_ROOT)).glob(f"users/*/threads/*/user-data/{rest}"))
        return matches[0] if matches else None
    return None


def _resolve_out(file_path: str) -> Path | None:
    """Resolve an agent OUTPUT path to a real write path in this container.

    Unlike _resolve_path (read), the file need not exist yet. Literal absolute
    path wins; otherwise a /mnt/user-data/<rest> virtual path is glob-searched
    under the data root (mirrors mcp-server/text-to-cad-mcp). ponytail: glob
    assumes the thread dir for <rest> is unique; pass an absolute path to
    disambiguate. Upgrade path: carry thread_id via MCP context.
    """
    p = Path(file_path)
    if p.is_absolute():
        return p
    if "/mnt/user-data/" in file_path:
        rest = file_path.split("/mnt/user-data/", 1)[1].lstrip("/")
        parts = rest.split("/")
        leaf = parts[-1]
        parent_rest = "/".join(parts[:-1])
        root = Path(os.getenv("CAD_DATA_ROOT", _DEFAULT_DATA_ROOT))
        glob_pat = f"users/*/threads/*/user-data/{parent_rest}" if parent_rest else "users/*/threads/*/user-data"
        matches = sorted(root.glob(glob_pat))
        return (matches[0] / leaf) if matches else None
    return None


def _entity_text(e) -> str:
    """Best-effort text from a TEXT/MTEXT entity (MTEXT strips formatting)."""
    try:
        if e.dxftype() == "MTEXT":
            return e.text.strip()
        return e.dxf.text.strip()
    except Exception:
        return ""


def _parse_dxf(path: Path) -> tuple[dict, list[str]]:
    """Parse a DXF into structured facts. Returns (facts, warnings)."""
    import ezdxf

    try:
        doc = ezdxf.readfile(str(path))
    except Exception as exc:  # IOError / DXFStructureError on corrupt input
        raise RuntimeError(f"DXF parse failed: {exc}") from exc

    msp = doc.modelspace()
    entities = list(msp)

    entity_counts = dict(Counter(e.dxftype() for e in entities))

    layer_counts: Counter = Counter()
    for e in entities:
        try:
            layer_counts[e.dxf.layer] += 1
        except Exception:
            layer_counts["<no-layer>"] += 1
    layers = [{"name": n, "entities": c} for n, c in layer_counts.most_common()]

    pipes: Counter = Counter()
    risers: Counter = Counter()
    text_samples: list[str] = []
    for e in entities:
        if e.dxftype() not in ("TEXT", "MTEXT"):
            continue
        t = _entity_text(e)
        if not t:
            continue
        for m in _DN.finditer(t):
            pipes[m.group()] += 1
        for m in _XL.finditer(t):
            risers[re.sub(r"\s+", "", m.group())] += 1
        if len(text_samples) < _MAX_SAMPLES:
            text_samples.append(t[:80])

    dim_samples: list[float] = []
    for e in entities:
        if e.dxftype() != "DIMENSION":
            continue
        try:
            m = e.get_measurement()
            if m and len(dim_samples) < _MAX_SAMPLES:
                dim_samples.append(round(float(m)))
        except Exception:
            continue

    extent: dict | None = None
    try:
        extmin = doc.header.get("$EXTMIN")
        extmax = doc.header.get("$EXTMAX")
        if extmin and extmax:
            extent = {
                "min": [round(extmin.x, 1), round(extmin.y, 1)],
                "max": [round(extmax.x, 1), round(extmax.y, 1)],
                "width_mm": round(extmax.x - extmin.x, 1),
                "height_mm": round(extmax.y - extmin.y, 1),
            }
    except Exception:
        pass
    if extent is None:
        # Many real DXFs omit $EXTMIN/$EXTMAX — fall back to computing bounds
        # from the entities (fast=True skips curves, good enough for an extent).
        try:
            from ezdxf import bbox as _bbox

            e = _bbox.extents(entities, fast=True)
            if e.has_data:
                extent = {
                    "min": [round(e.extmin.x, 1), round(e.extmin.y, 1)],
                    "max": [round(e.extmax.x, 1), round(e.extmax.y, 1)],
                    "width_mm": round(e.extmax.x - e.extmin.x, 1),
                    "height_mm": round(e.extmax.y - e.extmin.y, 1),
                }
        except Exception:
            pass

    # Note: ezdxf decodes DXF Chinese (GBK) correctly to real Unicode (verified:
    # 器械 = U+5668 U+68B0). "Garbled" output on the console is a terminal-rendering
    # artifact, NOT data loss — the JSON the agent receives carries valid Chinese.
    # Genuine codepage loss (bytes already '?' on disk) is rare; ASCII facts
    # (DN sizes, XL risers) survive regardless, so no warning heuristic is needed.
    warnings: list[str] = []
    codepage = doc.header.get("$DWGCODEPAGE", "")

    facts = {
        "dxf_version": doc.dxfversion,
        "codepage": codepage or None,
        "entity_count": len(entities),
        "entity_counts": entity_counts,
        "layers": layers,
        "pipe_diameters": [{"size": k, "count": v} for k, v in pipes.most_common()],
        "hydrant_risers": [{"id": k, "count": v} for k, v in risers.most_common()],
        "axis_dimensions_mm_sample": dim_samples,
        "text_samples": text_samples,
        "extent": extent,
    }
    return facts, warnings


def _rasterize(path: Path, out_png: Path, dpi: int = 80) -> str:
    """Render modelspace to PNG via matplotlib. ~80s on large drawings."""
    import matplotlib.pyplot as plt
    import ezdxf
    from ezdxf.addons.drawing.frontend import Frontend
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.properties import RenderContext

    doc = ezdxf.readfile(str(path))
    fig, ax = plt.subplots()
    Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(doc.modelspace())
    fig.savefig(str(out_png), dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return str(out_png)


@mcp.tool()
def analyze_cad(file_path: str, rasterize: bool = False) -> str:
    """Parse a DXF drawing into structured facts for compliance/report skills.

    Extracts layers, entity counts, pipe diameters (DN*), hydrant risers (XL-*),
    axis/dimension measurements (mm), text samples, and drawing extent.
    Structured-first: these ASCII facts survive even when Chinese text labels
    are lost on export. Optionally rasterizes a PNG for vision-based symbol
    recognition (slow: ~80s for large drawings — enable only when needed).

    Args:
        file_path: Absolute path to a .dxf file, as seen inside this container.
            The container shares the deer-flow data volume (mounted at /data).
        rasterize: If True, also render a PNG preview next to the input. Slow.

    Returns:
        JSON: {status:"ok", file, facts, raster_png?, warnings?} on success,
        or {status:"error", error, ...} on failure (file_not_found /
        unsupported_format / parse_failed).
    """
    if Path(file_path).suffix.lower() != ".dxf":
        # Format check first: a clearer hint than file_not_found for a wrong-type path.
        # Phase 1: DXF only. DWG needs upstream conversion (AutoCAD DXFOUT) or
        # ODA File Converter, which is not yet bundled in this image.
        return json.dumps(
            {
                "status": "error",
                "error": "unsupported_format",
                "file": file_path,
                "suffix": Path(file_path).suffix.lower(),
                "hint": "Phase 1 accepts .dxf only. Convert .dwg to .dxf via AutoCAD DXFOUT, then retry.",
            },
            ensure_ascii=False,
        )
    p = _resolve_path(file_path)
    if p is None:
        return json.dumps({"status": "error", "error": "file_not_found", "file": file_path}, ensure_ascii=False)
        # Phase 1: DXF only. DWG needs upstream conversion (AutoCAD DXFOUT) or
        # ODA File Converter, which is not yet bundled in this image.
        return json.dumps(
            {
                "status": "error",
                "error": "unsupported_format",
                "file": file_path,
                "suffix": p.suffix.lower(),
                "hint": "Phase 1 accepts .dxf only. Convert .dwg to .dxf via AutoCAD DXFOUT, then retry.",
            },
            ensure_ascii=False,
        )

    try:
        facts, warnings = _parse_dxf(p)
    except RuntimeError as exc:
        return json.dumps({"status": "error", "error": "parse_failed", "file": file_path, "detail": str(exc)}, ensure_ascii=False)

    result: dict = {"status": "ok", "file": file_path, "facts": facts}
    if warnings:
        result["warnings"] = warnings

    if rasterize:
        out_png = p.with_suffix(".preview.png")
        try:
            result["raster_png"] = _rasterize(p, out_png)
        except Exception as exc:  # rasterization is best-effort; parse result still returned
            result["raster_error"] = str(exc)

    return json.dumps(result, ensure_ascii=False, default=str)


# Engineering Drawing Platform: compose_drawing renders an intent JSON into a
# DXF (+ optional PNG) via the domain-agnostic core in edp/. Domain packs live
# under domains/<domain>/ (baked into the image). See PLATFORM_SPEC.md.
_DOMAINS_ROOT = os.getenv("EDP_DOMAINS_ROOT", str(Path(__file__).resolve().parent / "domains"))


@mcp.tool()
def compose_drawing(domain: str, drawing_type: str, intent_json: str, output_path: str, also_png: bool = True) -> str:
    """Generate a 2D engineering drawing (DXF) from a structured intent JSON.

    Domain-agnostic composer: the domain pack (domains/<domain>/) supplies the
    symbol library + entity schema + frame template + the strategy for the
    drawing type. The intent describes entities + annotations + title block; the
    composer places them deterministically and validates the result. Output is a
    DXF; PNG is a matplotlib preview.

    Use for: 煤矿设计图纸 (roadway_section), future 化工 P&ID, etc. For 3D solids
    use the separate text-to-cad MCP; this tool is 2D drafting only.

    Args:
        domain: pack name, e.g. "mine".
        drawing_type: a type declared in the pack manifest, e.g. "roadway_section".
        intent_json: intent object (see PLATFORM_SPEC.md §3) as a JSON string or
            already-parsed object — entities[], annotations[], title_block.
        output_path: .dxf destination — absolute, or /mnt/user-data/outputs/<name>.dxf.
        also_png: also write <name>.png preview next to the DXF.

    Returns:
        JSON {status:"ok", dxf, png?, report:{placed, skipped[]}, validations[]}
        on success, or {status:"error", error, detail?} (unknown_domain /
        unknown_drawing_type / unknown_strategy / schema_invalid / bad_suffix /
        resolve_failed / run_failed).
    """
    from edp import ComposeError, compose_from_json

    out = _resolve_out(output_path)
    if out is None:
        return json.dumps({"status": "error", "error": "resolve_failed", "output_path": output_path}, ensure_ascii=False)
    if out.suffix.lower() != ".dxf":
        return json.dumps({"status": "error", "error": "bad_suffix", "output_path": output_path, "hint": "output_path must end in .dxf"}, ensure_ascii=False)
    try:
        doc, report, validations = compose_from_json(intent_json, Path(_DOMAINS_ROOT))
    except ComposeError as exc:
        return json.dumps({"status": "error", "error": exc.code, "detail": exc.detail}, ensure_ascii=False)
    except Exception as exc:  # ezdxf/render errors — surface, don't crash the MCP server
        return json.dumps({"status": "error", "error": "run_failed", "detail": str(exc)}, ensure_ascii=False)

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(out))
    except Exception as exc:
        return json.dumps({"status": "error", "error": "run_failed", "detail": f"DXF write failed: {exc}"}, ensure_ascii=False)

    info: dict = {
        "status": "ok",
        "dxf": output_path,
        "report": {"placed": report.placed, "skipped": report.skipped},
        "validations": validations,
    }
    if also_png:
        png = out.with_suffix(".png")
        try:
            from edp.render import rasterize

            rasterize(doc, png)
            info["png"] = output_path[: -len(out.suffix)] + ".png"
        except Exception as exc:  # preview is best-effort; DXF still returned
            info["png_error"] = str(exc)
    return json.dumps(info, ensure_ascii=False, default=str)


def main() -> None:
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))


if __name__ == "__main__":
    main()
