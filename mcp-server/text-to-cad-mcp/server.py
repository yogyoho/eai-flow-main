#!/usr/bin/env python3
"""text-to-cad MCP Server — standalone container.

Phase 1: backed by the vendored text-to-cad engine (cadpy + step/inspect CLIs,
MIT). Two tools:

- create_step(source, output_path, also_glb): write a build123d generator
  (def gen_step()) and run the vendored `step` CLI → STEP (+ topology-rich GLB
  when also_glb). The GLB carries the occurrence/face/edge topology that
  inspect_step's selector refs (#o1.2.f1) resolve against.
- inspect_step(step_path, subcommand, selectors, facts, detail): run the
  vendored `inspect` CLI (refs/measure/align/frame) on a STEP produced by
  create_step.

Engine contract: cadpy requires RELATIVE output paths and a workspace CWD, so
both tools resolve the agent's /mnt/user-data virtual path to a physical
thread dir, use it as the workdir, and pass relative names to the CLIs.

Heavy CAD deps (build123d + cadquery-ocp-novtk + cadpy) stay isolated here;
the gateway image is untouched. snapshot (Playwright+Chromium), step-parts,
and assemble are later phases.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP  # noqa: E402

# mcp 1.28: host/port/path are FastMCP() constructor kwargs; default host
# 127.0.0.1 must be overridden to 0.0.0.0 or the gateway can't reach us.
mcp = FastMCP(
    "text-to-cad",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8004")),
    streamable_http_path=os.getenv("MCP_PATH", "/mcp"),
)

# Vendored text-to-cad engine (MIT), installed under /app/cad-skill.
_STEP_CLI = "/app/cad-skill/step"
_INSPECT_CLI = "/app/cad-skill/inspect"
_STEP_TIMEOUT = 300  # complex parts / assemblies can take a while
_INSPECT_TIMEOUT = 120

_DEFAULT_DATA_ROOT = "/data"


def _resolve_output_path(file_path: str) -> Path | None:
    """Resolve an agent OUTPUT path to a real path in this container.

    Literal absolute path wins; otherwise a /mnt/user-data/<rest> virtual path
    is glob-searched under the data root (leaf = file, parent = searched).

    ponytail: glob assumes the thread dir for a given <rest> is unique. Upgrade
    path: carry thread_id via MCP context and resolve directly.
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


def _err(error: str, **extra) -> str:
    payload = {"status": "error", "error": error}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def create_step(source: str, output_path: str, also_glb: bool = False) -> str:
    """Generate a STEP (ISO 10303) from a build123d generator, via the text-to-cad engine.

    Writes your build123d source (which MUST define ``def gen_step():`` returning
    the final geometry) and runs the vendored ``step`` CLI. STEP is the primary
    artifact; the GLB (when ``also_glb``) is a topology-rich mesh whose
    occurrence/face/edge structure ``inspect_step``'s selector refs resolve
    against — and which the browser viewer renders.

    Units: millimeters. build123d is pre-imported in your source. Example::

        def gen_step():
            with BuildPart() as p:
                Box(100, 60, 20)
                with Locations(*[(42, 26, 0), (-42, 26, 0), (42, -26, 0), (-42, -26, 0)]):
                    Hole(4)
            return p.part

    Use for: natural-language CAD specs, brackets, enclosures, shafts, flanges.
    For inspecting an existing STEP (measure/refs), call ``inspect_step`` after.

    Args:
        source: build123d Python defining ``gen_step()`` returning a Part/Shape
            /Compound. For an assembly, return a Compound of labeled parts.
        output_path: .step destination — absolute path or
            /mnt/user-data/outputs/<name>.step virtual path. The generator is
            written next to it as <name>.py (same basename, upstream convention).
        also_glb: If True, also emit <name>.glb (topology-rich; needed before
            inspect_step refs, and for the browser viewer).

    Returns:
        JSON ``{status:"ok", step, glb?}`` on success, or
        ``{status:"error", error, detail?}`` (resolve_failed / bad_suffix /
        run_failed with the engine's stderr tail).
    """
    out = _resolve_output_path(output_path)
    if out is None:
        return _err("resolve_failed", output_path=output_path)
    if out.suffix.lower() not in (".step", ".stp"):
        return _err("bad_suffix", output_path=output_path, hint="output_path must end in .step or .stp")
    workdir = out.parent
    workdir.mkdir(parents=True, exist_ok=True)
    base = out.stem
    gen_py = workdir / f"{base}.py"
    gen_py.write_text(source, encoding="utf-8")

    # cadpy requires RELATIVE output paths + workspace CWD.
    cmd = ["python", _STEP_CLI, gen_py.name, "-o", out.name]
    if also_glb:
        cmd += ["--glb", f"{base}.glb"]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=_STEP_TIMEOUT)
    except subprocess.TimeoutExpired:
        return _err("run_failed", detail=f"step CLI timed out after {_STEP_TIMEOUT}s")
    if proc.returncode != 0:
        return _err("run_failed", detail=(proc.stderr or proc.stdout or "").strip()[-800:])

    info: dict = {"status": "ok", "step": output_path}
    glb_phys = workdir / f"{base}.glb"
    if also_glb:
        if glb_phys.exists():
            info["glb"] = output_path[: -len(out.suffix)] + ".glb"
        else:
            info["glb_error"] = "engine did not produce the GLB"
    return json.dumps(info, ensure_ascii=False, default=str)


