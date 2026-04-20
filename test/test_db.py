import asyncio
import asyncpg
import sys

async def test_db():
    print("=== Test Extensions DB Connection ===")
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5434,
            user='agentflow',
            password='agentflow123',
            database='agentflow',
            timeout=5
        )
        print("Connected successfully!")

        # Check if users table exists
        result = await conn.fetch("SELECT id, username, email, status FROM users WHERE username='admin'")
        print(f"Admin user query: {result}")

        # Check roles table
        roles = await conn.fetch("SELECT id, name, code, permissions, is_system, level, created_at FROM roles LIMIT 5")
        print(f"Roles: {roles}")

        await conn.close()
        print("Connection closed.")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test_db())
