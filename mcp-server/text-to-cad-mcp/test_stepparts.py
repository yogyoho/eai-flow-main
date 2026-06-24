#!/usr/bin/env python3
"""Self-check for search_step_parts (search + download). Run inside container."""
import json
import os
import sys

sys.path.insert(0, "/app")
from server import search_step_parts  # noqa: E402

# search
res = search_step_parts(query="M3 socket head screw", limit=3)
data = json.loads(res)
items = data.get("items", [])
assert items, f"no items / api unreachable: {res[:200]}"
pid = items[0]["id"]
print(f"OK search: {len(items)} items; first id={pid} name={items[0]['name']}")

# download
dl = json.loads(search_step_parts(download_id=pid, output_path="/tmp/dl.step"))
assert dl["status"] == "ok", f"download failed: {dl}"
assert os.path.exists("/tmp/dl.step") and os.path.getsize("/tmp/dl.step") > 0, "STEP not saved"
print(f"OK download: /tmp/dl.step {os.path.getsize('/tmp/dl.step')} bytes")
print("SELF_CHECK_OK")