@mcp.tool()
def inspect_step(step_path: str, subcommand: str, selectors: list[str] | None = None, facts: bool = False, detail: bool = False) -> str:
    """Inspect a STEP via the text-to-cad engine — refs / measure / align / frame.

    Runs the vendored ``inspect`` CLI on a STEP produced by ``create_step``.
    Selector refs (``#o1.2``, ``#o1.2.f1``) resolve against the topology-rich GLB
    that ``create_step(..., also_glb=True)`` emits — so generate with
    ``also_glb=True`` first when you need refs.

    Args:
        step_path: .step to inspect — absolute or /mnt/user-data/outputs/<name>.step.
        subcommand: one of ``refs`` (resolve refs + facts), ``measure`` (signed
            distance between two selectors), ``align`` (translation delta for
            alignment), ``frame`` (world frame of an occurrence). ``diff`` is
            two-file and not exposed here.
        selectors: selector tokens for the subcommand, e.g. ["#o1.2.f1"] for
            refs, ["#o1.2", "#o2.1"] for measure/align. Omit for a whole-entry
            refs dump.
        facts: refs only — include compact geometry facts (volume, bbox, ...).
        detail: refs only — include detailed face/edge facts for selected refs.

    Returns:
        The inspect CLI's JSON output (``--format json``), or
        ``{status:"error", error, detail?}`` (resolve_failed / not_found /
        run_failed).
    """
    valid = {"refs", "measure", "align", "frame"}
    if subcommand not in valid:
        return _err("bad_subcommand", subcommand=subcommand, valid=sorted(valid))
    out = _resolve_output_path(step_path)
    if out is None:
        return _err("resolve_failed", step_path=step_path)
    if not out.exists():
        return _err("not_found", step_path=step_path)
    workdir = out.parent
    cmd = ["python", _INSPECT_CLI, subcommand, out.name]
    if selectors:
        cmd += list(selectors)
    if subcommand == "refs":
        if facts:
            cmd.append("--facts")
        if detail:
            cmd.append("--detail")
    cmd += ["--format", "json"]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=_INSPECT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return _err("run_failed", detail=f"inspect CLI timed out after {_INSPECT_TIMEOUT}s")
    if proc.returncode != 0:
        return _err("run_failed", detail=(proc.stderr or proc.stdout or "").strip()[-800:])
    # inspect --format json prints JSON to stdout; pass through. Empty stdout = nothing matched.
    body = proc.stdout.strip()
    if not body:
        return _err("empty", detail="inspect produced no output (no matching refs?)")
    return body


def main() -> None:
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))


if __name__ == "__main__":
    main()
