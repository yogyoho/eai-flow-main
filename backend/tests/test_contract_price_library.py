"""合同文件库（cpa v3, spec 2026-10-14 §1）：表注册 + 端点编排 + scanner 跳过。

表注册用共享 Base 断言；端点编排用 asyncio.run 直调路由函数 +
monkeypatch crud/storage（镜像 test_contract_price_document_file.py 的模式），
不需要真实 DB / MinIO。
"""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.extensions.contract_price  # noqa: F401 — 导入即注册模型
from app.extensions.contract_price import crud as cpa_crud
from app.extensions.contract_price import storage as cpa_storage
from app.extensions.contract_price.routers import (
    analyze_library_file,
    delete_library_folder_endpoint,
    library_file_content,
    list_library_files_endpoint,
    update_library_folder,
    upload_library_files,
)


def test_library_tables_registered_on_shared_base():
    from app.extensions.database import Base

    assert {"cpa_library_folders", "cpa_library_files"} <= set(Base.metadata.tables)


def test_router_exposes_library_area():
    from app.extensions.contract_price import router

    paths = {r.path for r in router.routes}
    base = "/api/extensions/contract-price"
    assert f"{base}/library/folders" in paths
    assert f"{base}/library/files" in paths
    assert f"{base}/library/files/upload" in paths
    assert f"{base}/library/files/{{file_id}}/content" in paths
    assert f"{base}/library/files/{{file_id}}/items" in paths
    assert f"{base}/library/files/{{file_id}}/analyze" in paths


def test_library_key_shape():
    key = cpa_storage.library_key("f-1", "a" * 64, "合同 A.pdf")
    assert key.startswith("library/f-1/")
    assert key.endswith("_合同 A.pdf")
    assert "a" * 16 in key  # hash 前 16 位
    assert cpa_storage.library_key("f-1", "a" * 64, "x/y.pdf").count("/") == 2  # 文件名里的 / 被替换


def test_copy_object_uses_server_side_copy(monkeypatch):
    captured = {}

    class _FakeMinio:
        def copy_object(self, bucket, dst, src):
            # minio 7.2.x CopySource 暴露 bucket_name / object_name（无 .bucket 别名）
            captured.update(bucket=bucket, dst=dst, src_bucket=src.bucket_name, src_key=src.object_name)

    monkeypatch.setattr(cpa_storage, "_client", lambda: _FakeMinio())
    uri = cpa_storage.copy_object("library/f1/abc_合同.pdf", "合同B.pdf")
    assert captured == {
        "bucket": "cpa-contracts",
        "dst": "合同B.pdf",
        "src_bucket": "cpa-contracts",
        "src_key": "library/f1/abc_合同.pdf",
    }
    assert uri == "s3://cpa-contracts/合同B.pdf"


# ---- Task 5: 路由编排测试（asyncio.run 直调 + monkeypatch crud/storage）----


class _Body:
    """PATCH body 桩: model_dump(**kw) 返回预置 fields。"""

    def __init__(self, fields):
        self._f = fields

    def model_dump(self, **_kw):
        return dict(self._f)


