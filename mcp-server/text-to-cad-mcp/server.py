#!/usr/bin/env python3
"""text-to-cad MCP Server — standalone container.

Backed by the vendored text-to-cad engine (cadpy + step/inspect/snapshot/dxf
CLIs, MIT). Five tools:

- create_step(source, output_path, also_glb, also_stl): write a build123d
  generator (def gen_step()) and run the vendored `step` CLI → STEP (+
  topology-rich GLB when also_glb, + STL mesh when also_stl). The GLB carries
  the occurrence/face/edge topology that inspect_step's selector refs
  (#o1.2.f1) resolve against.
- inspect_step(step_path, subcommand, selectors, facts, detail): run the
  vendored `inspect` CLI (refs/measure/align/frame) on a STEP produced by
  create_step.
- snapshot_step(step_path, output_path, ...): render a STEP to PNG via the
  vendored `snapshot` CLI (Playwright + headless Chromium) for the agent's
  visual self-check.
- create_dxf(source, output_path): write a build123d generator (def gen_dxf())
  and run the vendored `dxf` CLI → 2D DXF drawing. (Generic mechanical DXF;
  domain-specific 2D engineering drawings live on the separate `cad` EDP
  server via cad_compose_drawing.)
- check_printability(mesh_path, process): run the vendored dfam_tool (trimesh
  ray-cast) → watertightness / wall thickness / overhang facts vs DfAM limits.

Engine contract: cadpy requires RELATIVE output paths and a workspace CWD, so
the tools resolve the agent's /mnt/user-data virtual path to a physical
thread dir, use it as the workdir, and pass relative names to the CLIs.

Heavy CAD deps (build123d + cadquery-ocp-novtk + cadpy) stay isolated here;
the gateway image is untouched. Runs inside the merged cad-suite image
alongside the cad (EDP :8003) and cad-viewer (:4178) services.
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
_SNAPSHOT_CLI = "/app/cad-skill/snapshot"
_DXF_CLI = "/app/cad-skill/dxf"
_DFAM_CLI = "/app/dfam/dfam_tool.py"
_STEPPARTS_CLI = "/app/step-parts/download_step_part.py"
_STEP_TIMEOUT = 300  # complex parts / assemblies can take a while
_INSPECT_TIMEOUT = 120
_SNAPSHOT_TIMEOUT = 360  # CLI default 300s + first-call OCP GLB regeneration & browser startup
_DXF_TIMEOUT = 180
_DFAM_TIMEOUT = 180
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


_PIN_HINT = (
    "先 write_file('/mnt/user-data/.cad_thread_pin','1') 钉定当前线程,再重试。"
    "原因:此工具跨线程共享、看不见 thread_id,不钉定→文件落错线程→下载404。"
)


def _ensure_thread_pin() -> str | None:
    """Return an error payload if no thread pin exists, else None (bug-324)."""
    root = Path(os.getenv("CAD_DATA_ROOT", _DEFAULT_DATA_ROOT))
    if not any(root.glob("users/*/threads/*/user-data/**/.cad_thread_pin")):
        return _err("no_thread_pin", hint=_PIN_HINT)
    return None


@mcp.tool()
def create_step(source: str, output_path: str, also_glb: bool = False, also_stl: bool = False) -> str:
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
        also_stl: If True, also emit <name>.stl (plain triangle mesh; the input
            format for ``check_printability`` and 3D-print slicers).

    Returns:
        JSON ``{status:"ok", step, glb?, public_glb?, viewer_url?, stl?}`` on success.
        When ``also_glb=True``, includes ``viewer_url`` — a clickable CAD Viewer
        3D preview link (e.g. ``http://127.0.0.1:4178/?dir=/data&file=public/<name>.glb``).
        **You MUST surface this ``viewer_url`` to the user in your final reply** (as a
        clickable/bold link) — it is the deliverable's live 3D preview; do not omit it.
        On failure: ``{status:"error", error, detail?}`` (no_thread_pin / resolve_failed /
        bad_suffix / run_failed with the engine's stderr tail).
    """
    # Force thread pin (bug-324): this container can't see thread_id; without a
    # pin the fallback glob writes to the wrong thread → download 404.
    pin_err = _ensure_thread_pin()
    if pin_err:
        return pin_err
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
    if also_stl:
        cmd += ["--stl", f"{base}.stl"]
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
    if also_stl:
        if (workdir / f"{base}.stl").exists():
            info["stl"] = output_path[: -len(out.suffix)] + ".stl"
        else:
            info["stl_error"] = "engine did not produce the STL"
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


