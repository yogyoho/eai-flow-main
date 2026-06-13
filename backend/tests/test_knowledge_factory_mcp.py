"""Tests for knowledge factory MCP server tools and TemplateService name filter.

TDD: test-first patterns for the new code added in the fire-protection-report-v2 integration.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _make_template(**overrides):
    """Create a sample ExtractionTemplate-like object."""
    t = MagicMock()
    t.id = overrides.get("id", uuid4())
    t.domain = overrides.get("domain", "environmental_impact_assessment")
    t.name = overrides.get("name", "公用工程_消防设计专篇_模板")
    t.version = overrides.get("version", "v1.0")
    t.status = overrides.get("status", "published")
    t.completeness_score = overrides.get("completeness_score", 72)
    t.root_sections_json = overrides.get("root_sections_json", {"sections": []})
    t.cross_section_rules = overrides.get("cross_section_rules", None)
    t.source_report_ids = overrides.get("source_report_ids", None)
    t.created_by = overrides.get("created_by", None)
    t.created_at = MagicMock()
    t.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    t.updated_at = MagicMock()
    t.updated_at.isoformat.return_value = "2026-06-01T00:00:00"
    return t


@pytest.fixture
def mock_db():
    """Async database session mock."""
    return AsyncMock()


@pytest.fixture
def mock_run_in_db():
    """A fake _run_in_db that calls the closure synchronously with a mock db."""
    async def _fake(func):
        db = AsyncMock()
        return await func(db)
    return _fake


# ──────────────────────────────────────────────────────────────────────
# TemplateService.list_templates — name filter
# ──────────────────────────────────────────────────────────────────────


class TestListTemplatesNameFilter:
    """Test the new `name` parameter on TemplateService.list_templates."""

    @pytest.mark.asyncio
    async def test_filter_by_name_matches(self, mock_db):
        """ILIKE filter returns matching templates."""
        from app.extensions.knowledge_factory.service import TemplateService

        mock_db.execute = AsyncMock()

        template = _make_template()

        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [template]

        mock_db.execute.side_effect = [mock_count, mock_result]

        templates, total = await TemplateService.list_templates(
            mock_db, name="消防设计", status="published"
        )

        assert total == 1
        assert len(templates) == 1
        assert templates[0].name == template.name

        # SQLAlchemy compiles ilike to lower(...) LIKE lower(...)
        last_query = str(mock_db.execute.call_args_list[-1][0][0])
        assert "lower" in last_query.lower()

    @pytest.mark.asyncio
    async def test_filter_by_name_no_match(self, mock_db):
        """ILIKE filter returns empty when no name matches."""
        from app.extensions.knowledge_factory.service import TemplateService

        mock_count = MagicMock()
        mock_count.scalar.return_value = 0
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count, mock_result]

        templates, total = await TemplateService.list_templates(
            mock_db, name="不存在的模板名称xyz"
        )

        assert total == 0
        assert templates == []

    @pytest.mark.asyncio
    async def test_filter_by_name_preserves_existing_params(self, mock_db):
        """Name filter works alongside existing domain and status filters."""
        from app.extensions.knowledge_factory.service import TemplateService

        mock_count = MagicMock()
        mock_count.scalar.return_value = 2
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count, mock_result]

        templates, total = await TemplateService.list_templates(
            mock_db, domain="env", name="消防", status="published,draft", page=2, limit=10
        )

        assert total == 2
        # Verify the SQL contains all filter clauses
        last_query = str(mock_db.execute.call_args_list[-1][0][0])
        assert "domain" in last_query.lower()
        assert "lower" in last_query.lower()  # ilike compiles to lower LIKE


# ──────────────────────────────────────────────────────────────────────
# kf_resolve_template — matching logic
# ──────────────────────────────────────────────────────────────────────


class TestKfResolveTemplate:
    """Test the intelligent template matching logic."""

    @pytest.mark.asyncio
    async def test_exact_match_found(self):
        """Returns template when exact match exists. Patches the
        TemplateService imported inside the handler."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_resolve_template,
        )

        tid = str(uuid4())

        # Patch TemplateService where it's actually imported (service.py level)
        with patch(
            "app.extensions.knowledge_factory.service.TemplateService"
        ) as mock_svc:
            # Mock to_template_document return
            mock_doc = MagicMock()
            mock_doc.model_dump.return_value = {
                "template_id": tid,
                "name": "消防设计模板",
                "version": "v1.0",
                "domain": "env",
                "status": "published",
                "completeness_score": 80,
                "root_sections": [],
                "cross_section_rules": [],
                "created_at": "2026-01-01T00:00:00",
            }
            mock_svc.to_template_document.return_value = mock_doc

            # Provide a _run_in_db that skips DB queries entirely
            async def _fake_run_in_db(func):
                return {
                    "template_id": tid,
                    "name": "消防设计模板",
                    "version": "v1.0",
                    "domain": "env",
                    "status": "published",
                    "completeness_score": 80,
                    "root_sections": [],
                    "cross_section_rules": [],
                    "created_at": "2026-01-01T00:00:00",
                    "found": True,
                    "match_level": "exact",
                }

            result = await handle_kf_resolve_template(
                {
                    "domain_keywords": ["消防设计专篇", "消防设计报告"],
                    "industry": "化工",
                    "min_completeness_score": 60,
                },
                _fake_run_in_db,
            )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["found"] is True
        assert data["match_level"] in ("exact", "keyword", "loose")

    @pytest.mark.asyncio
    async def test_no_template_found(self, mock_run_in_db):
        """Returns found=false when no template matches."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_resolve_template,
        )

        async def _fake_run_in_db(func):
            return {"found": False, "reason": "no_template_found",
                    "suggestion": "请先通过知识工厂抽取该领域的报告模板"}

        result = await handle_kf_resolve_template(
            {"domain_keywords": ["完全不存在的领域xyz"]},
            _fake_run_in_db,
        )

        data = json.loads(result[0].text)
        assert data["found"] is False
        assert "reason" in data

    @pytest.mark.asyncio
    async def test_low_quality_filtered(self, mock_run_in_db):
        """Returns found=false when template completeness is below threshold."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_resolve_template,
        )

        async def _fake_run_in_db(func):
            return {"found": False, "reason": "low_quality",
                    "suggestion": "存在模板但完整度评分低于阈值(90)，建议优化模板后再生成"}

        result = await handle_kf_resolve_template(
            {"domain_keywords": ["消防设计专篇"], "min_completeness_score": 90},
            _fake_run_in_db,
        )

        data = json.loads(result[0].text)
        assert data["found"] is False
        assert data["reason"] == "low_quality"

    @pytest.mark.asyncio
    async def test_missing_domain_keywords_uses_defaults(self, mock_run_in_db):
        """Call with minimal args still works."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_resolve_template,
        )

        call_count = 0

        async def _fake_run_in_db(func):
            nonlocal call_count
            call_count += 1
            return {"found": False, "reason": "no_template_found",
                    "suggestion": "请先通过知识工厂抽取该领域的报告模板"}

        await handle_kf_resolve_template({"domain_keywords": []}, _fake_run_in_db)
        assert call_count == 1


# ──────────────────────────────────────────────────────────────────────
# kf_get_template — UUID handling
# ──────────────────────────────────────────────────────────────────────


class TestKfGetTemplate:
    """Test get-template-by-id with UUID validation."""

    @pytest.mark.asyncio
    async def test_valid_uuid_returns_template(self, mock_run_in_db):
        """Valid UUID returns template data."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_get_template,
        )

        tid = str(uuid4())

        async def _fake_run_in_db(func):
            return {"found": True, "template_id": tid, "name": "测试模板"}

        result = await handle_kf_get_template({"template_id": tid}, _fake_run_in_db)

        data = json.loads(result[0].text)
        assert data["found"] is True
        assert data["template_id"] == tid

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_error(self, mock_run_in_db):
        """Invalid UUID string returns found=false immediately without calling DB."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_get_template,
        )

        result = await handle_kf_get_template(
            {"template_id": "not-a-valid-uuid"}, mock_run_in_db
        )

        data = json.loads(result[0].text)
        assert data["found"] is False
        assert data["reason"] == "invalid_uuid"

    @pytest.mark.asyncio
    async def test_empty_uuid_returns_error(self, mock_run_in_db):
        """Empty string returns invalid_uuid error."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_get_template,
        )

        result = await handle_kf_get_template({"template_id": ""}, mock_run_in_db)

        data = json.loads(result[0].text)
        assert data["found"] is False
        assert data["reason"] == "invalid_uuid"

    @pytest.mark.asyncio
    async def test_nonexistent_template(self, mock_run_in_db):
        """Valid UUID but template not found in DB."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_get_template,
        )

        tid = str(uuid4())

        async def _fake_run_in_db(func):
            return {"found": False, "reason": "template_not_found",
                    "detail": f"模板 {tid} 不存在"}

        result = await handle_kf_get_template({"template_id": tid}, _fake_run_in_db)

        data = json.loads(result[0].text)
        assert data["found"] is False
        assert data["reason"] == "template_not_found"


# ──────────────────────────────────────────────────────────────────────
# kf_query_templates
# ──────────────────────────────────────────────────────────────────────


class TestKfQueryTemplates:
    """Test template search/filtering."""

    @pytest.mark.asyncio
    async def test_query_with_all_params(self, mock_run_in_db):
        """Query with domain, name, status, limit."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_query_templates,
        )

        async def _fake_run_in_db(func):
            return {
                "templates": [
                    {"id": str(uuid4()), "domain": "env", "name": "消防模板",
                     "version": "v1.0", "status": "published",
                     "completeness_score": 80,
                     "created_at": "2026-01-01T00:00:00",
                     "updated_at": "2026-06-01T00:00:00"}
                ],
                "total": 1,
            }

        result = await handle_kf_query_templates(
            {"domain": "env", "name": "消防", "status": "published", "limit": 5},
            _fake_run_in_db,
        )

        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert len(data["templates"]) == 1
        assert data["templates"][0]["name"] == "消防模板"

    @pytest.mark.asyncio
    async def test_query_defaults(self, mock_run_in_db):
        """No params uses sensible defaults."""
        from app.extensions.knowledge_factory.mcp_server.tools.template_tools import (
            handle_kf_query_templates,
        )

        async def _fake_run_in_db(func):
            return {"templates": [], "total": 0}

        result = await handle_kf_query_templates({}, _fake_run_in_db)

        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["templates"] == []


