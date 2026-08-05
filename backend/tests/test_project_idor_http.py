"""项目 IDOR 端点 HTTP 级闭合：非成员 403 / 成员 200 / 超管 200。

真实 project router；mock db 只服务 is_superadmin(跳过) 与 membership 查询。
"""
import uuid

import pytest
from rbac_helpers import build_app, fake_identity, make_user, patch_identity, smart_db

from app.extensions.auth import admin as _admin_mod
from app.extensions.project.routers import router as project_router

PID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _no_superadmin(monkeypatch):
    """默认让 is_superadmin 返回 False（非超管路径）。"""

    async def _false(db, user_id):  # noqa: ARG001
        return False

    monkeypatch.setattr(_admin_mod, "is_superadmin", _false)


def test_non_member_403(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user", member_projects=[]))
    db = smart_db(member_row=None)  # 非成员 → membership 查询 None
    tc = build_app(project_router, user=make_user(), db=db)
    assert tc.get(f"/api/extensions/project/projects/{PID}/activities").status_code == 403
    assert tc.get(f"/api/extensions/project/projects/{PID}/stats").status_code == 403
    assert tc.get(f"/api/extensions/project/projects/{PID}/files").status_code == 403


def test_member_200(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user", member_projects=[str(PID)]))
    db = smart_db(member_row=object())  # 有成员行 → 过门 → 端点体跑（空数据 → 200）
    tc = build_app(project_router, user=make_user(), db=db)
    assert tc.get(f"/api/extensions/project/projects/{PID}/activities").status_code == 200


def test_superadmin_200(monkeypatch):
    async def _true(db, user_id):  # noqa: ARG001
        return True

    monkeypatch.setattr(_admin_mod, "is_superadmin", _true)  # 覆盖 autouse 的 False
    patch_identity(monkeypatch, fake_identity(role_code="superadmin"))
    db = smart_db(member_row=None)
    tc = build_app(project_router, user=make_user(role_name="超级管理员"), db=db)
    assert tc.get(f"/api/extensions/project/projects/{PID}/activities").status_code == 200
