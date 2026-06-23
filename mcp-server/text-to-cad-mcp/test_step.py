#!/usr/bin/env python3
"""Self-check for create_step: generate a Box, assert STEP + STL are produced.

No external fixture needed — builds the source inline. Run:

    python test_step.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server import create_step  # noqa: E402


def test_box_exports_step_and_stl(tmp_path: Path | None = None) -> None:
    out_dir = tmp_path or Path(tempfile.mkdtemp())
    out = out_dir / "box.step"
    src = "result = Box(100, 60, 20)"
    res = json.loads(create_step(source=src, output_path=str(out), also_stl=True))

    assert res["status"] == "ok", res
    assert out.exists() and out.stat().st_size > 0, "STEP not written"

    stl = out.with_suffix(".stl")
    assert stl.exists() and stl.stat().st_size > 0, "STL not written"

    size = res.get("bbox_mm", {}).get("size")
    assert size, f"missing bbox: {res}"
    assert abs(size[0] - 100) < 0.1 and abs(size[1] - 60) < 0.1 and abs(size[2] - 20) < 0.1, size

    print(f"OK: STEP {out.stat().st_size}B, STL {stl.stat().st_size}B, bbox_size={size}")


def test_missing_result_errors() -> None:
    out = Path(tempfile.mkdtemp()) / "bad.step"
    res = json.loads(create_step(source="x = 1", output_path=str(out)))
    assert res["status"] == "error" and res["error"] == "no_result", res
    print("OK: missing-result rejected")


if __name__ == "__main__":
    test_box_exports_step_and_stl()
    test_missing_result_errors()
    print("self-check passed")
