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


# ---- 无线程文档：用户级图片上传/读取（EAI-CUSTOM，docmgr 直接新建的文档无 source_thread_id） ----


def _patch_user_fs(monkeypatch, tmp_path):
    """把用户级图片目录解析指到 tmp_path，端点不碰真实文件系统。"""
    img_dir = tmp_path / "docmgr-images"
    monkeypatch.setattr(docmgr_routers, "Paths", lambda: None)
    monkeypatch.setattr(docmgr_routers, "_user_images_dir", lambda paths, uid: img_dir)
    return img_dir


def test_user_image_routes_registered():
    assert ("/api/extensions/docmgr/images", "POST") in _routes()
    assert ("/api/extensions/docmgr/images/{name}", "GET") in _routes()


def _route(path: str):
    return next(r for r in router.routes if getattr(r, "path", "") == path)


def test_user_image_routes_gated():
    """POST 挂 doc:upload 门，GET 挂 doc:read 门。"""
    post = _route("/api/extensions/docmgr/images")
    assert any(c.cell_contents == "doc:upload" for dep in post.dependant.dependencies for c in (getattr(dep.call, "__closure__", None) or []))
    get = _route("/api/extensions/docmgr/images/{name}")
    assert any(c.cell_contents == "doc:read" for dep in get.dependant.dependencies for c in (getattr(dep.call, "__closure__", None) or []))


@pytest.mark.asyncio
async def test_user_upload_creates_dir_writes_file_and_returns_url(tmp_path, monkeypatch):
    img_dir = _patch_user_fs(monkeypatch, tmp_path)  # 目录不存在——首次上传应自动创建
    resp = await docmgr_routers.upload_user_image(_upload(b"\x89PNG-fake", "shot.png", "image/png"), current_user=_FakeUser())
    name = resp.url.rsplit("/", 1)[-1]
    f = img_dir / name
    assert f.read_bytes() == b"\x89PNG-fake"
    assert len(name) == 16 and name.endswith(".png")
    assert resp.url == f"/api/extensions/docmgr/images/{name}"


@pytest.mark.asyncio
async def test_user_upload_rejects_unsupported_type(tmp_path, monkeypatch):
    img_dir = _patch_user_fs(monkeypatch, tmp_path)
    with pytest.raises(HTTPException) as ei:
        await docmgr_routers.upload_user_image(_upload(b"<svg/>", "evil.svg", "image/svg+xml"), current_user=_FakeUser())
    assert ei.value.status_code == 415
    assert not img_dir.exists()


@pytest.mark.asyncio
async def test_user_get_serves_file(tmp_path, monkeypatch):
    _patch_user_fs(monkeypatch, tmp_path)
    up = await docmgr_routers.upload_user_image(_upload(b"\x89PNG-fake", "shot.png", "image/png"), current_user=_FakeUser())
    name = up.url.rsplit("/", 1)[-1]
    resp = await docmgr_routers.get_user_image(name, current_user=_FakeUser())
    assert str(resp.path).endswith(name)
    assert resp.media_type == "image/png"


@pytest.mark.asyncio
async def test_user_get_rejects_traversal_and_unknown_names(tmp_path, monkeypatch):
    """name 只放行服务端生成的 12hex+白名单后缀；穿越/陌生名一律 404。"""
    _patch_user_fs(monkeypatch, tmp_path)
    for bad in ("../../evil.png", "deadbeef.png", "aaaaaaaaaaaa.svg", "aaaaaaaaaaaa.png"):
        with pytest.raises(HTTPException) as ei:
            await docmgr_routers.get_user_image(bad, current_user=_FakeUser())
        assert ei.value.status_code == 404


# ---- Word 导出图片 URL→字节解析（_make_image_fetcher，EAI-CUSTOM） ----


