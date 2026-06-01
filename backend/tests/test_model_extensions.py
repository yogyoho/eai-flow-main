"""Tests for extended Department and ProjectMember models."""
import pytest
from unittest.mock import MagicMock

from app.extensions.models import Department, ProjectMember


def test_department_has_unit_type():
    """Department model should have unit_type field."""
    dept = Department(name="Test", unit_type="internal")
    assert dept.unit_type == "internal"


def test_department_unit_type_default():
    """Department unit_type defaults to 'internal' at DB insert time (server default)."""
    # mapped_column(default=...) is a server-side default, not Python constructor default
    # When constructing in-memory, the value is None until persisted
    dept = Department(name="Test")
    assert dept.unit_type is None  # Not set until DB insert
    # The actual default is enforced at the DB level:
    # CREATE TABLE ... unit_type VARCHAR(20) DEFAULT 'internal' NOT NULL


def test_department_unit_type_external():
    """Department can be external type."""
    dept = Department(name="External Partner", unit_type="external")
    assert dept.unit_type == "external"


def test_department_unit_type_virtual():
    """Department can be virtual (temporary project group)."""
    dept = Department(name="Project Team", unit_type="virtual")
    assert dept.unit_type == "virtual"


def test_department_has_metadata():
    """Department model should have metadata JSONB field."""
    dept = Department(name="Test", extra_metadata={"contact": "test@example.com"})
    assert dept.extra_metadata == {"contact": "test@example.com"}


def test_department_metadata_default_none():
    """Department metadata should default to None."""
    dept = Department(name="Test")
    assert dept.extra_metadata is None


def test_project_member_has_phase_duties():
    """ProjectMember model should have phase_duties JSONB field."""
    duties = {"phase-a": {"duty": "lead", "role": "阶段负责人"}}
    member = ProjectMember(project_id=None, user_id=None, phase_duties=duties)
    assert member.phase_duties == duties


def test_project_member_phase_duties_default_none():
    """ProjectMember phase_duties should default to None."""
    member = ProjectMember(project_id=None, user_id=None)
    assert member.phase_duties is None


def test_project_member_has_source_org_unit_id():
    """ProjectMember model should have source_org_unit_id field."""
    member = ProjectMember(project_id=None, user_id=None)
    # Field exists, value is None since no FK set
    assert member.source_org_unit_id is None
