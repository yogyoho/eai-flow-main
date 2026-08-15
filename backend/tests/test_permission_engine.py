from app.extensions.auth.engine import FilterRule, UnifiedPermissionEngine
from app.extensions.auth.identity import AttributeSet


def identity(**kwargs):
    defaults = {
        "user_id": "u1",
        "username": "test",
        "role_code": "writer",
        "role_level": 10,
    }
    defaults.update(kwargs)
    return AttributeSet(**defaults)


class TestUnifiedPermissionEngine:
    def test_star_wildcard_grants_all(self):
        idn = identity(role_code="superadmin")
        engine = UnifiedPermissionEngine(
            role_permissions={"superadmin": {"*"}},
        )
        assert engine.check(idn, "kb:create") is True
        assert engine.check(idn, "any:random:thing") is True

    def test_exact_permission_match(self):
        idn = identity(role_code="writer")
        engine = UnifiedPermissionEngine(
            role_permissions={"writer": {"kb:read", "doc:read", "system:access"}},
        )
        assert engine.check(idn, "kb:read") is True
        assert engine.check(idn, "kb:create") is False

    def test_module_wildcard(self):
        idn = identity(role_code="admin")
        engine = UnifiedPermissionEngine(
            role_permissions={"admin": {"kb:*", "system:access"}},
        )
        assert engine.check(idn, "kb:read") is True
        assert engine.check(idn, "kb:create") is True
        assert engine.check(idn, "user:read") is False

    def test_list_permissions(self):
        idn = identity(role_code="writer")
        engine = UnifiedPermissionEngine(
            role_permissions={"writer": {"kb:read", "doc:read", "system:access"}},
        )
        perms = engine.list_permissions(idn)
        assert set(perms) == {"kb:read", "doc:read", "system:access"}

    def test_list_permissions_star_expands_all(self):
        idn = identity(role_code="superadmin")
        engine = UnifiedPermissionEngine(
            role_permissions={"superadmin": {"*"}},
            all_permission_ids={"kb:read", "kb:create", "user:read"},
        )
        perms = engine.list_permissions(idn)
        assert perms == {"kb:read", "kb:create", "user:read"}

    def test_unknown_role_denies_all(self):
        idn = identity(role_code=None)
        engine = UnifiedPermissionEngine(
            role_permissions={"writer": {"kb:read"}},
        )
        assert engine.check(idn, "kb:read") is False

    def test_policy_evaluation_or_semantics(self):
        from app.extensions.auth.engine import Policy

        idn = identity(role_code="writer")
        engine = UnifiedPermissionEngine(
            role_permissions={"writer": {"kb:read"}},
            policies=[
                Policy(name="p1", priority=10, conditions={"attr": "tags", "op": "contains", "value": "editor"}, grants={"permissions": ["kb:create"]}),
                Policy(name="p2", priority=20, conditions={"attr": "role_level", "op": "gte", "value": 5}, grants={"permissions": ["kb:delete"]}),
            ],
        )
        # writer has kb:read directly, NOT kb:create (no "editor" tag), but kb:delete via policy
        assert engine.check(idn, "kb:read") is True
        assert engine.check(idn, "kb:create") is False
        assert engine.check(idn, "kb:delete") is True


