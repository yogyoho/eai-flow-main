#!/usr/bin/env python3
"""CAD Suite supervisor — run the three CAD services inside one container.

- text-to-cad MCP :8004 (env MCP_PORT from the image)
- cad / EDP MCP   :8003 (per-process MCP_PORT override — cad-mcp's server.py
                         reads MCP_PORT, same as the text-to-cad server)
- cad-viewer      :4178 (node, serves /data)

If ANY service exits, the remaining ones are terminated and the container
exits non-zero so docker's restart policy brings the whole suite back —
partial CAD capability is worse than none (skill texts cross-reference all
three).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

SERVICES = [
    {"name": "text-to-cad-mcp", "cmd": [sys.executable, "/app/server.py"], "cwd": "/app"},
    {
        "name": "cad-edp-mcp",
        "cmd": [sys.executable, "/app/cad-mcp/server.py"],
        "cwd": "/app/cad-mcp",
        "env": {**os.environ, "MCP_PORT": "8003"},
    },
    {
        "name": "cad-viewer",
        "cmd": ["node", "/app/viewer/backend/server.mjs", "--host", "0.0.0.0", "--port", "4178", "--dir", "/data"],
        "cwd": "/app/viewer",
    },
]


def main() -> int:
    procs = [
        subprocess.Popen(s["cmd"], cwd=s["cwd"], env=s.get("env", os.environ))
        for s in SERVICES
    ]

    def forward(signum, _frame):
        for p in procs:
            if p.poll() is None:
                p.terminate()

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)

    try:
        while True:
            time.sleep(5)
            for name, p in zip((s["name"] for s in SERVICES), procs):
                rc = p.poll()
                if rc is not None:
                    print(f"[cad-suite] {name} exited rc={rc}; terminating suite", flush=True)
                    forward(signal.SIGTERM, None)
                    for q in procs:
                        try:
                            q.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            q.kill()
                    return rc or 1
    except KeyboardInterrupt:
        forward(signal.SIGTERM, None)
        return 0


if __name__ == "__main__":
    sys.exit(main())
