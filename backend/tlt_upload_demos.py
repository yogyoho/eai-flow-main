"""Upload demo docs via the asset library API (temp)."""

import asyncio
import glob

import httpx


async def main():
    files = sorted(glob.glob("/tmp/tlt-testdocs/*.docx"))
    print("files:", [f.split("/")[-1] for f in files], flush=True)

    async with httpx.AsyncClient(base_url="http://localhost:8001", timeout=60) as c:
        r = await c.post(
            "/api/extensions/auth/login",
            json={"username": "admin@eai-flow.com", "password": "Admin@2026"},
        )
        r.raise_for_status()
        csrf = c.cookies.get("csrf_token") or ""
        h = {"X-CSRF-Token": csrf} if csrf else {}

        # 找合同文件夹
        r = await c.get("/api/extensions/translation/folders")
        fid = None
        for f in r.json()["items"]:
            if f["name"] == "合同":
                fid = f["id"]
                break

        data = {"folder_id": fid} if fid else {}
        upload_files = [("files", open(fp, "rb")) for fp in files]
        r = await c.post(
            "/api/extensions/translation/upload",
            files=upload_files,
            data=data,
            headers=h,
        )
        r.raise_for_status()
        for it in r.json()["items"]:
            print(f"  uploaded: {it['file']} | task: {it['task_id'][:8]} | reused: {it['reused']}", flush=True)

        # 逐个入队翻译（stored → pending）
        for fp in files:
            sha = __import__("hashlib").sha256(open(fp, "rb").read()).hexdigest()
            # 找 task id
            r2 = await c.get(
                "/api/extensions/translation/tasks",
                params={"folder_id": fid or "", "page_size": 100},
            )
            for it in r2.json()["items"]:
                if it["doc_sha"] == sha and it["state"] == "stored":
                    r3 = await c.post(
                        f"/api/extensions/translation/tasks/{it['id']}/transition",
                        json={"target": "pending"},
                        headers=h,
                    )
                    print(f"  queued: {it['file_name']} -> {r3.json().get('state')}", flush=True)
                    break


asyncio.run(main())
