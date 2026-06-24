"""Verify the recursive-glob fix: pin at user-data/workspace/ (where the sandbox
actually puts /mnt/user-data/.cad_thread_pin) → create_step finds it + resolves
to the pinned thread."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from server import create_step  # noqa: E402

root = Path("/data")
for p in root.glob("users/*/threads/*/user-data/**/.cad_thread_pin"):
    p.unlink()

cands = sorted(root.glob("users/*/threads/*/user-data/outputs"))
target = cands[-1]  # non-first thread
# Sandbox writes /mnt/user-data/.cad_thread_pin → lands in user-data/workspace/
pin = target.parent / "workspace" / ".cad_thread_pin"
pin.parent.mkdir(parents=True, exist_ok=True)
pin.write_text("1")
print("pin at (sandbox location):", pin)

r = json.loads(create_step(
    source="from build123d import *\ndef gen_step():\n    return Box(10,10,5)\n",
    output_path="/mnt/user-data/outputs/pC.step",
    also_glb=True,
))
print("status:", r.get("status"), "| error:", r.get("error"), "| viewer_url:", r.get("viewer_url"))
print("STEP in PINNED thread (want True):", (target / "pC.step").exists())
print("STEP in glob-FIRST thread (want False):", (cands[0] / "pC.step").exists())
pin.unlink(missing_ok=True)
