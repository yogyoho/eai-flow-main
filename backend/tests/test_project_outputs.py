"""Tests for project-outputs aggregation, cross-user write-back, and versions."""

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


class TestProjectDocVersionModel:
    def test_model_tablename_and_key_fields(self):
        from app.extensions.models import ProjectDocVersion
        assert ProjectDocVersion.__tablename__ == "project_doc_versions"
        cols = {c.name for c in ProjectDocVersion.__table__.columns}
        # 关键列存在
        assert {"project_id", "thread_id", "rel_path", "content", "editor_user_id"}.issubset(cols)
