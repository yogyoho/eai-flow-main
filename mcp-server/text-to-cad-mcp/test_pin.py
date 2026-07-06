"""Directly verify the thread-pin resolution (bug-324 fix), no LLM needed.

Writes a .cad_thread_pin into a NON-first thread's user-data/, calls create_step
with a virtual /mnt/user-data/outputs path, and confirms the STEP lands in the
PINNED thread — not the alphabetically-first one the bare glob would pick.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from server import create_step  # noqa: E402

root = Path("/data")
candidates = sorted(root.glob("users/*/threads/*/user-data/outputs"))
assert len(candidates) >= 2, "need >=2 threads to test pin vs glob-first"
# Pick a thread that is NOT the glob-first (index 0) — use the LAST one.
target = candidates[-1]
pin = target.parent / ".cad_thread_pin"
pin.write_text("pin-test")
print("pin written ->", pin)
print("pinned thread outputs:", target)
print("glob-FIRST thread (bare glob would pick this):", candidates[0])

res = json.loads(create_step(
    source="from build123d import *\ndef gen_step():\n    return Box(10,10,5)\n",
    output_path="/mnt/user-data/outputs/pintest.step",
    also_glb=True,
))
print("create_step status:", res.get("status"), "| viewer_url:", res.get("viewer_url"))

pinned_step = target / "pintest.step"
first_step = candidates[0] / "pintest.step"
print("STEP in PINNED thread (want True):", pinned_step.exists(), "->", pinned_step)
print("STEP in glob-FIRST thread (want False):", first_step.exists())
pin.unlink(missing_ok=True)
