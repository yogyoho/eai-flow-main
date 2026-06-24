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

import hashlib
import json
import os
import re
import shutil
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
_STEPPARTS_CLI = "/app/step-parts/download_step_part.py"
_STEP_TIMEOUT = 300  # complex parts / assemblies can take a while
_INSPECT_TIMEOUT = 120
_STEPPARTS_TIMEOUT = 120
# cad-viewer base URL (the agent hands this to the user's browser). Override via
# CAD_VIEWER_URL if served behind a different host/nginx path.
_VIEWER_BASE = os.getenv("CAD_VIEWER_URL", "http://127.0.0.1:4178")

_DEFAULT_DATA_ROOT = "/data"


def _resolve_output_path(file_path: str) -> Path | None:
    """Resolve an agent OUTPUT path to a real path in this container.

    Virtual /mnt/user-data/<rest> paths resolve to the CURRENT thread's dir,
    identified by the newest ``.cad_thread_pin`` (the skill's sandbox writes it
    just before calling this tool). The MCP container is shared across threads
    and can't see thread_id, so the pin (newest mtime) is the bridge (bug-324);
    a bare glob would land on the alphabetically-first thread, not the current
    one, orphaning the file. Virtual check BEFORE is_absolute
    (/mnt/user-data/... is absolute on Linux).

    Upgrade path: per-call thread_id via MCP context (needs harness support).
    """
    if "/mnt/user-data/" in file_path:
        rest = file_path.split("/mnt/user-data/", 1)[1].lstrip("/")
        root = Path(os.getenv("CAD_DATA_ROOT", _DEFAULT_DATA_ROOT))
        # Current thread = newest .cad_thread_pin under any user-data/ dir.
        pins = sorted(
            root.glob("users/*/threads/*/user-data/**/.cad_thread_pin"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if pins:
            # The pin may sit under user-data/ directly or in a subdir (the
            # sandbox puts /mnt/user-data/<file> into user-data/workspace/).
            # Walk up to the user-data/ root, then resolve <rest> under it.
            ud = pins[0]
            while ud.name != "user-data":
                ud = ud.parent
            return ud / rest
        # Fallback (no pin yet): glob parent — may pick the wrong thread.
        parts = rest.split("/")
        leaf = parts[-1]
        parent_rest = "/".join(parts[:-1])
        glob_pat = f"users/*/threads/*/user-data/{parent_rest}" if parent_rest else "users/*/threads/*/user-data"
        matches = sorted(root.glob(glob_pat))
        return (matches[0] / leaf) if matches else None
    p = Path(file_path)
    return p if p.is_absolute() else None


def _err(error: str, **extra) -> str:
    payload = {"status": "error", "error": error}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def create_step(source: str, output_path: str, also_glb: bool = False) -> str:
    """**PREREQUISITE — do this FIRST, every call:** ``write_file('/mnt/user-data/.cad_thread_pin', '1')``.
    This tool runs in a container shared across threads and CANNOT see your
    ``thread_id``; without the pin, your STEP/GLB land in the wrong thread and the
    user's download 404s. If you get ``no_thread_pin``, write the pin then retry.

    Generate a STEP (ISO 10303) from a build123d generator, via the text-to-cad engine.

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
        JSON ``{status:"ok", step, glb?, public_glb?, viewer_url?}`` on success.
        When ``also_glb=True``, includes ``viewer_url`` — a clickable CAD Viewer
        3D preview link (e.g. ``http://127.0.0.1:4178/?dir=/data&file=public/<name>.glb``).
        **You MUST surface this ``viewer_url`` to the user in your final reply** (as a
        clickable/bold link) — it is the deliverable's live 3D preview; do not omit it.
        On failure: ``{status:"error", error, detail?}`` (no_thread_pin / resolve_failed /
        bad_suffix / run_failed with the engine's stderr tail).
    """
    # Force thread pin (bug-324): this container can't see thread_id; without a
    # pin the fallback glob writes to the wrong thread → download 404.
    root = Path(os.getenv("CAD_DATA_ROOT", _DEFAULT_DATA_ROOT))
    if not any(root.glob("users/*/threads/*/user-data/**/.cad_thread_pin")):
        return _err("no_thread_pin", hint="先 write_file('/mnt/user-data/.cad_thread_pin','1') 钉定当前线程,再重试 create_step。原因:此工具跨线程共享、看不见 thread_id,不钉定→文件落错线程→下载404。")
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
            # Bridge to cad-viewer (4178): also drop a copy in the flat /data/public/
            # dir so the agent can hand the user a simple viewer URL (avoids the deep
            # users/<uid>/threads/<tid>/... path that the agent can't see).
            try:
                public_dir = Path(os.getenv("CAD_DATA_ROOT", _DEFAULT_DATA_ROOT)) / "public"
                public_dir.mkdir(parents=True, exist_ok=True)
                # ASCII-safe public name (Chinese/special chars break the viewer URL)
                safe = re.sub(r"[^A-Za-z0-9._-]", "", base)
                if len(safe) < 3:
                    safe = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
                public_name = f"{safe}.glb"
                shutil.copy(str(glb_phys), str(public_dir / public_name))
                info["public_glb"] = f"public/{public_name}"
                info["viewer_url"] = f"{_VIEWER_BASE}/?dir=/data&file=public/{public_name}"
            except Exception as exc:
                info["public_glb_error"] = repr(exc)
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


@mcp.tool()
def search_step_parts(query: str = "", limit: int = 8, download_id: str | None = None, output_path: str | None = None, standard: str | None = None) -> str:
    """Search the step.parts hosted catalog for standard parts (screws/bolts/bearings/motors/connectors), or download one part's STEP.

    Two modes:
    - **Search** (no ``download_id``): fuzzy ``query`` (e.g. "M3 socket head 12") → returns the
      catalog JSON ``{catalog, items:[{id, name, standard, attributes, stepUrl, pageUrl}, ...]}``.
      Use a returned ``id`` to download. ``standard`` filters e.g. "ISO 4762".
    - **Download** (``download_id`` set): fetches that part's canonical STEP to ``output_path``.
      Returns ``{status, step, id}``.

    Network: reaches api.step.parts (catalog) + media.githubusercontent.com (STEP files). If
    unreachable, returns run_failed. Use for assemblies referencing real off-the-shelf parts; the
    downloaded STEP can be imported into an assembly source.

    Args:
        query: fuzzy search across id/name/category/standard/attributes. Required for search.
        limit: search page size (1-500, default 8).
        download_id: part id from a search result → download mode.
        output_path: download destination (.step) — required with download_id. Absolute or
            /mnt/user-data/outputs/<name>.step virtual path.
        standard: optional filter, e.g. "ISO 4762".

    Returns:
        Search: the catalog JSON. Download: ``{status:"ok", step, id}`` or
        ``{status:"error", error, detail?}`` (bad_args/resolve_failed/bad_suffix/run_failed/empty).
    """
    if download_id:
        if not output_path:
            return _err("bad_args", hint="download_id requires output_path")
        out = _resolve_output_path(output_path)
        if out is None:
            return _err("resolve_failed", output_path=output_path)
        if out.suffix.lower() not in (".step", ".stp"):
            return _err("bad_suffix", output_path=output_path, hint="output_path must end in .step or .stp")
        workdir = out.parent
        workdir.mkdir(parents=True, exist_ok=True)
        cmd = ["python", _STEPPARTS_CLI, "--id", download_id, "--download",
               "--out-dir", str(workdir), "--filename", out.name, "--overwrite"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_STEPPARTS_TIMEOUT)
        except subprocess.TimeoutExpired:
            return _err("run_failed", detail=f"download timed out after {_STEPPARTS_TIMEOUT}s")
        if proc.returncode != 0:
            return _err("run_failed", detail=(proc.stderr or proc.stdout or "").strip()[-800:])
        return json.dumps({"status": "ok", "step": output_path, "id": download_id}, ensure_ascii=False)

    # search mode
    if not query:
        return _err("bad_args", hint="provide a query (search) or download_id (download)")
    cmd = ["python", _STEPPARTS_CLI, query, "--limit", str(max(1, min(limit, 500)))]
    if standard:
        cmd += ["--standard", standard]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_STEPPARTS_TIMEOUT)
    except subprocess.TimeoutExpired:
        return _err("run_failed", detail=f"search timed out after {_STEPPARTS_TIMEOUT}s")
    if proc.returncode != 0:
        return _err("run_failed", detail=(proc.stderr or proc.stdout or "").strip()[-800:])
    body = proc.stdout.strip()
    if not body:
        return _err("empty", detail="no results (API unreachable or no matches)")
    return body


def main() -> None:
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))


if __name__ == "__main__":
    main()
