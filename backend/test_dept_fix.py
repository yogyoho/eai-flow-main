import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.extensions.models import User, UserDepartment, Department
from app.extensions.user.service import UserService
from app.extensions.user_department.service import UserDepartmentService
from app.extensions.schemas import UserUpdate

async def test():
    engine = create_async_engine('postgresql+asyncpg://agentflow:agentflow123@postgres-ext:5432/agentflow')
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Find a user with 2+ departments
        subq = select(UserDepartment.user_id, func.count().label('cnt')).group_by(UserDepartment.user_id).having(func.count() >= 2).subquery()
        stmt = select(UserDepartment).join(subq, UserDepartment.user_id == subq.c.user_id).limit(1)
        result = await db.execute(stmt)
        ud = result.scalar_one_or_none()

        if not ud:
            print('No user with 2+ departments, creating test data...')
            stmt = select(UserDepartment).limit(1)
            result = await db.execute(stmt)
            ud = result.scalar_one_or_none()
            if not ud:
                print('No user-department associations at all')
                return

            dept_stmt = select(Department).where(Department.id != ud.dept_id).limit(1)
            dept_result = await db.execute(dept_stmt)
            dept2 = dept_result.scalar_one_or_none()
            if not dept2:
                print('No second department available')
                return

            await UserDepartmentService.add_user_to_dept(db, ud.user_id, dept2.id, is_primary=False)
            user_id = ud.user_id
        else:
            user_id = ud.user_id

        dept_ids_before, primary_before = await UserDepartmentService.get_user_all_dept_ids(db, user_id)
        print(f'Before: dept_ids={dept_ids_before}, primary={primary_before}')

        user = await UserService.get_user_by_id(db, user_id)
        print(f'User dept_id: {user.dept_id}')

        # Remove one department (keep the primary one)
        keep_dept = primary_before
        remove_dept = [d for d in dept_ids_before if d != keep_dept][0]
        print(f'Removing dept: {remove_dept}, keeping: {keep_dept}')

        update_data = UserUpdate(dept_ids=[keep_dept], dept_id=keep_dept)
        updated_user = await UserService.update_user(db, user, update_data)

        dept_ids_after, primary_after = await UserDepartmentService.get_user_all_dept_ids(db, updated_user.id)
        print(f'After: dept_ids={dept_ids_after}, primary={primary_after}')

        assert len(dept_ids_after) == 1, f'FAIL: expected 1 dept, got {len(dept_ids_after)}'
        assert dept_ids_after[0] == keep_dept, f'FAIL: expected {keep_dept}, got {dept_ids_after}'
        assert primary_after == keep_dept, f'FAIL: expected primary={keep_dept}, got {primary_after}'
        print('TEST 1 PASSED: Remove one of two departments')

        # Restore the removed department
        await UserDepartmentService.add_user_to_dept(db, updated_user.id, remove_dept, is_primary=False)
        await db.commit()
        dept_ids_restored, _ = await UserDepartmentService.get_user_all_dept_ids(db, user_id)
        print(f'Restored: dept_ids={dept_ids_restored}')
        assert len(dept_ids_restored) == 2, f'FAIL: expected 2 depts'
        print('TEST 2 PASSED: Restored department')

        print('=== ALL TESTS PASSED ===')

    await engine.dispose()

asyncio.run(test())