def _lf(**kw):
    base = dict(
        id=uuid4(),
        folder_id=None,
        file_name="合同B.pdf",
        storage_key="library/f1/abc_合同B.pdf",
        file_hash="h" * 64,
        file_size=100,
        file_type="pdf",
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _DB:
    async def get(self, model, obj_id):
        return None


def test_analyze_already_parsed_short_circuits(monkeypatch):
    lf = _lf()
    doc = SimpleNamespace(id=uuid4(), file_name="原件.pdf", parse_status="parsed", file_hash=lf.file_hash)
    monkeypatch.setattr(cpa_crud, "get_library_file", _async_returning(lf))
    monkeypatch.setattr(cpa_crud, "find_parsed_document_by_hash", _async_returning(doc))
    called = []
    monkeypatch.setattr(cpa_storage, "copy_object", lambda *a: called.append(a))

    out = asyncio.run(analyze_library_file(lf.id, db=_DB(), _=None))
    assert out.status == "already" and out.document_id == doc.id
    assert called == []  # 已解析 → 不拷贝


def test_analyze_name_conflict_diff_content_409(monkeypatch):
    lf = _lf()
    monkeypatch.setattr(cpa_crud, "get_library_file", _async_returning(lf))
    monkeypatch.setattr(cpa_crud, "find_parsed_document_by_hash", _async_returning(None))
    monkeypatch.setattr(
        cpa_crud,
        "find_document_by_storage_key",
        _async_returning(SimpleNamespace(file_name="合同B.pdf", file_hash="x" * 64)),
    )

    with pytest.raises(HTTPException) as ei:
        asyncio.run(analyze_library_file(lf.id, db=_DB(), _=None))
    assert ei.value.status_code == 409


def test_analyze_queued_copies_to_scan_area(monkeypatch):
    lf = _lf()
    monkeypatch.setattr(cpa_crud, "get_library_file", _async_returning(lf))
    monkeypatch.setattr(cpa_crud, "find_parsed_document_by_hash", _async_returning(None))
    monkeypatch.setattr(cpa_crud, "find_document_by_storage_key", _async_returning(None))
    copied = {}
    monkeypatch.setattr(cpa_storage, "copy_object", lambda src, dst: copied.update(src=src, dst=dst))
    pending = {}
    monkeypatch.setattr(cpa_crud, "create_pending_document", _async_capture(pending))

    out = asyncio.run(analyze_library_file(lf.id, db=_DB(), _=None))
    assert out.status == "queued"
    assert copied == {"src": lf.storage_key, "dst": lf.file_name}
    assert pending["kwargs"]["file_hash"] == lf.file_hash


def test_upload_reuses_same_folder_same_hash(monkeypatch):
    dup = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(cpa_crud, "find_library_duplicate", _async_returning(dup))

    class _F:
        filename = "a.pdf"
        content_type = "application/pdf"

        async def read(self):
            return b"%PDF"

    out = asyncio.run(upload_library_files(folder_id="", files=[_F()], db=_DB(), _=None))
    assert out["items"][0]["reused"] is True and out["items"][0]["file_id"] == dup.id


def test_upload_rejects_non_pdf_docx():
    class _F:
        filename = "a.txt"
        content_type = "text/plain"

        async def read(self):
            return b"x"

    out = asyncio.run(upload_library_files(folder_id="", files=[_F()], db=_DB(), _=None))
    assert "仅接受" in out["items"][0]["error"]


def test_folder_delete_nonempty_409(monkeypatch):
    monkeypatch.setattr(cpa_crud, "delete_library_folder", _async_returning(False))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(delete_library_folder_endpoint(uuid4(), db=_DB(), _=None))
    assert ei.value.status_code == 409


def test_folder_update_cycle_guard_422(monkeypatch):
    """环防护: 移到自身后代下 → crud ValueError → 路由 422。"""
    monkeypatch.setattr(
        cpa_crud,
        "update_library_folder",
        _raising(ValueError("不能把文件夹移动到自己的子文件夹下")),
    )
    with pytest.raises(HTTPException) as ei:
        asyncio.run(update_library_folder(uuid4(), _Body({"parent_id": str(uuid4())}), db=_DB(), _=None))
    assert ei.value.status_code == 422


def test_content_inline_for_pdf(monkeypatch):
    lf = _lf()
    monkeypatch.setattr(cpa_storage, "get_object", lambda k: b"%PDF-1.7")

    class _GetDB:
        async def get(self, model, obj_id):
            return lf

    resp = asyncio.run(library_file_content(lf.id, db=_GetDB(), _=None))
    assert resp.headers["content-disposition"].startswith("inline;")
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]


def _async_returning(value):
    async def _fn(*a, **kw):
        return value

    return _fn


def _async_capture(sink):
    async def _fn(*a, **kw):
        sink["kwargs"] = kw
        return SimpleNamespace(id=uuid4())

    return _fn


def _raising(exc):
    async def _fn(*a, **kw):
        raise exc

    return _fn


# ---- 质量审查 Task 5 必须项: 环防护 crud 层直测 + upload 路径段校验 ----


class _FakeFolderSession:
    """crud.update_library_folder 直调桩: get 按预置 id→行 返回;commit/refresh no-op。"""

    def __init__(self, rows):
        self._rows = rows

    async def get(self, model, obj_id):
        return self._rows.get(obj_id)

    async def commit(self):
        pass

    async def refresh(self, row):
        pass


def _folder(fid, parent_id=None):
    return SimpleNamespace(id=fid, parent_id=parent_id, name="旧名")


def test_crud_update_folder_cycle_guard_direct_hit():
    """① new_parent 祖先链命中 folder_id → ValueError。"""
    fid, mid, top = uuid4(), uuid4(), uuid4()
    session = _FakeFolderSession({fid: _folder(fid), mid: _folder(mid, fid), top: _folder(top, mid)})
    with pytest.raises(ValueError, match="不能把文件夹移动到自己的子文件夹下"):
        asyncio.run(cpa_crud.update_library_folder(session, fid, {"parent_id": top}))


