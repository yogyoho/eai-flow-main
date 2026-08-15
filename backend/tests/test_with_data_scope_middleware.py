"""with_data_scope 中间件依赖直调（现无直测）：超管 allow_all / deny 收集 / AND NOT deny。"""

import pytest
from rbac_helpers import fake_identity, make_user, patch_identity, policy_row, policy_rows_db

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.middleware import with_data_scope


@pytest.mark.asyncio
async def test_superadmin_gets_allow_all(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="superadmin"))
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=policy_rows_db([]))
    assert isinstance(rule, FilterRule) and rule.operator == "allow_all"


@pytest.mark.asyncio
async def test_deny_collected_composes_and_not(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    db = policy_rows_db([policy_row("d", grants={"deny_data_scopes": ["knowledge_public"]})])
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=db)
    assert rule.operator == "and", "allow AND NOT deny"
    assert rule.children[1].operator == "not"


@pytest.mark.asyncio
async def test_no_deny_returns_plain_allow(monkeypatch):
    patch_identity(monkeypatch, fake_identity(role_code="user"))
    rule = await with_data_scope("knowledge")(current_user=make_user(), db=policy_rows_db([]))
    assert rule.operator != "and"  # 无 deny → 不产生 AND NOT
