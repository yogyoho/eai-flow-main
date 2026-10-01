"""终审执行驱动：按 final_execute_plan.json 逐批 invoke_batch。"""
import json, sys, time
from pathlib import Path
import urllib.request

TOK = sys.argv[1]
plan = json.loads(Path("scripts/eia_prereview_out/final_execute_plan.json").read_text(encoding="utf-8"))
url = "http://localhost:8005/api/extensions/ontology/actions/invoke_batch"
total_ok = total_fail = 0
t0 = time.time()
for bi, batch in enumerate(plan, 1):
    body = json.dumps(batch).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {TOK}", "Content-Type": "application/json",
        "Cookie": f"access_token={TOK}"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            d = json.loads(resp.read())
        ok = d.get("succeeded")
        if not isinstance(ok, int):
            ok = len(d.get("results", []) or [])
        fail = d.get("failed", 0)
        if not isinstance(fail, int):
            fail = len(fail) if isinstance(fail, list) else 0
        total_ok += ok; total_fail += fail
        print(f"batch {bi}/{len(plan)} [{batch['action_id'].split('.')[-1]}]: ok={ok} fail={fail}", flush=True)
    except Exception as e:
        print(f"batch {bi}: ERROR {str(e)[:120]}", flush=True)
print(f"DONE confirm+reject ok={total_ok} fail={total_fail} time={time.time()-t0:.0f}s", flush=True)
