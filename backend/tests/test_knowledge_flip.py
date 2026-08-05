"""knowledge 可见性接线（HTTP/SQL 层）：dept 角色 scope 含 overlap；by-id 复用 list scope。"""
import uuid

import pytest

from rbac_helpers import build_app, capture_sql, fake_identity, make_user, patch_identity, smart_db
from app.extensions.auth.middleware import with_data_scope
from app.extensions.knowledge.routers import router
from app.extensions.models import KnowledgeBase

_COLMAP = {
    "owner_id": KnowledgeBase.owner_id,
    "access_type": KnowledgeBase.access_type,
    "allowed_depts": KnowledgeBase.allowed_depts,
}


@pytest.mark.asyncio
async def test_dept_role_scope_includes_overlap(monkeypatch):
    """dept_head 角色的 knowledge scope 必须表达 allowed_depts OVERLAP（dept 共享接线）。"""
    dept = uuid.uuid4()
    patch_identity(monkeypatch, fake_identity(role_code="dept_head", dept_ids=[str(dept)]))
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=smart_db(policy_rows=[]))
    sql = str(rule.to_sqlalchemy(KnowledgeBase, _COLMAP).compile()).lower()
    assert "allowed_depts" in sql and "&&" in sql, f"dept 共享未接线: {sql}"


def test_by_id_reuses_list_scope(monkeypatch):
    """GET /knowledge-bases/{id} 的查询必须叠加 scope 谓词（404 on no-access）。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = smart_db(policy_rows=[], kb_row=None)
    tc = build_app(router, user=make_user(), db=db)
    r = tc.get(f"/api/extensions/knowledge-bases/{uuid.uuid4()}")
    assert r.status_code == 404
    sql = capture_sql(db)
    assert "owner_id" in sql  # 查询带 scope（doc_owner 分支），非裸 id 查询