def test_image_fetcher_resolves_user_and_thread_urls(tmp_path, monkeypatch):
    """fetcher 白名单两种 URL：用户级 docmgr-images 与线程 outputs/images；其余 None。"""
    user_dir = tmp_path / "docmgr-images"
    user_dir.mkdir()
    thread_dir = tmp_path / "user-data"
    thread_dir.mkdir()
    monkeypatch.setattr(docmgr_routers, "Paths", lambda: None)
    monkeypatch.setattr(docmgr_routers, "_user_images_dir", lambda paths, uid: user_dir)
    monkeypatch.setattr(docmgr_routers, "_resolve_thread_sandbox_dir", lambda paths, tid, uid: thread_dir)
    (user_dir / "aaaaaaaaaaaa.png").write_bytes(b"USERPNG")
    tdir = thread_dir / "outputs" / "images"
    tdir.mkdir(parents=True)
    (tdir / "bbbbbbbbbbbb.jpg").write_bytes(b"THREADJPG")

    fetch = docmgr_routers._make_image_fetcher("uid-1")
    assert fetch("/api/extensions/docmgr/images/aaaaaaaaaaaa.png") == b"USERPNG"
    assert fetch("/api/threads/t-1/artifacts/mnt/user-data/outputs/images/bbbbbbbbbbbb.jpg") == b"THREADJPG"
    assert fetch("/api/extensions/docmgr/images/cccccccccccc.png") is None  # 文件不存在
    assert fetch("https://evil.example/x.png") is None  # 非白名单 URL
    assert fetch("/api/extensions/docmgr/images/..%2fevil.png") is None  # 穿越一律不认


# ---- bug-3004：SKILL 相对引用 images/{12hex}.png 经 source_thread_id 解析（EAI-CUSTOM） ----


def test_image_fetcher_resolves_relative_ref_via_source_thread(tmp_path, monkeypatch):
    """export 时 agent 只写得出 images/xxx.png（不知道 thread_id）；fetcher 用 AIDocument.source_thread_id 兜底解析。"""
    thread_dir = tmp_path / "user-data"
    img_dir = thread_dir / "outputs" / "images"
    img_dir.mkdir(parents=True)
    monkeypatch.setattr(docmgr_routers, "Paths", lambda: None)
    monkeypatch.setattr(docmgr_routers, "_user_images_dir", lambda paths, uid: tmp_path / "docmgr-images")
    monkeypatch.setattr(docmgr_routers, "_resolve_thread_sandbox_dir", lambda paths, tid, uid: thread_dir)
    (img_dir / "08bb824f44bb.png").write_bytes(b"RELPNG")

    fetch = docmgr_routers._make_image_fetcher("uid-1", source_thread_id="t-9")
    assert fetch("images/08bb824f44bb.png") == b"RELPNG"  # SKILL.md 写的裸相对引用
    assert fetch("/mnt/user-data/outputs/images/08bb824f44bb.png") == b"RELPNG"  # 带虚拟前缀的等价形式
    assert fetch("images/999999999999.png") is None  # 文件不存在
    assert fetch("images/notahexname.png") is None  # 非 12hex 名不认
    assert fetch("images/../../evil.png") is None  # 穿越一律不认
    no_thread = docmgr_routers._make_image_fetcher("uid-1")  # 无 source_thread_id（线程外导出）→ 相对引用解析不了
    assert no_thread("images/08bb824f44bb.png") is None


def test_image_fetcher_coerces_non_str_ids(tmp_path, monkeypatch):
    """EAI-CUSTOM (bug-3004 回归): extensions 鉴权给出 asyncpg 原生 UUID（非 str）时，
    fetcher 必须自行 str() 落地，否则 paths._validate_user_id 的正则抛 TypeError →
    所有图片降级为字面文本（E2E 实测 docx 零 media 的根因）。"""
    import uuid as _uuid

    thread_dir = tmp_path / "user-data"
    img_dir = thread_dir / "outputs" / "images"
    img_dir.mkdir(parents=True)
    monkeypatch.setattr(docmgr_routers, "Paths", lambda: None)
    monkeypatch.setattr(docmgr_routers, "_user_images_dir", lambda paths, uid: tmp_path / "docmgr-images")
    seen: list[object] = []

    def _fake_resolve(paths, tid, uid):
        seen.extend([tid, uid])
        return thread_dir

    monkeypatch.setattr(docmgr_routers, "_resolve_thread_sandbox_dir", _fake_resolve)
    (img_dir / "08bb824f44bb.png").write_bytes(b"UUIDPNG")

    uid_obj = _uuid.UUID("f8766d55-2b1b-422e-a945-5fcf268a8a39")
    tid_obj = _uuid.UUID("5f3a42ff-f893-470a-b468-85d660dfac92")
    fetch = docmgr_routers._make_image_fetcher(uid_obj, source_thread_id=tid_obj)
    assert fetch("images/08bb824f44bb.png") == b"UUIDPNG"
    assert seen[-2] == str(tid_obj) and seen[-1] == str(uid_obj)  # 落到 resolver 前已 str()