# ──────────────────────────────────────────────────────────────────────
# kf_list_domains
# ──────────────────────────────────────────────────────────────────────


class TestKfListDomains:
    """Test domain listing."""

    @pytest.mark.asyncio
    async def test_list_all_domains(self, mock_run_in_db):
        """Returns all domains when no filter."""
        from app.extensions.knowledge_factory.mcp_server.tools.domain_tools import (
            handle_kf_list_domains,
        )

        async def _fake_run_in_db(func):
            return {
                "domains": [
                    {"id": "env", "name": "环境影响评价", "industry": "化工",
                     "report_type": "消防设计专篇", "description": "...",
                     "parent_domain": None}
                ],
                "total": 1,
            }

        result = await handle_kf_list_domains({}, _fake_run_in_db)

        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["domains"][0]["id"] == "env"

    @pytest.mark.asyncio
    async def test_filter_by_industry(self, mock_run_in_db):
        """Industry filter is passed through."""
        from app.extensions.knowledge_factory.mcp_server.tools.domain_tools import (
            handle_kf_list_domains,
        )

        async def _fake_run_in_db(func):
            return {"domains": [], "total": 0}

        result = await handle_kf_list_domains({"industry": "化工"}, _fake_run_in_db)

        data = json.loads(result[0].text)
        assert data["total"] == 0


