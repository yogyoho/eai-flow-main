"""Tests for project MCP bridge fix — dead refs, commit, status validation, derived stage.

EAI-CUSTOM: 桥修复回归测试（设计文档 Success Criteria 5）。
纯单元测试，不依赖 DB：
- (a) 5 工具 handler 无死引用（可 import + 函数可调用）
- (b) write_chapter 的 status 集合成员校验（非法值被拒）
- (c) ProjectOut 含 derived_stage（P2：current_stage 已删除）
- (d) mcp.py 的 _run_in_db 含 commit
"""

import asyncio
import inspect
import os

import pytest

from app.extensions.project import mcp


@pytest.fixture(autouse=True)
def _fake_db_url(monkeypatch):
    """让 _run_in_db 能走到连接阶段（验证逻辑在 DB 调用之前执行）。"""
    monkeypatch.setenv("PROJECT_DB_URL", "postgresql+asyncpg://x:x@localhost:1/nonexistent")


class TestNoDeadRefs:
    """5 工具 handler 引用的 service 函数都存在。"""

    def test_service_helpers_exist(self):
        """_get_chapter_or_404 / get_outline_tree 已在 service.py 定义。"""
        from app.extensions.project import service
        assert hasattr(service, "_get_chapter_or_404")
        assert hasattr(service, "get_outline_tree")
        assert hasattr(service, "_get_assigned_names")
        assert hasattr(service, "update_chapter")

    def test_all_tool_handlers_registered(self):
        """MCP 服务器注册了全部 5 个工具。"""
        names = {t.name for t in mcp.TOOLS}
        assert names == {"read_chapter", "write_chapter", "list_chapters", "get_project", "get_chapter_spec"}

    def test_handlers_callable(self):
        """每个 handler 是 async 函数（无 import 期 AttributeError）。"""
        for h in (mcp._handle_read_chapter, mcp._handle_write_chapter, mcp._handle_list_chapters,
                  mcp._handle_get_project, mcp._handle_get_chapter_spec):
            assert inspect.iscoroutinefunction(h), f"{h.__name__} 不是 async"


class TestWriteChapterStatusValidation:
    """断点 4：write_chapter 只在 MCP 边界做集合成员校验。"""

    def test_invalid_status_rejected(self):
        """非法 status（如 approved/editing）返回错误而非入库。"""
        result = asyncio.run(mcp._handle_write_chapter(
            {"chapter_id": "00000000-0000-0000-0000-000000000000", "content": "x", "status": "approved"}
        ))
        text = result[0].text
        assert "非法 status" in text
        assert "approved" in text

    def test_editing_status_rejected(self):
        """状态机不存在的 editing 被拒（断点 4 核心）。"""
        result = asyncio.run(mcp._handle_write_chapter(
            {"chapter_id": "00000000-0000-0000-0000-000000000000", "content": "x", "status": "editing"}
        ))
        assert "非法 status" in result[0].text

    def test_valid_status_passes_validation(self):
        """合法 status（pending/draft/completed）不触发校验拒绝。
        校验在 DB 调用前；合法 status 会走到 _run_in_db 连接失败（RuntimeError/连接错误），
        而非返回"非法 status"——用异常证明校验放行。
        """
        with pytest.raises(Exception):
            asyncio.run(mcp._handle_write_chapter(
                {"chapter_id": "00000000-0000-0000-0000-000000000000", "content": "x", "status": "draft"}
            ))
        # 若 status 非法，会在进入 _run_in_db 前直接返回文本，不会抛异常
        assert True  # 到达 DB 连接阶段 = 校验已放行

    def test_null_status_ok(self):
        """status 缺省合法（仅 content 写入）。"""
        with pytest.raises(Exception):
            asyncio.run(mcp._handle_write_chapter(
                {"chapter_id": "00000000-0000-0000-0000-000000000000", "content": "x"}
            ))
        assert True  # 校验放行，走到 DB 阶段


class TestRunInDbCommits:
    """断点 3：_run_in_db 必须 commit。"""

    def test_run_in_db_source_has_commit(self):
        src = inspect.getsource(mcp._run_in_db)
        assert "session.commit()" in src, "_run_in_db 缺 commit，写入会被回滚"


class TestDerivedStage:
    """P2（ADR 2026-08-02）：current_stage 删除，派生 stage 替代。"""

    def test_project_out_has_derived_stage(self):
        from app.extensions.project.schemas import ProjectOut
        assert "derived_stage" in ProjectOut.model_fields
        assert "current_stage" not in ProjectOut.model_fields

    def test_get_project_passes_derived_stage(self):
        from app.extensions.project.service import get_project
        src = inspect.getsource(get_project)
        assert "derived_stage=" in src, "get_project 未构造 derived_stage"
        assert "current_stage=project.current_stage" not in src, "current_stage 应已删除"

    def test_derive_project_stage_mapping(self):
        from app.extensions.project.service import derive_project_stage
        # setup (no chapters) -> 1; outline confirmed (all pending) -> 2
        assert derive_project_stage("draft", []) == 1
        assert derive_project_stage("draft", ["pending", "pending"]) == 2
        # writing (any draft) -> 3; collab (all >= reviewing) -> 4
        assert derive_project_stage("draft", ["draft", "pending"]) == 3
        assert derive_project_stage("draft", ["reviewing", "approved"]) == 4
        # approval -> 5; approved + all done -> 6; approved + rework -> 4
        assert derive_project_stage("in_review", ["reviewing", "approved"]) == 5
        assert derive_project_stage("approved", ["approved", "approved"]) == 6
        assert derive_project_stage("approved", ["draft", "approved"]) == 4


class TestWriteChapterEnum:
    """断点 4：write_chapter schema enum 对齐。"""

    def test_enum_values(self):
        for tool in mcp.TOOLS:
            if tool.name == "write_chapter":
                status_schema = tool.inputSchema["properties"]["status"]
                assert status_schema["enum"] == ["pending", "draft", "completed"], \
                    f"enum 应为 [pending,draft,completed]，实际 {status_schema['enum']}"
                assert "approved" not in status_schema["enum"], "agent 不得自批"
                assert "editing" not in status_schema["enum"], "editing 状态机不存在"
