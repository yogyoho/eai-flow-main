"""Self-check for analyze_cad (parse-only; rasterize is too slow for a unit test).

Run:  CAD_FIXTURE=/path/to/x.dxf python test_analyze.py
Skips the real-fixture test gracefully when no fixture is provided, so this file
still runs clean in CI without the 2MB binary checked in.
"""
import json
import os
from server import analyze_cad

FIXTURE = os.environ.get("CAD_FIXTURE", "")


def test_rejects_non_dxf():
    out = json.loads(analyze_cad("foo.dwg"))
    assert out["status"] == "error" and out["error"] == "unsupported_format", out


def test_missing_file():
    out = json.loads(analyze_cad("does-not-exist.dxf"))
    assert out["status"] == "error", out


def test_virtual_path_resolution():
    """The agent passes /mnt/user-data/uploads/<name>; the tool must resolve it
    by glob-searching CAD_DATA_ROOT. We stage the fixture under a fake
    users/.../threads/.../user-data/uploads/ tree and point CAD_DATA_ROOT at it."""
    import os
    import tempfile
    from pathlib import Path

    if not FIXTURE or not os.path.exists(FIXTURE):
        print("skip test_virtual_path_resolution (set CAD_FIXTURE to enable)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        uploads = Path(tmp) / "users/u1/threads/t1/user-data/uploads"
        uploads.mkdir(parents=True)
        (uploads / "x.dxf").write_bytes(Path(FIXTURE).read_bytes())
        os.environ["CAD_DATA_ROOT"] = tmp
        try:
            out = json.loads(analyze_cad("/mnt/user-data/uploads/x.dxf"))
        finally:
            os.environ["CAD_DATA_ROOT"] = "/data"
        assert out["status"] == "ok", out
        print("OK: virtual path resolved ->", out["facts"]["entity_count"], "entities")


def test_real_dxf():
    if not FIXTURE or not os.path.exists(FIXTURE):
        print("skip test_real_dxf (set CAD_FIXTURE=/path/to/x.dxf to enable)")
        return
    out = json.loads(analyze_cad(FIXTURE))
    assert out["status"] == "ok", out
    f = out["facts"]
    assert f["entity_count"] > 1000, f
    assert any(d["size"].startswith("DN") for d in f["pipe_diameters"]), f
    assert len(f["layers"]) > 10, f
    print(
        f"OK: {f['entity_count']} entities, {len(f['layers'])} layers, "
        f"{len(f['pipe_diameters'])} pipe sizes, {len(f['hydrant_risers'])} risers"
    )


if __name__ == "__main__":
    test_rejects_non_dxf()
    test_missing_file()
    test_real_dxf()
    test_virtual_path_resolution()
    print("all self-checks passed")