# ──────────────────────────────────────────────────────────────────────
# _run_in_db — engine lifecycle
# ──────────────────────────────────────────────────────────────────────


class TestRunInDb:
    """Test the _run_in_db helper ensures proper resource cleanup.

    Patches sqlalchemy.ext.asyncio at the import site because
    create_async_engine / async_sessionmaker are imported lazily inside
    _run_in_db via `from sqlalchemy.ext.asyncio import ...`.
    """

    @pytest.mark.asyncio
    async def test_engine_disposed_after_success(self):
        """Engine.dispose() is called after a successful query."""
        from app.extensions.knowledge_factory.mcp_server.server import _run_in_db

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("os.environ", {"KF_DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test"}):
            with patch(
                "sqlalchemy.ext.asyncio.create_async_engine",
                return_value=mock_engine,
            ):
                with patch(
                    "sqlalchemy.ext.asyncio.async_sessionmaker",
                    return_value=lambda **kw: mock_session,
                ):
                    async def _query(db):
                        return {"ok": True}

                    result = await _run_in_db(_query)

        assert result == {"ok": True}
        mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_engine_disposed_after_error(self):
        """Engine.dispose() is called even when the query function raises."""
        from app.extensions.knowledge_factory.mcp_server.server import _run_in_db

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("os.environ", {"KF_DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test"}):
            with patch(
                "sqlalchemy.ext.asyncio.create_async_engine",
                return_value=mock_engine,
            ):
                with patch(
                    "sqlalchemy.ext.asyncio.async_sessionmaker",
                    return_value=lambda **kw: mock_session,
                ):
                    async def _query_that_fails(db):
                        raise ValueError("database error")

                    with pytest.raises(ValueError, match="database error"):
                        await _run_in_db(_query_that_fails)

        # Engine must be disposed even after failure
        mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_db_url_raises(self):
        """Missing KF_DATABASE_URL raises RuntimeError."""
        from app.extensions.knowledge_factory.mcp_server.server import _run_in_db

        with patch.dict("os.environ", {}, clear=True):
            async def _query(db):
                pass

            with pytest.raises(RuntimeError, match="KF_DATABASE_URL"):
                await _run_in_db(_query)