@mcp.tool()
def snapshot_step(step_path: str, output_path: str, camera: str = "iso", width: int | None = None, height: int | None = None) -> str:
    """**PREREQUISITE — same as create_step:** the ``.cad_thread_pin`` must exist (write it once per thread).

    Render a STEP to a PNG snapshot so you can visually self-check your own CAD
    output (agent-side eyes — deterministic ``inspect_step`` cannot see shape
    pathology like an open shell rendered wrong). The browser viewer_url stays
    the human's interactive preview; this PNG is yours.

    Runs the vendored ``snapshot`` CLI (Playwright + headless Chromium, fully
    offline render). Output filename gets a UTC timestamp appended — use the
    returned ``snapshot`` path, not the path you passed.

    Args:
        step_path: STEP to render (must be a real .step; GLB is rejected) —
            absolute or /mnt/user-data/outputs/<name>.step virtual path.
        output_path: PNG destination (.png) — virtual path convention as above.
        camera: view preset, e.g. "iso" (default) / "front" / "top" / "iso-opposite".
        width: render width in px (default engine-chosen).
        height: render height in px.

    Returns:
        JSON ``{status:"ok", snapshot, step}`` where ``snapshot`` is the actual
        timestamped PNG path, or ``{status:"error", error, detail?}``
        (no_thread_pin / resolve_failed / bad_suffix / render_failed).
    """
    pin_err = _ensure_thread_pin()
    if pin_err:
        return pin_err
    src = _resolve_output_path(step_path)
    png = _resolve_output_path(output_path)
    if src is None or png is None:
        return _err("resolve_failed", step_path=step_path, output_path=output_path)
    if src.suffix.lower() not in (".step", ".stp"):
        return _err("bad_suffix", step_path=step_path, hint="snapshot renders a .step/.stp input")
    if png.suffix.lower() != ".png":
        return _err("bad_suffix", output_path=output_path, hint="output_path must end in .png")
    workdir = src.parent
    png.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["python", _SNAPSHOT_CLI, "--input", src.name, "--output", png.name,
           "--mode", "view", "--camera", camera]
    if width:
        cmd += ["--width", str(width)]
    if height:
        cmd += ["--height", str(height)]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=_SNAPSHOT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return _err("render_failed", detail=f"snapshot CLI timed out after {_SNAPSHOT_TIMEOUT}s")
    if proc.returncode != 0:
        return _err("render_failed", detail=(proc.stderr or proc.stdout or "").strip()[-800:])
    # The CLI appends a UTC timestamp to the output stem; report the real file.
    produced = sorted(workdir.glob(f"{png.stem}_*.png"), key=lambda p: p.stat().st_mtime)
    if not produced:
        produced = [png] if png.exists() else []
    if not produced:
        return _err("render_failed", detail="snapshot CLI reported success but no PNG found")
    # Report as the agent's virtual path so present_files/download resolve.
    rest = produced[-1].relative_to(_thread_user_data_root(workdir))
    return json.dumps({"status": "ok", "snapshot": f"/mnt/user-data/{rest}", "step": step_path},
                      ensure_ascii=False)


def _thread_user_data_root(physical: Path) -> Path:
    """Walk a physical thread path up to its user-data/ root (pin convention)."""
    ud = physical
    while ud.name != "user-data" and ud != ud.parent:
        ud = ud.parent
    return ud


