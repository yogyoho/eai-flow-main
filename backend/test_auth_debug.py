import sys

sys.path.insert(0, r"D:\eai\eai-flow-main\backend")
from pathlib import Path  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(r"D:\eai\eai-flow-main\.env"), override=True)

import asyncio  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.extensions.auth.jwt import verify_token  # noqa: E402
from app.extensions.database import get_db_context  # noqa: E402
from app.extensions.models import Role, User  # noqa: E402

TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMTExMTExMS0xMTExLTExMTEtMTExMS0xMTExMTExMTExMTEiLCJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6InN1cGVyX2FkbWluIiwicGVybWlzc2lvbnMiOlsiKiJdLCJleHAiOjE3NzY2NTE2NTYsInR5cGUiOiJhY2Nlc3MifQ."
    "cF4tWbhnpB8ZmAbG0TxsmcGPBGjHsQ4B4_8LVCRvM7g"
)


async def test_auth():
    print(f"Token: {TOKEN[:50]}...")
    payload = verify_token(TOKEN, "access")
    if payload is None:
        print("FAIL: verify_token returned None")
        return
    print(f"Payload: sub={payload.sub}, username={payload.username}, role={payload.role}, permissions={payload.permissions}")

    async with get_db_context() as db:
        result = await db.execute(select(User).where(User.id == payload.sub))
        user = result.scalar_one_or_none()
        if user is None:
            print("FAIL: User not found in DB")
            result2 = await db.execute(select(User))
            users = result2.scalars().all()
            print(f"Total users in DB: {len(users)}")
            for u in users[:5]:
                print(f"  - id={u.id}, username={u.username}, role_id={u.role_id}, status={u.status}")
            return
        print(f"User: id={user.id}, username={user.username}, role_id={user.role_id}, status={user.status}")

        if user.role_id:
            result_role = await db.execute(select(Role).where(Role.id == user.role_id))
            role = result_role.scalar_one_or_none()
            if role:
                print(f"Role: id={role.id}, name={role.name}, code={role.code}, permissions={role.permissions}, is_system={role.is_system}")
            else:
                print("Role not found!")
        else:
            print("User has no role_id!")


if __name__ == "__main__":
    asyncio.run(test_auth())
