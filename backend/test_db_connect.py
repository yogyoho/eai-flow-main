import asyncio

import asyncpg


async def test(port, db, user, pw):
    try:
        conn = await asyncpg.connect(host="localhost", port=port, user=user, password=pw, database=db, timeout=5)
        r = await conn.fetchval("SELECT 1")
        print(f"OK  port={port} db={db} user={user} pw={pw}")

        # Check for users table
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('users','roles','departments')")
        for t in tables:
            print(f"  Table: {t['table_name']}")

        await conn.close()
        return True
    except Exception as e:
        print(f"FAIL port={port} db={db} user={user} pw={pw}: {type(e).__name__} - {e}")
        return False


async def main():
    # Try postgres superuser with agentflow123
    await test(5434, "agentflow", "postgres", "agentflow123")
    await test(5434, "postgres", "postgres", "agentflow123")

    # Try postgres superuser with common passwords
    for pw in ["postgres", "password", "123456", "agentflow", "admin"]:
        if await test(5434, "agentflow", "postgres", pw):
            break

    # Try eai_flow user with agentflow123 on agentflow database
    await test(5434, "agentflow", "eai_flow", "agentflow123")
    await test(5434, "eai_extensions", "eai_flow", "agentflow123")

    # Try without password (trust auth)
    try:
        conn = await asyncpg.connect(host="localhost", port=5434, user="eai_flow", database="agentflow", timeout=5)
        r = await conn.fetchval("SELECT 1")
        print("OK  port=5434 db=agentflow user=eai_flow (no password)")
        await conn.close()
    except Exception as e:
        print(f"FAIL no password: {type(e).__name__} - {e}")


asyncio.run(main())
