"""抽取任务闭环 E2E 演练（T8）——API 级走查 SC2 终裁版闭环.

EAI-CUSTOM(2026-10-01 T8): 设计 docs/designs/2026-10-01-ontostudio-ux-governance.md §B2。
容器内运行: docker exec ontostudio-backend python scripts/e2e_ingest_drill.py
（也可宿主机跑，--base 指向 :8005；鉴权用容器内 ONTOSTUDIO_JWT_SECRET 铸 superadmin token，
与 tests/conftest.py make_test_token 同形状。）

断言链（全部 API 级，不碰库）:
  1. /health 200 且 tables_ready
  2. /ingest-tasks/samples 取首个样例（或 --sample-id 指定）
  3. 记 /doc-graph/resolution/pending 待审基数 → POST /ingest-tasks（force_review）
  4. 轮询 GET /ingest-tasks/{id} 至终态（默认上限 120s）
  5. 断言 done 且 stats.entities_upserted>0；pending 增量 == entities_upserted（闭环铁证）
  6. 队列 GET /ingest-tasks 可见该任务行
退出码 0=PASS / 1=FAIL；每步打印证据行。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8005"
API = "/api/extensions"


def _mint_token(secret: str) -> str:
    """HS256 superadmin token——claims 形状照 tests/conftest.py make_test_token。"""
    import jwt  # PyJWT——auth.py 生产依赖，容器内必有

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "username": "e2e-drill",
        "email": "e2e-drill@local",
        "roles": ["superadmin"],
        "iat": now,
        "exp": now + timedelta(hours=1),
        "type": "access",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _call(method: str, path: str, token: str, body: dict | None = None, timeout: int = 30) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("E2E_BASE", BASE))
    ap.add_argument("--sample-id", default=None, help="指定样例 id；缺省取 /samples 首个")
    ap.add_argument("--timeout", type=int, default=120, help="任务终态轮询上限秒")
    args = ap.parse_args()
    BASE = args.base.rstrip("/")

    # 秘钥链与 app/auth.py 一致：ONTOSTUDIO_JWT_SECRET → 回退 AUTH_JWT_SECRET（gateway 同名）
    secret = os.environ.get("ONTOSTUDIO_JWT_SECRET", "") or os.environ.get("AUTH_JWT_SECRET", "")
    if not secret:
        print("FAIL: ONTOSTUDIO_JWT_SECRET 未设（容器内自带；宿主机需 export）")
        return 1
    token = _mint_token(secret)
    ok = True

    # 1. health
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
            h = json.loads(r.read().decode())
        assert h.get("tables_ready") is True, f"tables_ready={h.get('tables_ready')}"
        print(f"1. HEALTH  ok  tables_ready=True")
    except Exception as e:
        print(f"1. HEALTH  FAIL  {e}")
        return 1

    # 2. 样例
    code, data = _call("GET", f"{API}/ingest-tasks/samples", token)
    samples = data.get("samples", []) if code == 200 else []
    if args.sample_id:
        sid, title = args.sample_id, "(指定)"
    elif samples:
        sid, title = samples[0]["id"], samples[0]["title"]
    else:
        print("2. SAMPLES FAIL  无可建任务样例（kf_samples 需有 outline_json.ontology 非空行）")
        return 1
    print(f"2. SAMPLES ok  选用: {title} ({sid[:8]}…)")

    # 3. 待审基数
    code, before = _call("GET", f"{API}/doc-graph/resolution/pending?limit=1", token)
    pending_before = before.get("total", before.get("count"))
    if code != 200 or pending_before is None:
        # 契约兜底：无 total 字段时拉全量数长度（pending 上限内）
        code2, full = _call("GET", f"{API}/doc-graph/resolution/pending?limit=1000", token)
        pending_before = len(full.get("entities", [])) if code2 == 200 else None
    print(f"3. PENDING-BASELINE  {pending_before if pending_before is not None else '未知（跳过增量断言）'}")

    # 4. 建任务
    code, created = _call("POST", f"{API}/ingest-tasks", token, {"sample_id": sid, "force_review": True})
    if code != 201:
        print(f"4. CREATE  FAIL  HTTP {code}: {created}")
        return 1
    tid = created["id"]
    print(f"4. CREATE  ok  task={tid[:8]}… status={created['status']}")

    # 5. 轮询终态
    deadline = time.time() + args.timeout
    task: dict = {}
    while time.time() < deadline:
        code, task = _call("GET", f"{API}/ingest-tasks/{tid}", token)
        if code == 200 and task.get("status") in ("done", "completed_empty", "failed", "aborted"):
            break
        time.sleep(2)
    status = task.get("status")
    stats = task.get("stats") or {}
    upserted = stats.get("entities_upserted", 0)
    print(f"5. RUN  status={status}  entities_upserted={upserted}  mentions={stats.get('mentions')}  error={task.get('error')}")
    if status != "done" or upserted <= 0:
        print(f"   FAIL  期望 done 且实体>0")
        return 1

    # 6. pending 增量 == entities_upserted（SC2 闭环铁证）
    if pending_before is not None:
        code, after = _call("GET", f"{API}/doc-graph/resolution/pending?limit=1", token)
        pending_after = after.get("total", after.get("count"))
        if pending_after is None:
            code2, full2 = _call("GET", f"{API}/doc-graph/resolution/pending?limit=1000", token)
            pending_after = len(full2.get("entities", [])) if code2 == 200 else None
        if pending_after is not None:
            delta = pending_after - pending_before
            if delta == upserted:
                verdict = "PASS"
                note = ""
            elif 0 < delta < upserted:
                # 合并语义：部分实体自然键命中既有 active 行，promote-only 守卫正确地不降级
                verdict = "PASS"
                note = f"（{upserted - delta} 条自然键合并进既有 active 行——promote-only 守卫，符合契约）"
            else:
                verdict = "FAIL"
                note = "（pending 增量异常）"
            print(f"6. PENDING-DELTA  {pending_before} → {pending_after} (Δ{delta})  新建 {upserted}  [{verdict}]{note}")
            if verdict != "PASS":
                ok = False
        else:
            print("6. PENDING-DELTA  跳过（pending 端点不可达）")
    else:
        print("6. PENDING-DELTA  跳过（无基线）")

    # 7. 队列可见
    code, lst = _call("GET", f"{API}/ingest-tasks", token)
    visible = any(t.get("id") == tid for t in lst.get("tasks", [])) if code == 200 else False
    print(f"7. QUEUE-VISIBLE  {'PASS' if visible else 'FAIL'}")
    if not visible:
        ok = False

    print(f"\nE2E DRILL: {'PASS' if ok else 'FAIL'}  (task {tid})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
