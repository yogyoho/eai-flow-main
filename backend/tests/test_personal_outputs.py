"""Tests for personal-outputs endpoint and star/share metadata."""

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.extensions.docmgr.service import AIDocumentService


class TestListPersonalOutputs:
    @pytest.mark.asyncio
    async def test_empty_when_no_threads_dir(self, tmp_path: Path):
        user_id = uuid4()
        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(),
                user_id,
            )
        assert result["threads"] == [] and result["total"] == 0

    @pytest.mark.asyncio
    async def test_skips_thread_without_outputs_dir(self, tmp_path: Path):
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        (threads_dir / "t1").mkdir(parents=True)
        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(),
                user_id,
            )
        assert result["threads"] == [] and result["total"] == 0

    @pytest.mark.asyncio
    async def test_total_counts_only_threads_with_visible_files(self, tmp_path: Path):
        """bug-2232 回归：total 只数非空线程（与前端可见文件夹数一致），
        空 outputs 候选线程不进 total；has_more 仍按候选目录数（两个计数单位不同）。"""
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        (threads_dir / "tid-2" / "user-data" / "outputs").mkdir(parents=True)  # 空 outputs
        (threads_dir / "tid-1" / "user-data" / "outputs").mkdir(parents=True)
        (threads_dir / "tid-1" / "user-data" / "outputs" / "a.md").write_text("# a")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(AsyncMock(), user_id, skip=0, limit=1)

        assert result["total"] == 1, "total 不得计入空 outputs 线程"
        assert result["has_more"] is True, "候选 2 个、扫描 1 个后仍应可翻页"
        assert result["next_skip"] == 1
        # bug-3071 mtime 倒序 → 首页扫到最新的 tid-1（有文件）
        assert [t["thread_id"] for t in result["threads"]] == ["tid-1"]

    @pytest.mark.asyncio
    async def test_returns_files_for_thread_with_outputs(self, tmp_path: Path):
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        outputs_dir = threads_dir / "tid-1" / "user-data" / "outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "report.md").write_text("# Report")
        (outputs_dir / "data.csv").write_text("a,b\n1,2")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(),
                user_id,
            )
        assert len(result["threads"]) == 1
        assert result["total"] == 1
        assert result["threads"][0]["thread_id"] == "tid-1"
        names = {f["name"] for f in result["threads"][0]["files"]}
        assert names == {"report.md", "data.csv"}

    @pytest.mark.asyncio
    async def test_skips_hidden_paths(self, tmp_path: Path):
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        outputs_dir = threads_dir / "tid-1" / "user-data" / "outputs"
        hidden_dir = outputs_dir / ".tool-results"
        hidden_dir.mkdir(parents=True)
        (hidden_dir / "large.json").write_text("{}")
        (outputs_dir / "visible.md").write_text("# ok")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(),
                user_id,
            )
        names = {f["name"] for f in result["threads"][0]["files"]}
        assert "visible.md" in names
        assert "large.json" not in names

    @pytest.mark.asyncio
    async def test_fallback_display_name_from_md_file(self, tmp_path: Path):
        """线程无标题 -> fallback 用首个 .md 文件名。"""
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        outputs_dir = threads_dir / "tid-1" / "user-data" / "outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "基地项目消防设计专篇.md").write_text("# doc")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            result = await AIDocumentService.list_personal_outputs(
                AsyncMock(),
                user_id,
            )
        assert result["threads"][0]["display_name"] == "基地项目消防设计专篇"

    @pytest.mark.asyncio
    async def test_next_skip_advances_by_scanned_count_past_empty_threads(self, tmp_path: Path):
        """bug-2225 回归：空 outputs 线程被过滤后返回数 < 扫描数，游标必须按扫描数推进。

        构造 tid-3(有文件) / tid-2(空 outputs) / tid-1(有文件)（无 threads_meta 时按
        outputs mtime 倒序——bug-3071：sqlite→postgres 切换后 threads_meta 停更，
        created_at 全空，回退键=outputs 目录 mtime；目录按 tid-3/tid-2/tid-1 顺序创建，
        tid-1 的文件最后写入 → mtime 最新在前），limit=2。第一页扫描 [tid-1, tid-3]
        两个非空线程全返回，next_skip 必须是 2——旧逻辑按返回数推进会让窗口重叠，
        整窗无新增时滚动加载永久卡死。
        """
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        (threads_dir / "tid-3" / "user-data" / "outputs").mkdir(parents=True)
        (threads_dir / "tid-3" / "user-data" / "outputs" / "a.md").write_text("# a")
        (threads_dir / "tid-2" / "user-data" / "outputs").mkdir(parents=True)  # 空 outputs
        (threads_dir / "tid-1" / "user-data" / "outputs").mkdir(parents=True)
        (threads_dir / "tid-1" / "user-data" / "outputs" / "b.md").write_text("# b")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path

            # 第一页：扫描 2 个线程，仅返回 1 个非空
            page1 = await AIDocumentService.list_personal_outputs(AsyncMock(), user_id, skip=0, limit=2)
            assert page1["next_skip"] == 2, "游标必须按扫描数(2)而非返回数(1)推进"
            assert [t["thread_id"] for t in page1["threads"]] == ["tid-1"]
            assert page1["has_more"] is True

            # 按 next_skip 翻页到达剩余窗口（构造更多空线程时旧逻辑会整窗无新增而卡死）
            page2 = await AIDocumentService.list_personal_outputs(AsyncMock(), user_id, skip=page1["next_skip"], limit=2)
            assert page2["next_skip"] == 3
            assert [t["thread_id"] for t in page2["threads"]] == ["tid-3"]
            assert page2["has_more"] is False

    @pytest.mark.asyncio
    async def test_pagination_never_stalls_on_all_empty_window(self, tmp_path: Path):
        """bug-2225 回归（卡死形态）：整页全是空 outputs 线程时，按 next_skip 翻页仍前进。

        旧前端算法（按返回数推进）在此数据上 skip 永远停在 0，has_more=true，
        滚动加载永远拉不出 tid-1 的文件。
        """
        user_id = uuid4()
        threads_dir = tmp_path / "users" / str(user_id) / "threads"
        for i in range(2, 7):  # tid-6..tid-2 空，tid-1 有文件（thread_id 倒序 → 空的排前）
            (threads_dir / f"tid-{i}" / "user-data" / "outputs").mkdir(parents=True)
        (threads_dir / "tid-1" / "user-data" / "outputs").mkdir(parents=True)
        (threads_dir / "tid-1" / "user-data" / "outputs" / "x.md").write_text("# x")

        with patch("deerflow.config.paths.Paths") as mock_paths:
            mock_paths.return_value.base_dir = tmp_path
            skip, seen, hops = 0, set(), 0
            while hops < 10:
                hops += 1
                page = await AIDocumentService.list_personal_outputs(AsyncMock(), user_id, skip=skip, limit=2)
                seen.update(t["thread_id"] for t in page["threads"])
                if not page["has_more"]:
                    break
                assert page["next_skip"] > skip, f"卡死：skip={skip} 无法前进"
                skip = page["next_skip"]
            assert seen == {"tid-1"}, "按 next_skip 翻页必须能到达全部非空线程"
            assert hops < 10


class TestPersonalDocMetaModel:
    def test_model_tablename(self):
        from app.extensions.models import PersonalDocMeta

        assert PersonalDocMeta.__tablename__ == "personal_doc_meta"
