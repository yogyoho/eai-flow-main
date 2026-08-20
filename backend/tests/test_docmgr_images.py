"""Tests for personal-doc image upload endpoint (BlockNote uploadFile backend, EAI-CUSTOM)."""

import io
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

import app.extensions.docmgr.routers as docmgr_routers
from app.extensions.docmgr.routers import router


class _FakeUser:
    id = uuid4()


def _routes():
    return {(r.path, m) for r in router.routes for m in (getattr(r, "methods", None) or set())}


def _upload(data: bytes, filename: str, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _patch_fs(monkeypatch, tmp_path):
    """把线程目录解析与 Paths() 都指到 tmp_path，端点不碰真实文件系统。"""
    user_data = tmp_path / "user-data"
    user_data.mkdir()  # 模拟已存在的线程目录（存在性门只放行已存在目录）
    monkeypatch.setattr(docmgr_routers, "Paths", lambda: None)
    monkeypatch.setattr(
        docmgr_routers,
        "_resolve_thread_sandbox_dir",
        lambda paths, tid, uid: user_data,
    )
    return user_data


def test_image_route_registered():
    """路由必须注册，否则前端 404。"""
    assert ("/api/extensions/docmgr/threads/{thread_id}/images", "POST") in _routes()


def test_image_route_gated_by_doc_upload():
    """端点必须挂 doc:upload 权限门（require_permission 闭包 cell 含权限名）。"""
    route = next(r for r in router.routes if getattr(r, "path", "") == "/api/extensions/docmgr/threads/{thread_id}/images")
    assert any(c.cell_contents == "doc:upload" for dep in route.dependant.dependencies for c in (getattr(dep.call, "__closure__", None) or []))


@pytest.mark.asyncio
async def test_upload_image_writes_file_and_returns_url(tmp_path, monkeypatch):
    user_data = _patch_fs(monkeypatch, tmp_path)
    resp = await docmgr_routers.upload_thread_image("tid-1", _upload(b"\x89PNG-fake", "shot.png", "image/png"), current_user=_FakeUser())
    name = resp.url.rsplit("/", 1)[-1]
    f = user_data / "outputs" / "images" / name
    assert f.read_bytes() == b"\x89PNG-fake"
    assert name.endswith(".png") and len(name) == 16  # 12 hex + ".png"
    assert resp.url == f"/api/threads/tid-1/artifacts/mnt/user-data/outputs/images/{name}"


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_type(tmp_path, monkeypatch):
    _patch_fs(monkeypatch, tmp_path)  # SVG 走白名单拒绝，不应写任何文件
    with pytest.raises(HTTPException) as ei:
        await docmgr_routers.upload_thread_image("tid-1", _upload(b"<svg/>", "evil.svg", "image/svg+xml"), current_user=_FakeUser())
    assert ei.value.status_code == 415
    assert not (tmp_path / "user-data" / "outputs").exists()


@pytest.mark.asyncio
async def test_upload_rejects_oversize(tmp_path, monkeypatch):
    _patch_fs(monkeypatch, tmp_path)
    big = b"x" * (docmgr_routers._IMAGE_MAX_BYTES + 1)
    with pytest.raises(HTTPException) as ei:
        await docmgr_routers.upload_thread_image("tid-1", _upload(big, "big.png", "image/png"), current_user=_FakeUser())
    assert ei.value.status_code == 413


@pytest.mark.asyncio
async def test_upload_filename_traversal_is_ignored(tmp_path, monkeypatch):
    """filename 穿越（../../evil.png）不影响落盘——服务端生成 uuid 名，路径钉死在 outputs/images/ 下。"""
    user_data = _patch_fs(monkeypatch, tmp_path)
    resp = await docmgr_routers.upload_thread_image("tid-1", _upload(b"\x89PNG-fake", "../../evil.png", "image/png"), current_user=_FakeUser())
    name = resp.url.rsplit("/", 1)[-1]
    assert len(name) == 16 and name.endswith(".png")  # 12 hex + ".png"，无路径分量
    written = list((user_data / "outputs" / "images").iterdir())
    assert [f.name for f in written] == [name]
    assert written[0].read_bytes() == b"\x89PNG-fake"
    assert not (tmp_path / "evil.png").exists()  # 穿越目标未被创建


@pytest.mark.asyncio
async def test_upload_404_when_thread_dir_missing(tmp_path, monkeypatch):
    """线程目录不存在时 404（存在性门），且不写任何文件。"""
    user_data = _patch_fs(monkeypatch, tmp_path)
    user_data.rmdir()  # 制造"线程目录不存在"
    with pytest.raises(HTTPException) as ei:
        await docmgr_routers.upload_thread_image("tid-1", _upload(b"\x89PNG-fake", "shot.png", "image/png"), current_user=_FakeUser())
    assert ei.value.status_code == 404
    assert not user_data.exists()
