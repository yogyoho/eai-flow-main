"""F2/F3 回归：collab by-id 与 list_folders 必须走 scope 引擎（deny 生效）。

红→绿判别器：scope 引擎产出的 deny 否定被 SQLAlchemy 折叠为 "NOT IN"（deny 生效）；
legacy 手写子句是 `OR ... IN`，无 "not in"。
"""
import uuid

import pytest

from rbac_helpers import build_app, capture_sql, fake_identity, make_user, patch_identity, policy_row, smart_db
from app.extensions.docmgr.collab_routers import router as collab_router
from app.extensions.docmgr.routers import router as docmgr_router

DID = uuid.uuid4()


def _deny_db():
    # deny_data_scopes 策略 + user 角色（doc_owner/doc_project_member）
    return smart_db(
        policy_rows=[policy_row("d", grants={"deny_data_scopes": ["doc_project_member"]})],
        doc_row=None,
    )


def test_collab_by_id_scope_narrows(monkeypatch):
    """F2：collab by-id 查询必须含 scope 引擎的 deny 否定（deny 生效）。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = _deny_db()
    tc = build_app(collab_router, user=make_user(), db=db)
    r = tc.get(f"/api/extensions/docmgr/documents/{DID}/comments")
    assert r.status_code == 404  # mock 无行
    sql = capture_sql(db)
    assert "not in" in sql, f"collab by-id 未走 scope（deny 不生效）: {sql}"


def test_list_folders_scope_narrows(monkeypatch):
    """F3：/folders 查询必须含 scope 引擎的 deny 否定（deny 生效）。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = _deny_db()
    tc = build_app(docmgr_router, user=make_user(), db=db)
    r = tc.get("/api/extensions/docmgr/folders")
    assert r.status_code == 200  # 空数据
    sql = capture_sql(db)
    assert "not in" in sql, f"list_folders 未走 scope（deny 不生效）: {sql}"