@mcp.tool()
def create_dxf(source: str, output_path: str) -> str:
    """**PREREQUISITE — same as create_step:** the ``.cad_thread_pin`` must exist (write it once per thread).

    Generate a 2D DXF drawing via the text-to-cad engine. Your source MUST
    define ``def gen_dxf():`` returning an **ezdxf Document** (NOT build123d
    geometry — Sketch/BuildSketch objects are not valid here). Use for generic
    mechanical flat patterns and plate outlines. For domain-specific 2D
    ENGINEERING drawings (mine / chemical-plant layouts with title blocks),
    do NOT use this — call ``cad_compose_drawing`` on the ``cad`` server
    instead.

    Source template (ezdxf is pre-importable in the container)::

        import ezdxf

        def gen_dxf():
            doc = ezdxf.new("R2010")
            doc.units = ezdxf.units.MM
            msp = doc.modelspace()
            msp.add_lwpolyline([(0, 0), (60, 0), (60, 40), (0, 40)], close=True)
            return doc

    Args:
        source: Python defining ``gen_dxf()`` returning an ezdxf Document —
            pass the source STRING itself, never a file path.
        output_path: .dxf destination — absolute or /mnt/user-data/outputs/<name>.dxf
            virtual path. The generator is written next to it as <name>.py.

    Returns:
        JSON ``{status:"ok", dxf}`` or ``{status:"error", error, detail?}``
        (no_thread_pin / resolve_failed / bad_suffix / run_failed).
    """
    pin_err = _ensure_thread_pin()
    if pin_err:
        return pin_err
    # Trust-boundary guard (E2E T6): agents sometimes pass a PATH here instead
    # of the source string — a path is one line ending in .py and would be
    # written out as a garbage "generator". Fail fast with the fix in the hint.
    if source.strip().endswith(".py") and "\n" not in source.strip():
        return _err("bad_args", hint="source 参数传 gen_dxf() 源码字符串本身,不是文件路径——把完整 Python 源码内联传入。")
    out = _resolve_output_path(output_path)
    if out is None:
        return _err("resolve_failed", output_path=output_path)
    if out.suffix.lower() != ".dxf":
        return _err("bad_suffix", output_path=output_path, hint="output_path must end in .dxf")
    workdir = out.parent
    workdir.mkdir(parents=True, exist_ok=True)
    gen_py = workdir / f"{out.stem}.py"
    gen_py.write_text(source, encoding="utf-8")
    # cadpy requires RELATIVE paths + workspace CWD (same contract as step).
    cmd = ["python", _DXF_CLI, gen_py.name, "-o", out.name]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=_DXF_TIMEOUT)
    except subprocess.TimeoutExpired:
        return _err("run_failed", detail=f"dxf CLI timed out after {_DXF_TIMEOUT}s")
    if proc.returncode != 0:
        return _err("run_failed", detail=(proc.stderr or proc.stdout or "").strip()[-800:])
    if not out.exists():
        return _err("run_failed", detail="dxf CLI reported success but no DXF found")
    return json.dumps({"status": "ok", "dxf": output_path}, ensure_ascii=False)


@mcp.tool()
def check_printability(mesh_path: str, angle_limit: float | None = None) -> str:
    """**PREREQUISITE — same as create_step:** the ``.cad_thread_pin`` must exist (write it once per thread).

    DfAM printability facts for a mesh: watertightness, per-body wall thickness
    (ray cast), overhang/support area with angle histogram, and support-volume
    estimate. Fact-only output — compare the numbers against your process's
    limits yourself (FDM/SLS/SLA/PBF/MJF) and report honestly (hole diameters /
    positive features / bridges are NOT measured; the tool never passes/fails).

    Typical flow: ``create_step(..., also_stl=True)`` first, then pass the
    returned ``stl`` path here.

    Args:
        mesh_path: STL file — absolute or /mnt/user-data/outputs/<name>.stl.
        angle_limit: overhang threshold in degrees (default 45).

    Returns:
        The dfam tool's JSON facts, or ``{status:"error", error, detail?}``.
    """
    pin_err = _ensure_thread_pin()
    if pin_err:
        return pin_err
    mesh = _resolve_output_path(mesh_path)
    if mesh is None:
        return _err("resolve_failed", mesh_path=mesh_path)
    if not mesh.exists():
        return _err("not_found", mesh_path=mesh_path)
    if mesh.suffix.lower() != ".stl":
        return _err("bad_suffix", mesh_path=mesh_path, hint="STL is the only supported input here")
    cmd = ["python", _DFAM_CLI, "measure", mesh.name]
    if angle_limit is not None:
        cmd += ["--angle-limit", str(angle_limit)]
    try:
        proc = subprocess.run(cmd, cwd=mesh.parent, capture_output=True, text=True, timeout=_DFAM_TIMEOUT)
    except subprocess.TimeoutExpired:
        return _err("run_failed", detail=f"dfam tool timed out after {_DFAM_TIMEOUT}s")
    if proc.returncode != 0:
        return _err("run_failed", detail=(proc.stderr or proc.stdout or "").strip()[-800:])
    body = proc.stdout.strip()
    if not body:
        return _err("empty", detail="dfam tool produced no output")
    return body


def main() -> None:
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))


if __name__ == "__main__":
    main()
