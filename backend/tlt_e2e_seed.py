"""Upload all 4 demo docs + queue stored → pending + poll to terminal (temp)."""

import asyncio
import glob
import hashlib
import os
import urllib.request

import httpx

BASE = "http://localhost:8001"


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as c:
        r = await c.post(
            f"{BASE}/api/extensions/auth/login",
            json={"username": "admin@eai-flow.com", "password": "Admin@2026"},
        )
        r.raise_for_status()
        csrf = c.cookies.get("csrf_token") or ""
        h = {"X-CSRF-Token": csrf} if csrf else {}

        # 上传 4 份演示文档到合同文件夹
        r = await c.get(f"{BASE}/api/extensions/translation/folders")
        folders = {f["name"]: f["id"] for f in r.json()["items"]}
        fid = folders.get("合同")

        docs = sorted(glob.glob("/tmp/tlt-testdocs/*.docx"))
        for fp in docs:
            fname = os.path.basename(fp)
            content = open(fp, "rb").read()
            sha = hashlib.sha256(content).hexdigest()

            # 检查是否已存在
            r = await c.get(
                f"{BASE}/api/extensions/translation/tasks",
                params={"page_size": 100},
            )
            exists = any(
                t["doc_sha"] == sha and t["state"] not in ("archived", "cancelled", "superseded")
                for t in r.json()["items"]
            )
            if exists:
                print(f"  skip (exists): {fname}", flush=True)
                continue

            r = await c.post(
                f"{BASE}/api/extensions/translation/upload",
                files=[("files", (fname, content, "application/octet-stream"))],
                data={"folder_id": fid} if fid else {},
                headers=h,
            )
            r.raise_for_status()
            print(f"  uploaded: {fname}", flush=True)

        # 入队所有 stored 任务
        r = await c.get(
            f"{BASE}/api/extensions/translation/tasks",
            params={"page_size": 100},
        )
        stored = [t for t in r.json()["items"] if t["state"] == "stored"]
        print(f"queued: {len(stored)} stored tasks", flush=True)
        for t in stored:
            r = await c.post(
                f"{BASE}/api/extensions/translation/tasks/{t['id']}/transition",
                json={"target": "pending"},
                headers=h,
            )
            r.raise_for_status()
            print(f"  → pending: {t['file_name']}", flush=True)

        # 轮询到终态
        for _ in range(60):
            await asyncio.sleep(5)
            r = await c.get(
                f"{BASE}/api/extensions/translation/tasks",
                params={"page_size": 100},
            )
            items = r.json()["items"]
            active = [t for t in items if t["state"] in ("pending", "running", "check_failed", "retrying", "indexed")]
            if not active:
                break
            for t in active:
                print(f"  ... {t['file_name']}: {t['state']} {t['progress']}%", flush=True)

        print("\n=== FINAL STATES ===", flush=True)
        r = await c.get(
            f"{BASE}/api/extensions/translation/tasks",
            params={"page_size": 100},
        )
        for t in r.json()["items"]:
            if t["state"] not in ("archived", "cancelled", "superseded"):
                deliv = "✓" if t["deliverable_uri"] else "✗"
                print(f"  {t['file_name']}: {t['state']} | deliv: {deliv}", flush=True)


asyncio.run(main())
