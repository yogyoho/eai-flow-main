"""Law system-KB registration tests — owner fixed to admin (EAI-CUSTOM).

系统级法规标准库由 init-ragflow / ragflow-status 自动注册 / sync-all 创建，
owner 必须固定为 bootstrap admin（admin@eai-flow.com），不得是触发操作时
的登录用户——否则测试/临时账号被软删后会产生孤儿 owner（如 bug-1097 相关）。
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.extensions.law.service import LawService
from app.extensions.models import KnowledgeBase

ADMIN_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()


def _fake_config():
    """Minimal config: only ``law.dataset_display_info`` is read here."""
    return SimpleNamespace(
        law=SimpleNamespace(
            dataset_display_info={
                "ragflow-laws-legal": SimpleNamespace(
                    name="法规标准库 — 法律/法规/规章",
                    description="法律、行政法规和部门规章知识库",
                ),
            }
        )
    )


def _db_with_execute_results(*results):
    """AsyncMock db whose awaited ``execute()`` yields results in order.

    Each awaited ``db.execute(...)`` returns a plain MagicMock whose
    ``scalar_one_or_none()`` returns the matching result.
    """
    db = AsyncMock()
    db.add = MagicMock()
    mocks = []
    for r in results:
        rm = MagicMock()
        rm.scalar_one_or_none.return_value = r
        mocks.append(rm)
    db.execute.side_effect = mocks
    return db


@patch("app.extensions.law.service.get_extensions_config")
@pytest.mark.asyncio
async def test_ensure_kb_registered_owner_fixed_to_admin(mock_config):
    """系统级法规标准库创建时 owner 固定为 admin，忽略调用方传入的 owner_id。"""
    mock_config.return_value = _fake_config()
    # 第 1 次 execute: admin 查找 → admin id；第 2 次: 已有 KB 检查 → 无记录
    db = _db_with_execute_results(ADMIN_ID, None)

    ok = await LawService._ensure_kb_registered(
        db,
        owner_id=OTHER_USER_ID,
        kb_name="ragflow-laws-legal",
        ragflow_dataset_id="ds-1",
        chunk_method="laws",
    )

    assert ok is True
    assert db.execute.await_count == 2  # admin lookup + existing-KB check
    created = db.add.call_args.args[0]
    assert isinstance(created, KnowledgeBase)
    assert created.owner_id == ADMIN_ID
    assert created.access_type == "public"


@patch("app.extensions.law.service.get_extensions_config")
@pytest.mark.asyncio
async def test_ensure_kb_registered_falls_back_when_admin_missing(mock_config):
    """找不到 admin 用户时回退调用方传入的 owner_id（不因解析失败而崩溃）。"""
    mock_config.return_value = _fake_config()
    db = _db_with_execute_results(None, None)  # 无 admin；无已有 KB

    ok = await LawService._ensure_kb_registered(
        db,
        owner_id=OTHER_USER_ID,
        kb_name="ragflow-laws-legal",
        ragflow_dataset_id="ds-1",
        chunk_method="laws",
    )

    assert ok is True
    created = db.add.call_args.args[0]
    assert created.owner_id == OTHER_USER_ID
