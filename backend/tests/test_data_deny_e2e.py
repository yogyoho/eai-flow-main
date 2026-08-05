"""deny_data_scopes 必须到达 knowledge 真实列表查询（engine 组合之外，走 with_data_scope 全链）。"""
import pytest
from rbac_helpers import fake_identity, make_user, patch_identity, policy_row, smart_db

from app.extensions.auth.middleware import with_data_scope
from app.extensions.models import KnowledgeBase

_COLMAP = {
    "owner_id": KnowledgeBase.owner_id,
    "access_type": KnowledgeBase.access_type,
    "allowed_depts": KnowledgeBase.allowed_depts,
}


def _compile(rule):
    # 不用 literal_binds（UUID 列 vs str 无法内联渲染）；结构断言即可
    return str(rule.to_sqlalchemy(KnowledgeBase, _COLMAP).compile()).lower()


@pytest.mark.asyncio
async def test_deny_reaches_list_query_sql(monkeypatch):
    """带 deny_data_scopes=[knowledge_public] 策略时，列表 SQL 必须含 AND NOT 拒绝谓词。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = smart_db(policy_rows=[policy_row("d", grants={"deny_data_scopes": ["knowledge_public"]})])
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=db)
    sql = _compile(rule)
    # SQLAlchemy 把 NOT (access_type = 'public') 折叠为 access_type != ...——"!=" 即 deny 分支标记
    assert "!=" in sql, f"数据 deny 未出现在列表 SQL: {sql}"
    assert "access_type" in sql  # deny 分支引用 knowledge_public 的 access_type 列


@pytest.mark.asyncio
async def test_no_deny_list_query_plain(monkeypatch):
    """无 deny 策略时，scope 规则不含 NOT。"""
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = smart_db(policy_rows=[])
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=db)
    sql = _compile(rule)
    assert "!=" not in sql and "not" not in sql, f"无 deny 却出现否定谓词: {sql}"
