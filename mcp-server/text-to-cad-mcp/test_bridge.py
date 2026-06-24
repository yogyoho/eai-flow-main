import json
import os
import sys

sys.path.insert(0, "/app")
from server import create_step  # noqa: E402

src = "from build123d import *\ndef gen_step():\n    return Cylinder(10, 20)\n"
r = json.loads(create_step(source=src, output_path="/tmp/bridge_test.step", also_glb=True))
print("status:", r.get("status"))
print("viewer_url:", r.get("viewer_url"))
print("public_glb:", r.get("public_glb"))
print("public_glb_error:", r.get("public_glb_error"))
p = "/data/public/bridge_test.glb"
print("/data/public/bridge_test.glb exists:", os.path.exists(p), "size:", os.path.getsize(p) if os.path.exists(p) else 0)
