"""Upload single demo file via API (temp)."""

import asyncio

import httpx


async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8001", timeout=60) as c:
        r = await c.post(
            "/api/extensions/auth/login",
            json={"username": "admin@eai-flow.com", "password": "Admin@2026"},
        )
        r.raise_for_status()
        csrf = c.cookies.get("csrf_token") or ""
        h = {"X-CSRF-Token": csrf} if csrf else {}

        fp = "/tmp/tlt-testdocs/HSE Safety Policy EN Rev3.docx"
        with open(fp, "rb") as f:
            r = await c.post(
                "/api/extensions/translation/upload",
                files=[
                    (
                        "files",
                        (
                            "Supply Agreement SA-2025-0412.docx",
                            f,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        ),
                    )
                ],
                headers=h,
            )
        print("STATUS:", r.status_code)
        print("BODY:", r.text[:300])


asyncio.run(main())