class TestFilterRule:
    def test_eq_to_dict(self):
        rule = FilterRule(operator="eq", field="owner_id", value="user-1")
        d = rule.to_dict()
        assert d == {"operator": "eq", "field": "owner_id", "value": "user-1", "children": None}

    def test_and_composite(self):
        inner1 = FilterRule(operator="eq", field="a", value=1)
        inner2 = FilterRule(operator="in", field="b", value=[1, 2])
        rule = FilterRule(operator="and", children=[inner1, inner2])
        d = rule.to_dict()
        assert d["operator"] == "and"
        assert len(d["children"]) == 2

    def test_from_template_simple_eq(self):
        template = {"owner_id": "$identity.user_id"}
        idn = identity(user_id="user-99")
        rule = FilterRule.from_template(template, idn)
        assert rule.operator == "eq"
        assert rule.field == "owner_id"
        assert rule.value == "user-99"

    def test_from_template_in_list(self):
        template = {"dept_id IN": "$identity.dept_ids"}
        idn = identity(dept_ids=["d1", "d2"])
        rule = FilterRule.from_template(template, idn)
        assert rule.operator == "in"
        assert rule.field == "dept_id"
        assert rule.value == ["d1", "d2"]

    def test_from_template_or(self):
        template = {
            "or": [
                {"owner_id": "$identity.user_id"},
                {"dept_id IN": "$identity.dept_ids"},
            ]
        }
        idn = identity(user_id="u1", dept_ids=["d1"])
        rule = FilterRule.from_template(template, idn)
        assert rule.operator == "or"
        assert len(rule.children) == 2
        assert rule.children[0].value == "u1"

    def test_from_template_empty_is_allow_all(self):
        rule = FilterRule.from_template({}, identity())
        assert rule.operator == "allow_all"

    def test_none_allow_default(self):
        rule = FilterRule()
        assert rule.operator == "none_allow"

    def test_to_sqlalchemy_eq(self):
        from sqlalchemy import Column, String, select
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()

        class MockModel(Base):
            __tablename__ = "mock_eq"
            owner_id = Column(String, primary_key=True)

        rule = FilterRule(operator="eq", field="owner_id", value="user-1")
        column_map = {"owner_id": MockModel.owner_id}
        expr = rule.to_sqlalchemy(MockModel, column_map)
        stmt = select(MockModel).where(expr)
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "owner_id" in sql

    def test_to_sqlalchemy_in(self):
        from sqlalchemy import Column, String
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()

        class MockModel(Base):
            __tablename__ = "mock_in"
            dept_id = Column(String, primary_key=True)

        rule = FilterRule(operator="in", field="dept_id", value=["d1", "d2"])
        column_map = {"dept_id": MockModel.dept_id}
        expr = rule.to_sqlalchemy(MockModel, column_map)
        assert expr is not None

    def test_to_sqlalchemy_and_composite(self):
        from sqlalchemy import Column, String
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()

        class MockModel(Base):
            __tablename__ = "mock_and"
            owner_id = Column(String, primary_key=True)
            dept_id = Column(String)

        inner1 = FilterRule(operator="eq", field="owner_id", value="u1")
        inner2 = FilterRule(operator="in", field="dept_id", value=["d1"])
        rule = FilterRule(operator="and", children=[inner1, inner2])
        column_map = {"owner_id": MockModel.owner_id, "dept_id": MockModel.dept_id}
        expr = rule.to_sqlalchemy(MockModel, column_map)
        assert expr is not None

    def test_to_sqlalchemy_auto_resolve_column(self):
        from sqlalchemy import Column, String
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()

        class MockModel(Base):
            __tablename__ = "mock_auto"
            access_type = Column(String, primary_key=True)

        rule = FilterRule(operator="eq", field="access_type", value="public")
        expr = rule.to_sqlalchemy(MockModel, column_map=None)
        assert expr is not None

    def test_to_sqlalchemy_none_allow_returns_false(self):
        from sqlalchemy import Column, String
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()

        class MockModel(Base):
            __tablename__ = "mock_none"
            id = Column(String, primary_key=True)

        rule = FilterRule(operator="none_allow")
        expr = rule.to_sqlalchemy(MockModel)
        # Should produce a SQLAlchemy false() expression
        assert expr is not None

    def test_from_template_in_with_none_value_returns_none_allow(self):
        template = {"dept_id IN": "$identity.dept_id"}
        idn = identity(dept_id=None)
        rule = FilterRule.from_template(template, idn)
        assert rule.operator == "none_allow"

    def test_not_contains_returns_false_when_attr_not_container(self):
        from app.extensions.auth.engine import Policy

        idn = identity(tags=None)
        engine = UnifiedPermissionEngine(
            role_permissions={"writer": set()},
            policies=[
                Policy(name="test", priority=10, conditions={"attr": "tags", "op": "not_contains", "value": "restricted"}, grants={"permissions": ["kb:create"]}),
            ],
        )
        assert engine.check(idn, "kb:create") is False

    def test_not_in_returns_false_when_value_not_list(self):
        from app.extensions.auth.engine import Policy

        idn = identity(dept_id="dept-1")
        engine = UnifiedPermissionEngine(
            role_permissions={"writer": set()},
            policies=[
                Policy(name="test", priority=10, conditions={"attr": "dept_id", "op": "not_in", "value": "dept-123"}, grants={"permissions": ["kb:create"]}),
            ],
        )
        assert engine.check(idn, "kb:create") is False

    def test_not_contains_works_with_valid_list(self):
        from app.extensions.auth.engine import Policy

        idn = identity(tags=["editor", "viewer"])
        engine = UnifiedPermissionEngine(
            role_permissions={"writer": set()},
            policies=[
                Policy(name="test", priority=10, conditions={"attr": "tags", "op": "not_contains", "value": "restricted"}, grants={"permissions": ["kb:create"]}),
            ],
        )
        assert engine.check(idn, "kb:create") is True


def test_engine_uses_resolved_inherited_permissions():
    """验证 engine 接收 registry.resolve_role_permissions 已展开 #inherit 的结果。"""
    engine = UnifiedPermissionEngine(
        role_permissions={
            # 模拟 registry.resolve_role_permissions 已展开 #inherit
            "manager": {"project:edit", "kb:read", "doc:read"},
            "user": {"kb:read"},
        },
        all_permission_ids={"project:edit", "kb:read", "doc:read"},
    )
    identity = AttributeSet(user_id="1", username="u", role_code="manager", role_level=20)
    assert engine.check(identity, "project:edit") is True
    assert engine.check(identity, "doc:read") is True  # 继承来的权限
