"""Tests for AttributeSet and IdentityProvider."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.identity import AttributeSet, IdentityProvider


class TestAttributeSet:
    def test_basic_attributes(self):
        """Test that basic attributes are stored correctly."""
        attrs = AttributeSet(
            user_id="user-1",
            username="testuser",
            role_code="dept_head",
            role_level=50,
            dept_id="dept-1",
            dept_ids=["dept-1", "dept-2"],
        )
        assert attrs.user_id == "user-1"
        assert attrs.role_code == "dept_head"
        assert "dept-1" in attrs.dept_ids

    def test_to_dict_includes_all_fields(self):
        """Test that to_dict() includes all relevant fields."""
        attrs = AttributeSet(
            user_id="u1",
            username="test",
            role_code="writer",
            role_level=10,
            dept_id="d1",
            dept_ids=["d1"],
            member_projects=["p1"],
            project_roles={"p1": "owner"},
            tags=["external"],
            labels={"region": "east"},
        )
        d = attrs.to_dict()
        assert d["role_code"] == "writer"
        assert d["tags"] == ["external"]
        assert d["labels"]["region"] == "east"

    def test_get_attr_simple_field(self):
        """Test get_attr() resolves simple fields."""
        attrs = AttributeSet(user_id="u1", username="test", role_code="admin", role_level=100)
        assert attrs.get_attr("role_code") == "admin"
        assert attrs.get_attr("role_level") == 100
        assert attrs.get_attr("nonexistent") is None

    def test_get_attr_nested_path(self):
        """Test get_attr() resolves dotted paths."""
        attrs = AttributeSet(user_id="u1", username="test", labels={"region": "east", "clearance": "L3"})
        assert attrs.get_attr("labels.region") == "east"
        assert attrs.get_attr("labels.clearance") == "L3"
        assert attrs.get_attr("labels.nonexistent") is None

    def test_default_role_level_zero(self):
        """Test that role_level defaults to 0."""
        attrs = AttributeSet(user_id="u1", username="test", role_code="viewer")
        assert attrs.role_level == 0


class TestIdentityProvider:
    @pytest.mark.asyncio
    async def test_resolve_returns_attribute_set(self):
        """Test that resolve() returns a properly populated AttributeSet."""
        user_id = str(uuid.uuid4())

        # Create mock User
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.username = "testuser"
        mock_user.dept_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_user.role_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        # Create mock Role
        mock_role = MagicMock()
        mock_role.code = "dept_head"
        mock_role.level = 50
        mock_role.is_system = False

        # Create mock UserDepartment
        mock_ud1 = MagicMock()
        mock_ud1.dept_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_ud2 = MagicMock()
        mock_ud2.dept_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

        # Create mock ProjectMember
        mock_pm = MagicMock()
        mock_pm.project_id = uuid.UUID("00000000-0000-0000-0000-000000000003")
        mock_pm.role = "owner"

        # Build mock DB session
        mock_db = MagicMock(spec=AsyncSession)

        # Call 1: User query -> returns mock_user
        user_result = MagicMock()
        user_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        # Call 2: UserDepartment query
        ud_result = MagicMock()
        ud_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_ud1, mock_ud2])))
        # Call 3: ProjectMember query
        pm_result = MagicMock()
        pm_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_pm])))

        mock_db.execute = AsyncMock(side_effect=[user_result, ud_result, pm_result])

        # Mock db.get for Role lookup
        async def mock_db_get(model, id_val):
            if str(id_val) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa":
                return mock_role
            return None
        mock_db.get = AsyncMock(side_effect=mock_db_get)

        provider = IdentityProvider()
        identity = await provider.resolve(user_id, mock_db)

        assert identity.user_id == user_id
        assert identity.username == "testuser"
        assert identity.role_code == "dept_head"
        assert identity.role_level == 50
        assert len(identity.dept_ids) == 2
        assert len(identity.member_projects) == 1
        assert str(mock_pm.project_id) in identity.member_projects
        assert identity.project_roles[str(mock_pm.project_id)] == "owner"

    @pytest.mark.asyncio
    async def test_resolve_user_not_found_raises(self):
        """Test that resolve() raises ValueError for unknown user."""
        mock_db = MagicMock(spec=AsyncSession)
        user_result = MagicMock()
        user_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=user_result)

        provider = IdentityProvider()
        with pytest.raises(ValueError, match="not found"):
            await provider.resolve("nonexistent", mock_db)

    @pytest.mark.asyncio
    async def test_resolve_no_role(self):
        """Test resolve() handles user without a role gracefully."""
        user_id = str(uuid.uuid4())
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.username = "nobody"
        mock_user.dept_id = None
        mock_user.role_id = None

        mock_db = MagicMock(spec=AsyncSession)
        user_result = MagicMock()
        user_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        ud_result = MagicMock()
        ud_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        pm_result = MagicMock()
        pm_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_db.execute = AsyncMock(side_effect=[user_result, ud_result, pm_result])

        provider = IdentityProvider()
        identity = await provider.resolve(user_id, mock_db)

        assert identity.user_id == user_id
        assert identity.role_code is None
        assert identity.role_level == 0
        assert identity.dept_ids == []

    @pytest.mark.asyncio
    async def test_tag_resolver_adds_tags_and_labels(self):
        """Test that registered TagResolvers add tags, labels, and extra data."""
        user_id = str(uuid.uuid4())
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.username = "tagged_user"
        mock_user.dept_id = None
        mock_user.role_id = None

        mock_db = MagicMock(spec=AsyncSession)
        user_result = MagicMock()
        user_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        ud_result = MagicMock()
        ud_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        pm_result = MagicMock()
        pm_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_db.execute = AsyncMock(side_effect=[user_result, ud_result, pm_result])

        # Create a mock TagResolver
        mock_resolver = MagicMock()
        mock_resolver.name = "test_resolver"
        mock_resolver.resolve = AsyncMock(return_value={
            "tags": ["vip", "external"],
            "labels": {"risk": "low"},
            "extra": {"notes": "test"},
        })

        provider = IdentityProvider()
        provider.register_tag_resolver(mock_resolver)
        identity = await provider.resolve(user_id, mock_db)

        assert "vip" in identity.tags
        assert "external" in identity.tags
        assert identity.labels["risk"] == "low"
        assert identity.extra["notes"] == "test"
        mock_resolver.resolve.assert_awaited_once_with(user_id, mock_db)

    @pytest.mark.asyncio
    async def test_tag_resolver_failure_does_not_block(self):
        """Test that a failing TagResolver doesn't prevent identity resolution."""
        user_id = str(uuid.uuid4())
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.username = "resilient_user"
        mock_user.dept_id = None
        mock_user.role_id = None

        mock_db = MagicMock(spec=AsyncSession)
        user_result = MagicMock()
        user_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        ud_result = MagicMock()
        ud_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        pm_result = MagicMock()
        pm_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_db.execute = AsyncMock(side_effect=[user_result, ud_result, pm_result])

        # Create a resolver that raises
        bad_resolver = MagicMock()
        bad_resolver.name = "bad_resolver"
        bad_resolver.resolve = AsyncMock(side_effect=RuntimeError("something went wrong"))

        provider = IdentityProvider()
        provider.register_tag_resolver(bad_resolver)
        identity = await provider.resolve(user_id, mock_db)

        # Should still succeed with no tags
        assert identity.username == "resilient_user"
        assert identity.tags == []
        bad_resolver.resolve.assert_awaited_once()

    def test_get_identity_provider_singleton(self):
        """Test that get_identity_provider() returns a singleton."""
        from app.extensions.auth.identity import get_identity_provider

        p1 = get_identity_provider()
        p2 = get_identity_provider()
        assert p1 is p2

    @pytest.mark.asyncio
    async def test_resolve_with_multiple_tag_resolvers(self):
        """Test that multiple TagResolvers are all invoked and merged."""
        user_id = str(uuid.uuid4())
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.username = "multi_tag_user"
        mock_user.dept_id = None
        mock_user.role_id = None

        mock_db = MagicMock(spec=AsyncSession)
        user_result = MagicMock()
        user_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        ud_result = MagicMock()
        ud_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        pm_result = MagicMock()
        pm_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_db.execute = AsyncMock(side_effect=[user_result, ud_result, pm_result])

        r1 = MagicMock()
        r1.name = "dept_resolver"
        r1.resolve = AsyncMock(return_value={"tags": ["engineering"], "labels": {"team": "backend"}})

        r2 = MagicMock()
        r2.name = "risk_resolver"
        r2.resolve = AsyncMock(return_value={"tags": ["vip"], "labels": {"risk": "medium"}})

        provider = IdentityProvider()
        provider.register_tag_resolver(r1)
        provider.register_tag_resolver(r2)
        identity = await provider.resolve(user_id, mock_db)

        assert "engineering" in identity.tags
        assert "vip" in identity.tags
        assert identity.labels["team"] == "backend"
        assert identity.labels["risk"] == "medium"
