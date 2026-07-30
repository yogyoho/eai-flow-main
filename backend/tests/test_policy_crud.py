"""Tests for Policy model and engine integration."""
from app.extensions.auth.engine import Policy as EnginePolicy


class TestPolicyEngine:
    def test_policy_from_db_row(self):
        p = EnginePolicy(
            name="test", priority=10,
            conditions={"attr": "role_level", "op": "gte", "value": 5},
            grants={"permissions": ["kb:create"]},
        )
        assert p.name == "test"
        assert p.priority == 10
        assert p.conditions["attr"] == "role_level"
        assert "kb:create" in p.grants["permissions"]
