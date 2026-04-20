"""Comprehensive diagnostic for login failure."""
import asyncio
import os
from pathlib import Path
import asyncpg
import bcrypt
import jwt
from dotenv import load_dotenv

_env = Path(__file__).parent / ".env"
load_dotenv(_env)

async def main():
    print("=" * 60)
    print("DIAGNOSTIC REPORT")
    print("=" * 60)

    # 1. Check env vars
    print("\n[1] Environment Variables:")
    db_host = os.getenv("EXTENSIONS_DB_HOST", "localhost")
    db_port = int(os.getenv("EXTENSIONS_DB_PORT", "5432"))
    db_user = os.getenv("EXTENSIONS_DB_USER", "eai_flow")
    db_pass = os.getenv("EXTENSIONS_DB_PASSWORD", "")
    db_name = os.getenv("EXTENSIONS_DB_NAME", "eai_extensions")
    jwt_secret = os.getenv("JWT_SECRET", "")
    print(f"  DB Host: {db_host}:{db_port}")
    print(f"  DB User: {db_user}")
    print(f"  DB Pass: {'***' if db_pass else '(empty)'}")
    print(f"  DB Name: {db_name}")
    print(f"  JWT Secret: {'***' if jwt_secret else '(empty)'}")

    # 2. Test database connections
    print("\n[2] Database Connection Tests:")

    test_configs = [
        (db_host, db_port, db_user, db_pass, db_name, f"{db_user}/{db_name}"),
        (db_host, db_port, db_user, db_pass, "agentflow", f"{db_user}/agentflow"),
        (db_host, db_port, "agentflow", db_pass, db_name, f"agentflow/{db_name}"),
        (db_host, db_port, "agentflow", db_pass, "agentflow", "agentflow/agentflow"),
        (db_host, db_port, "postgres", "postgres", db_name, "postgres/postgres"),
        (db_host, db_port, "postgres", "agentflow123", db_name, "postgres/agentflow123"),
    ]

    connected = False
    for host, port, user, pw, db, label in test_configs:
        try:
            conn = await asyncpg.connect(host=host, port=port, user=user, password=pw, database=db, timeout=5)
            print(f"  [{label}@{pw or 'nopw'}] -> CONNECTED")
            await conn.close()
            connected = True
        except Exception as e:
            print(f"  [{label}@{pw or 'nopw'}] -> {type(e).__name__}")

    if not connected:
        print("  All connection attempts failed!")
        return

    # 3. Query users table
    print("\n[3] Users Table (trying agentflow/agentflow):")
    conn = await asyncpg.connect(host=db_host, port=db_port, user="agentflow", password=db_pass, database="agentflow", timeout=5)
    try:
        users = await conn.fetch("SELECT id, username, email, status, role_id, password_hash FROM users")
        print(f"  Found {len(users)} user(s)")
        for u in users:
            print(f"  - {u['username']} ({u['email']}) status={u['status']} role={u['role_id']}")
            print(f"    hash: {u['password_hash'][:60]}...")
    except Exception as e:
        print(f"  Query failed: {type(e).__name__}: {e}")

    # 4. Test password verification
    print("\n[4] Password Verification:")
    import bcrypt
    for username in ['admin', 'test', 'user']:
        row = await conn.fetchrow("SELECT password_hash FROM users WHERE username=$1", username)
        if row:
            pw_hash = row['password_hash']
            for try_pw in ['admin123', 'password', 'test123', '123456', 'admin']:
                try:
                    ok = bcrypt.checkpw(try_pw.encode('utf-8'), pw_hash.encode('utf-8'))
                    if ok:
                        print(f"  {username}: MATCH with password '{try_pw}'")
                        break
                except Exception:
                    pass
            else:
                print(f"  {username}: hash={pw_hash[:40]}... (no common password matched)")

    # 5. JWT
    print("\n[5] JWT:")
    if jwt_secret:
        import time
        try:
            payload = {"sub": "test", "exp": int(time.time()) + 3600}
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")
            print(f"  JWT encode: OK")
        except Exception as e:
            print(f"  JWT error: {type(e).__name__}: {e}")
    else:
        print("  JWT_SECRET is empty! This will cause failures.")

    await conn.close()
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
