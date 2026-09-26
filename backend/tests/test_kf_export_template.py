"""Tests for GET /api/kf/templates/{id}/export Content-Disposition header.

回归:裸中文模板名直塞 Content-Disposition,starlette latin-1 编码 header 时
UnicodeEncodeError → 500,浏览器报"无法从网站上提取文件"而前端 toast 仍报成功。
修复:RFC 5987 filename*=UTF-8''(与 docmgr/contract_price 同款)。
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.extensions.knowledge_factory.routers import export_template

TEMPLATE_ID = "1ab84079-d885-477e-ad94-097e6552aa2a"


def _template(name="煤炭挖掘_煤矿操作规程报告_模板", version="v1.0"):
    t = MagicMock()
    t.id = TEMPLATE_ID
    t.name = name
    t.domain = "eia_report"
    t.version = version
    return t


@pytest.mark.asyncio
async def test_export_chinese_filename_uses_rfc5987():
    """中文文件名 → header 必须 latin-1 可编码且带 filename*=UTF-8''。"""
    with (
        patch(
            "app.extensions.knowledge_factory.routers.TemplateService.get_template",
            new=AsyncMock(return_value=_template()),
        ),
        patch(
            "app.extensions.knowledge_factory.routers.export_template_json",
            return_value=b'{"sections": []}',
        ),
    ):
        resp = await export_template(UUID(TEMPLATE_ID), db=AsyncMock(), current_user=MagicMock())

    header = resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in header
    # 回归锚点:header 值必须能 latin-1 编码(ASGI 层就是这么发的)
    header.encode("latin-1")
    assert "template.json" in header  # ASCII 回退名


@pytest.mark.asyncio
async def test_export_ascii_filename_still_downloads():
    with (
        patch(
            "app.extensions.knowledge_factory.routers.TemplateService.get_template",
            new=AsyncMock(return_value=_template(name="coal-plan", version="v1")),
        ),
        patch(
            "app.extensions.knowledge_factory.routers.export_template_json",
            return_value=b"{}",
        ),
    ):
        resp = await export_template(UUID(TEMPLATE_ID), db=AsyncMock(), current_user=MagicMock())
    assert "attachment" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_export_missing_snapshot_404():
    with (
        patch(
            "app.extensions.knowledge_factory.routers.TemplateService.get_template",
            new=AsyncMock(return_value=_template()),
        ),
        patch(
            "app.extensions.knowledge_factory.routers.export_template_json",
            return_value=None,
        ),
    ):
        with pytest.raises(HTTPException) as ei:
            await export_template(UUID(TEMPLATE_ID), db=AsyncMock(), current_user=MagicMock())
    assert ei.value.status_code == 404
    assert "发布" in ei.value.detail  # 提示 draft 未发布 → 无快照