def test_crud_update_folder_chain_to_root_updates_normally():
    """② 链正常到根（parent_id=None）→ 正常更新不抛错。"""
    fid, target = uuid4(), uuid4()
    row = _folder(fid, target)
    session = _FakeFolderSession({fid: row, target: _folder(target)})  # target.parent_id=None → 链到根
    out = asyncio.run(cpa_crud.update_library_folder(session, fid, {"parent_id": target, "name": "新名"}))
    assert out.parent_id == target and out.name == "新名"


def test_crud_update_folder_over_64_depth_raises():
    """③ >64 层链（永不触根）→ ValueError('文件夹层级异常')。"""
    fid = uuid4()
    rows = {fid: _folder(fid)}
    cur = uuid4()
    head = cur
    for _ in range(70):
        nxt = uuid4()
        rows[cur] = _folder(cur, nxt)
        cur = nxt
    session = _FakeFolderSession(rows)
    with pytest.raises(ValueError, match="文件夹层级异常"):
        asyncio.run(cpa_crud.update_library_folder(session, fid, {"parent_id": head}))


def test_upload_rejects_bad_path_segment():
    class _F:
        filename = "a.pdf"
        content_type = "application/pdf"

        async def read(self):
            return b"%PDF"

    out = asyncio.run(upload_library_files(folder_id="", paths='["x/../a.pdf"]', files=[_F()], db=_DB(), _=None))
    assert out["items"][0]["error"] == "路径段非法: .."


def test_upload_rejects_over_32_segments():
    class _F:
        filename = "a.pdf"
        content_type = "application/pdf"

        async def read(self):
            return b"%PDF"

    deep = "/".join(f"d{i}" for i in range(33)) + "/a.pdf"
    out = asyncio.run(upload_library_files(folder_id="", paths=json.dumps([deep]), files=[_F()], db=_DB(), _=None))
    assert out["items"][0]["error"] == "子目录层级过深（>32 段）"


# ---- 质量审查 Task 5 清理项: analyze 进行中文案 + folder_id UUID 422 ----


def test_analyze_pending_doc_reports_in_progress(monkeypatch):
    """parse_status pending/parsing → 「已有解析任务进行中」而非误报「已解析过」。"""
    lf = _lf()
    doc = SimpleNamespace(id=uuid4(), file_name="原件.pdf", parse_status="parsing", file_hash=lf.file_hash)
    monkeypatch.setattr(cpa_crud, "get_library_file", _async_returning(lf))
    monkeypatch.setattr(cpa_crud, "find_parsed_document_by_hash", _async_returning(doc))
    called = []
    monkeypatch.setattr(cpa_storage, "copy_object", lambda *a: called.append(a))

    out = asyncio.run(analyze_library_file(lf.id, db=_DB(), _=None))
    assert out.status == "already" and "解析任务进行中" in out.message
    assert called == []  # 进行中 → 不重复拷贝入队


@pytest.mark.parametrize("status", ["failed", "needs_review"])
def test_analyze_failed_doc_requeues(monkeypatch, status):
    """质量审查跨层#5: find_parsed_document_by_hash 不过滤状态——failed/needs_review
    不得被「已解析过」短路，应重新排队（copy_object + create_pending_document 按
    storage_uri upsert 复用同名行＝重试语义）。"""
    lf = _lf()
    doc = SimpleNamespace(id=uuid4(), file_name="原件.pdf", parse_status=status, file_hash=lf.file_hash)
    monkeypatch.setattr(cpa_crud, "get_library_file", _async_returning(lf))
    monkeypatch.setattr(cpa_crud, "find_parsed_document_by_hash", _async_returning(doc))
    monkeypatch.setattr(cpa_crud, "find_document_by_storage_key", _async_returning(None))
    copied = {}
    monkeypatch.setattr(cpa_storage, "copy_object", lambda src, dst: copied.update(src=src, dst=dst))
    pending = {}
    monkeypatch.setattr(cpa_crud, "create_pending_document", _async_capture(pending))

    out = asyncio.run(analyze_library_file(lf.id, db=_DB(), _=None))
    assert out.status == "queued", status
    assert copied == {"src": lf.storage_key, "dst": lf.file_name}, status
    assert pending["kwargs"]["file_hash"] == lf.file_hash, status


def test_list_files_bad_folder_id_422():
    with pytest.raises(HTTPException) as ei:
        asyncio.run(list_library_files_endpoint(folder_id="not-a-uuid", db=_DB(), _=None))
    assert ei.value.status_code == 422


def test_upload_bad_folder_id_422():
    with pytest.raises(HTTPException) as ei:
        asyncio.run(upload_library_files(folder_id="nope", files=[], db=_DB(), _=None))
    assert ei.value.status_code == 422
