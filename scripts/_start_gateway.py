import os
import sys

os.chdir(r"D:\eai\eai-flow-main\backend")
os.environ["PYTHONPATH"] = "."
sys.path.insert(0, r"D:\eai\eai-flow-main\backend")

import uvicorn
uvicorn.run("app.gateway.app:app", host="0.0.0.0", port=4001)
