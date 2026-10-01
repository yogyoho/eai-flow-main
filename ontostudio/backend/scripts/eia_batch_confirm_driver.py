"""分批确认驱动：读 batch_chunks.json，逐批 POST invoke_batch，进度实时输出。"""
import json, sys, time
from pathlib import Path
import urllib.request

TOK = sys.argv[1]
chunks = json.loads(Path("scripts/eia_prereview_out/batch_chunks.json").read_text(encoding="utf-8"))
url = "http://localhost:8005/api/extensions/ontology/actions/invoke_batch"
total_ok = total_fail = 0
t0 = time.time()
for bi, chunk in enumerate(chunks, 1):
    body = json.dumps({"action_id": "review_entity.confirm", "pks": chunk, "params": {}}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {TOK}", "Content-Type": "application/json",
        "Cookie": open("/tmp/oa_cookie.txt").read().strip().replace("\t", "=").replace("access_token=", "access_token=") if False else f"access_token={TOK}"})
    # Cookie 格式：access_token=<jwt>
    req.add_unredirected_header("Cookie", f"access_token={TOK}")
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
            print(f"batch {bi}/{len(chunks)}: ok={ok} fail={fail} elapsed={time.time()-t0:.0f}s", flush=True)
    except Exception as e:
        print(f"batch {bi}: ERROR {str(e)[:120]}", flush=True)
print(f"DONE ok={total_ok} fail={total_fail} total_time={time.time()-t0:.0f}s", flush=True)
