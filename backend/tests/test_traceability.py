"""Tests for AI content traceability parsing and missing source detection."""

from app.extensions.workflow.traceability import ParsedSource, find_missing_sources, parse_source_markers


class TestParseSourceMarkers:
    def test_basic_markers(self):
        content = (
            "SO₂市日均浓度为 0.045mg/m³[1]，"
            "低于标准 0.15mg/m³[2]。\n\n"
            "[1] source:rag_retrieval:知识库「监测」→「报告」p.23\n"
            "[2] source:regulation:GB 3095-2012 表2"
        )
        sources = parse_source_markers(content)
        assert len(sources) == 2
        assert sources[0].source_type == "rag_retrieval"
        assert sources[1].source_type == "regulation"

    def test_no_markers(self):
        content = "Plain text without any markers."
        sources = parse_source_markers(content)
        assert len(sources) == 0

    def test_empty_content(self):
        sources = parse_source_markers("")
        assert len(sources) == 0

    def test_marker_without_footnote(self):
        content = "Some text[1] but no footnote."
        sources = parse_source_markers(content)
        # [1] is not in footnotes dict, so it should not produce a source
        assert len(sources) == 0

    def test_multiple_blocks(self):
        content = "Block A[1]\n\nBlock B[2]\n\n[1] source:ai:thread-123\n[2] source:human:user-456"
        sources = parse_source_markers(content)
        assert len(sources) == 2
        assert sources[0].block_index == 0  # Block A
        assert sources[1].block_index == 1  # Block B

    def test_block_start_index_offset(self):
        content = "Text[1]\n\n[1] source:ai:thread-123"
        sources = parse_source_markers(content, block_start_index=5)
        assert len(sources) == 1
        assert sources[0].block_index == 5

    def test_return_type_is_parsed_source(self):
        content = "Text[1]\n\n[1] source:ai:thread-123"
        sources = parse_source_markers(content)
        assert isinstance(sources[0], ParsedSource)
        assert sources[0].source_ref == "thread-123"
        assert isinstance(sources[0].snippet, str)
        assert len(sources[0].snippet) > 0

    def test_footnote_block_not_counted(self):
        """Footnote-only blocks (starting with [N] source:) should be skipped for block_index."""
        content = "Text[1]\n\n[1] source:ai:thread-123\n\nMore text"
        sources = parse_source_markers(content)
        assert len(sources) == 1
        # The footnote block at index 1 is skipped, so block_index for "More text" is 2
        # but "More text" has no inline markers, so only the first block produces a source
        assert sources[0].block_index == 0


class TestFindMissingSources:
    def test_all_missing(self):
        content = "Block A\n\nBlock B\n\nBlock C"
        missing = find_missing_sources(content)
        assert len(missing) == 3

    def test_none_missing(self):
        content = "Data[1]\n\n[1] source:ai:thread-123"
        missing = find_missing_sources(content)
        assert len(missing) == 0

    def test_partial_missing(self):
        content = "Has source[1]\n\nNo source here\n\n[1] source:ai:thread-123"
        missing = find_missing_sources(content)
        assert len(missing) == 1
        assert missing[0]["block_index"] == 1

    def test_empty_blocks_skipped(self):
        content = "Text[1]\n\n\n\n[1] source:ai:thread-123"
        missing = find_missing_sources(content)
        assert len(missing) == 0

    def test_preview_truncation(self):
        content = "A" * 100
        missing = find_missing_sources(content)
        assert len(missing) == 1
        assert len(missing[0]["preview"]) == 50

    def test_footnote_block_excluded(self):
        """Footnote blocks themselves should not appear as missing."""
        content = "Text[1]\n\n[1] source:ai:thread-123"
        missing = find_missing_sources(content)
        assert len(missing) == 0

    def test_missing_returns_correct_keys(self):
        content = "Unannotated block"
        missing = find_missing_sources(content)
        assert "block_index" in missing[0]
        assert "preview" in missing[0]


class TestAutoParseSources:
    def test_update_chapter_auto_parse(self):
        """update_chapter should auto-parse source markers when content changes."""
        from unittest.mock import AsyncMock, MagicMock, patch

        content_with_markers = (
            "SO₂ 浓度为 0.045mg/m³[1]。\n\n"
            "[1] source:rag_retrieval:知识库「监测」p.23"
        )

        mock_chapter = MagicMock()
        mock_chapter.content = None
        mock_chapter.id = "test-chapter-id"

        async def _test():
            from app.extensions.project.service import _auto_parse_sources

            mock_db = AsyncMock()
            mock_db.execute = AsyncMock()
            mock_db.flush = AsyncMock()
            mock_db.add = MagicMock()

            await _auto_parse_sources(mock_db, "test-chapter-id", content_with_markers)

            mock_db.execute.assert_called_once()
            assert mock_db.add.call_count == 1

        import asyncio

        asyncio.run(_test())
