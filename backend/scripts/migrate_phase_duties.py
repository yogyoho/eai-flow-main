"""Migrate legacy phase_duties JSONB to unified format.

Old: {"node_id": {"duty": "lead", "slot_type": "leader"}}
New: {"node_id": {"role": "phase_lead"}}

Run: PYTHONPATH=. python scripts/migrate_phase_duties.py [--dry-run]
"""
import asyncio
import sys

LEGACY_MAP = {
    "lead": "phase_lead",
    "leader": "phase_lead",
    "writer": "writer",
    "write": "writer",
    "reviewer": "reviewer",
    "dept_reviewer": "reviewer",
    "approver": "approver",
    "company_reviewer": "approver",
    "data_reviewer": "reviewer",
}


async def migrate(dry_run: bool = True):
    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectMember
    from sqlalchemy import select

    async with get_db_context() as db:
        result = await db.execute(select(ProjectMember))
        members = result.scalars().all()

        migrated = 0
        skipped = 0

        for member in members:
            duties = member.phase_duties or {}
            if not duties:
                skipped += 1
                continue

            new_duties = {}
            changed = False
            for node_id, duty_data in duties.items():
                if not isinstance(duty_data, dict):
                    new_duties[node_id] = duty_data
                    continue

                old_duty = duty_data.get("duty")
                old_slot = duty_data.get("slot_type")
                new_role = duty_data.get("role")

                if new_role:
                    new_duties[node_id] = {"role": new_role}
                elif old_duty:
                    new_duties[node_id] = {"role": LEGACY_MAP.get(old_duty, old_duty)}
                    changed = True
                elif old_slot:
                    new_duties[node_id] = {"role": LEGACY_MAP.get(old_slot, old_slot)}
                    changed = True
                else:
                    new_duties[node_id] = duty_data

            if changed:
                if not dry_run:
                    member.phase_duties = new_duties
                migrated += 1

        if not dry_run:
            await db.commit()

        print(f"Total members: {len(members)}")
        print(f"Migrated: {migrated}")
        print(f"Skipped (no duties): {skipped}")
        if dry_run:
            print("[DRY RUN — no changes made]")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(migrate(dry_run=dry))
