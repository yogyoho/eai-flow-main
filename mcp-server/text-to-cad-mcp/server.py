#!/usr/bin/env python3
"""text-to-cad MCP Server — standalone container.

One tool: create_step(source, output_path, also_stl=False).
Executes agent-supplied build123d Python source and exports a STEP (primary
interchange format) plus an optional STL. Keeps the heavy CAD kernel
(build123d + OCP/OpenCascade native libs) out of the gateway image.

Mirrors mcp-server/cad-mcp: HTTP MCP over streamable-http, shares the
deer-flow data volume (mounted at /data), resolves agent virtual paths
(/mnt/user-data/<rest>) by glob-searching the data root.

Phase 1: STEP/STL generation only. Inspection/snapshot/assembly/DXF/URDF/
G-code come later — clone more @mcp.tool() functions here. See README.

Why STEP-first: STEP (ISO 10303) is the lossless interchange format every
mechanical CAD tool reads; STL/3MF are downstream mesh exports. The agent
authors build123d source (it has the LLM context); this container only
executes it — clean separation of reasoning vs. heavy execution.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP  # noqa: E402

# mcp 1.28: host/port/path are FastMCP() constructor kwargs (run() only takes
# transport), and the default host is 127.0.0.1 — must override to 0.0.0.0 or
# the server is unreachable from the gateway over the docker network.
mcp = FastMCP(
    "text-to-cad",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8004")),
    streamable_http_path=os.getenv("MCP_PATH", "/mcp"),
)

# Data root mounted into this container (see docker-compose `text-to-cad`
# service). The agent writes outputs at /mnt/user-data/outputs/<name> — a
# sandbox virtual path this MCP tool receives as a literal string. Read at
# call time so tests/env changes apply.
_DEFAULT_DATA_ROOT = "/data"


def _resolve_output_path(file_path: str) -> Path | None:
    """Resolve an agent-supplied OUTPUT path to a real path in this container.

    Unlike cad-mcp's read-oriented resolver, the target file need not exist
    yet (we create it). Accepts:
      - a literal absolute path (parent is mkdir'd by the caller), or
      - a /mnt/user-data/<rest> virtual path — the leaf is the new file, the
        parent is glob-searched under the data root.

    ponytail: glob assumes the thread dir for a given <rest> is unique; if two
    threads share the same outputs path, this picks the first. Upgrade path:
    carry thread_id via MCP context and resolve directly.
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


@mcp.tool()
def create_step(source: str, output_path: str, also_stl: bool = False) -> str:
    """Generate a STEP (ISO 10303) file from build123d Python source.

    Execute build123d code and export the resulting solid to STEP — the
    primary lossless interchange format for mechanical CAD. Optionally also
    export an STL mesh.

    The `source` MUST assign the final geometry to a variable named ``result``.
    Units are millimeters. Examples::

        result = Box(100, 60, 20)

        with BuildPart() as p:
            Box(100, 60, 20)
            # ...holes, fillets, etc.
        result = p.part

    Use this for: natural-language CAD specs ("a 100x60x20 block with four
    8mm through-holes"), brackets, enclosures, shafts, flanges — anything that
    becomes a parametric solid.

    Args:
        source: build123d Python source. Must end with the final geometry
            bound to a variable named ``result`` (a Part/Shape/Compound).
            build123d's full API is pre-imported (``from build123d import *``).
        output_path: Where to write the .step. An absolute path, or a
            /mnt/user-data/outputs/<name>.step virtual path (the sandbox path
            the agent uses; this container shares the data volume so the file
            lands in the right thread directory).
        also_stl: If True, also write an STL (same basename) next to the STEP.

    Returns:
        JSON: ``{status:"ok", step, stl?, volume_mm3?, bbox_mm?}`` on success,
        or ``{status:"error", error, detail?}`` on failure (``resolve_failed``
        / ``bad_suffix`` / ``no_result`` / ``exec_failed`` / ``export_failed``).
        Geometry summary (volume, bounding box) is best-effort and may be
        absent if the shape does not expose it.
    """
    out = _resolve_output_path(output_path)
    if out is None:
        return json.dumps({"status": "error", "error": "resolve_failed", "output_path": output_path}, ensure_ascii=False)
    if out.suffix.lower() not in (".step", ".stp"):
        return json.dumps(
            {"status": "error", "error": "bad_suffix", "output_path": output_path,
             "hint": "output_path must end in .step or .stp"},
            ensure_ascii=False,
        )
    out.parent.mkdir(parents=True, exist_ok=True)

    # Exec the agent's source in an isolated namespace; build123d is pre-imported.
    # Security: this runs untrusted-by-construction agent code, but the container
    # IS the isolation boundary (same posture as the sandbox bash tool).
    preamble = "from build123d import *\n"
    ns: dict = {}
    try:
        exec(compile(preamble + source + "\n", "<agent_source>", "exec"), ns)
    except Exception as exc:
        return json.dumps({"status": "error", "error": "exec_failed", "detail": repr(exc)}, ensure_ascii=False)

    result = ns.get("result")
    if result is None:
        return json.dumps(
            {"status": "error", "error": "no_result",
             "hint": "source must assign the final geometry to a variable named `result`"},
            ensure_ascii=False,
        )

    # Export STEP (build123d top-level export_step).
    try:
        from build123d import export_step

        export_step(result, str(out))
    except Exception as exc:
        return json.dumps({"status": "error", "error": "export_failed", "detail": repr(exc)}, ensure_ascii=False)

    info: dict = {"status": "ok", "step": output_path}

    # Best-effort geometry summary — never fail the export over this.
    try:
        bb = result.bounding_box
        info["bbox_mm"] = {
            "size": [round(bb.size.X, 3), round(bb.size.Y, 3), round(bb.size.Z, 3)],
        }
    except Exception:
        pass
    try:
        info["volume_mm3"] = round(float(result.volume), 3)
    except Exception:
        pass

    if also_stl:
        try:
            from build123d import export_stl

            stl_virtual = str(out.with_suffix(".stl"))
            # Re-express the STL path in the same virtual form the caller used.
            stl_virtual = output_path[: -len(out.suffix)] + ".stl"
            export_stl(result, str(out.with_suffix(".stl")))
            info["stl"] = stl_virtual
        except Exception as exc:
            info["stl_error"] = repr(exc)

    return json.dumps(info, ensure_ascii=False, default=str)


def main() -> None:
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))


if __name__ == "__main__":
    main()
