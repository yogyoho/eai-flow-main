"""Verify the bridge end-to-end: run the REAL agent, check its reply has viewer_url.

Runs inside the gateway container (DeerFlowClient, internal auth, default user).
This is the actual agent flow the chat page wraps — if viewer_url is in the
response here, the page will show it too.
"""
import uuid

from deerflow.client import DeerFlowClient

c = DeerFlowClient()
tid = str(uuid.uuid4())
prompt = "用 text-to-cad 做一个 100x60x20mm 方块,顶部四角各一个 8mm 通孔,导出 STEP+GLB"
print("=== PROMPT ===", prompt, flush=True)
print("=== running agent (may take 30-90s) ===", flush=True)
resp = c.chat(prompt, thread_id=tid)
print("=== AGENT RESPONSE (full) ===", flush=True)
print(resp, flush=True)
print("=== VERDICT ===", flush=True)
hit = ("127.0.0.1:4178" in resp) or ("viewer_url" in resp.lower())
print("viewer_url present in agent reply:", hit, flush=True)
