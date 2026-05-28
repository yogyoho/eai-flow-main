"""End-to-end test for the sync flow.

Tests whether Gateway provider is accessible and sync functions work,
without needing the full server stack.
"""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")

async def main():
    # ── Step 1: Initialize Gateway SQLite engine ──
    print("=" * 60)
    print("Step 1: Initialize Gateway SQLite engine")
    from deerflow.config.database_config import DatabaseConfig
    from deerflow.persistence.engine import init_engine_from_config, get_session_factory

    config = DatabaseConfig(backend="sqlite", sqlite_dir=".deer-flow/data")
    await init_engine_from_config(config)
    sf = get_session_factory()
    print(f"  Session factory: {sf}")

    # ── Step 2: Test get_local_provider ──
    print("=" * 60)
    print("Step 2: Test get_local_provider()")
    try:
        from app.gateway.deps import get_local_provider
        provider = get_local_provider()
        print(f"  Provider: {provider}")
        print(f"  Provider type: {type(provider).__name__}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        return

    # ── Step 3: Test _get_gateway_provider ──
    print("=" * 60)
    print("Step 3: Test _get_gateway_provider()")
    from app.extensions.user.sync import _get_gateway_provider

    gw_provider = await _get_gateway_provider()
    print(f"  Result: {gw_provider}")

    # ── Step 4: Test reading existing user ──
    print("=" * 60)
    print("Step 4: Read existing Gateway user")
    user = await provider.get_user_by_email("admin@eai-flow.com")
    if user:
        print(f"  Found: id={user.id}, email={user.email}, role={user.system_role}")
    else:
        print("  admin@eai-flow.com not found!")

    # ── Step 5: Test creating a Gateway user ──
    print("=" * 60)
    print("Step 5: Create a test Gateway user")
    test_email = "sync-test-direct@example.com"
    try:
        existing = await provider.get_user_by_email(test_email)
        if existing:
            print(f"  User already exists: {existing.email}")
        else:
            new_user = await provider.create_user(
                email=test_email,
                password="test123456",
                system_role="user",
            )
            print(f"  Created: id={new_user.id}, email={new_user.email}, role={new_user.system_role}")
            print(f"  Password hash prefix: {new_user.password_hash[:20]}...")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")

    # ── Step 6: Test sync_user_created (without Extensions DB) ──
    print("=" * 60)
    print("Step 6: Test sync_user_created")
    from app.extensions.user.sync import sync_user_created

    test_email2 = "sync-test-via-sync@example.com"
    try:
        # We don't have a real Extensions DB session, so role_id stays None
        await sync_user_created(
            db=None,  # type: ignore - not used because role_id is None
            email=test_email2,
            password="test123456",
            role_id=None,
        )
        print(f"  sync_user_created called without error")
        # Verify
        user2 = await provider.get_user_by_email(test_email2)
        if user2:
            print(f"  Verified: user exists in SQLite: {user2.email}")
        else:
            print(f"  FAILED: user NOT created in SQLite!")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)
    print("All tests completed.")

asyncio.run(main())
