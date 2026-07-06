"""Verify pin enforcement: no-pin → no_thread_pin error; with-pin → correct thread."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from server import create_step  # noqa: E402

root = Path("/data")
src = "from build123d import *\ndef gen_step():\n    return Box(10,10,5)\n"

# Case A: NO pin → expect no_thread_pin error (forces agent to write pin)
for p in root.glob("users/*/threads/*/user-data/.cad_thread_pin"):
    p.unlink()
rA = json.loads(create_step(source=src, output_path="/mnt/user-data/outputs/pA.step", also_glb=True))
print("Case A (no pin): status=", rA.get("status"), "| error=", rA.get("error"))

# Case B: WITH pin → STEP in the PINNED thread, not glob-first
cands = sorted(root.glob("users/*/threads/*/user-data/outputs"))
target = cands[-1]
(target.parent / ".cad_thread_pin").write_text("pin")
rB = json.loads(create_step(source=src, output_path="/mnt/user-data/outputs/pB.step", also_glb=True))
print("Case B (pin):    status=", rB.get("status"), "| STEP in pinned:", (target / "pB.step").exists(), "| in glob-first:", (cands[0] / "pB.step").exists())
(target.parent / ".cad_thread_pin").unlink(missing_ok=True)
