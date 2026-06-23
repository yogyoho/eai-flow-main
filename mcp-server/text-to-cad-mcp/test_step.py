#!/usr/bin/env python3
"""Self-check for create_step + inspect_step (vendored engine, gen_step convention).

Run: python test_step.py  (inside the container)
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server import create_step, inspect_step  # noqa: E402


def test_create_and_inspect() -> None:
    out_dir = Path(tempfile.mkdtemp())
    step_path = str(out_dir / "box.step")
    src = "from build123d import *\ndef gen_step():\n    return Box(100, 60, 20)\n"

    res = json.loads(create_step(source=src, output_path=step_path, also_glb=True))
    assert res["status"] == "ok", res
    assert (out_dir / "box.step").exists() and (out_dir / "box.step").stat().st_size > 0, "STEP not written"
    assert (out_dir / "box.glb").exists() and (out_dir / "box.glb").stat().st_size > 0, "GLB not written"
    print(f"OK create_step: STEP+GLB produced (glb={res.get('glb')})")

    # inspect_step refs on the produced STEP (refs resolve against box.glb topology)
    insp = inspect_step(step_path=step_path, subcommand="refs", facts=True)
    assert '"status": "error"' not in insp and '"status":"error"' not in insp, f"inspect failed: {insp[:300]}"
    try:
        idata = json.loads(insp)
        print(f"OK inspect_step refs: parsed JSON, type={type(idata).__name__}")
    except json.JSONDecodeError:
        print(f"OK inspect_step refs (non-JSON, first 120): {insp[:120]}")


def test_missing_gen_step_errors() -> None:
    out = str(Path(tempfile.mkdtemp()) / "bad.step")
    res = json.loads(create_step(source="x = 1", output_path=out))
    assert res["status"] == "error", res
    print(f"OK missing-gen_step rejected: {res['error']}")


if __name__ == "__main__":
    test_create_and_inspect()
    test_missing_gen_step_errors()
    print("self-check passed")
