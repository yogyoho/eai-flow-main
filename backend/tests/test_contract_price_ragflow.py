"""EAI-CUSTOM: 合同价格分析 × RAGFlow 初始化/状态/文件同步 —— ragflow_setup 单测。

httpx seam 镜像 test_knowledge_client_payload.py（monkeypatch httpx.AsyncClient），
配置 seam 镜像 test_contract_price_seed_config.py（monkeypatch crud._config_path →
tmp_path）。真实 RAGFlowClient 走全链路（wire payload 断言含 parse_type/parser_id），
无 extensions DB、无网络；端点用直调路由函数模式（test_contract_price_library.py）。
pytest-asyncio 每测一个新事件循环 → 模块级 _INIT_LOCK 由 autouse 夹具每测换新
（生产为进程单循环，锁常驻）。
"""

import asyncio
import json
import re
import uuid
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

import app.extensions.contract_price  # noqa: F401 — 导入即注册模型
from app.extensions.contract_price import crud as cpa_crud
from app.extensions.contract_price import ragflow_setup
from app.extensions.contract_price import storage as cpa_storage
from app.extensions.contract_price.routers import (
    contract_ragflow_status,
    init_contract_ragflow,
    ragflow_sync_items,
    ragflow_sync_library_file,
    upload_library_files,
)
from app.extensions.knowledge.client import RAGFlowClient

API = "/api/v1"


# ---- fake httpx（_CaptureHttp 的 seam，扩为按路径路由的假服务端） --------------


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=None)

    def json(self):
        return self._payload


class _State:
    """假 RAGFlow 服务端状态：datasets/documents + 全量调用记录。"""

    def __init__(self):
        self.available = True
        self.datasets = {}  # id -> {"id","name","description","document_count","chunk_count"}
        self.documents = {}  # dataset_id -> [{"id","name","run"}]
        self.calls = []  # {"method","path","json","params"}
        self._seq = 0

    def next_id(self, kind):
        self._seq += 1
        return f"{kind}-{self._seq}"

    def posts(self, path_suffix):
        return [c for c in self.calls if c["method"] == "POST" and c["path"].endswith(path_suffix)]


def _dispatch(state, method, url, kwargs):
    if not state.available:
        raise httpx.ConnectError("connection refused")  # 不可达 = 所有路由连接错误（is_available → False）
    path = url.split(API, 1)[1]
    state.calls.append({"method": method, "path": path, "json": kwargs.get("json"), "params": dict(kwargs.get("params") or {})})
    parts = [p for p in path.split("/") if p]
    if parts[0] != "datasets":
        return _Resp({"code": 102, "message": f"unknown route {path}"}, 404)
    if len(parts) == 1:
        if method == "GET":
            name = (kwargs.get("params") or {}).get("name")
            data = [d for d in state.datasets.values() if not name or d["name"] == name]
            return _Resp({"code": 0, "data": data})
        if method == "POST":
            payload = kwargs.get("json") or {}
            ds_id = state.next_id("ds-created")
            state.datasets[ds_id] = {
                "id": ds_id,
                "name": payload.get("name"),
                "description": "",
                "document_count": 0,
                "chunk_count": 0,
            }
            return _Resp({"code": 0, "data": {"id": ds_id}})
    ds_id = parts[1]
    if len(parts) == 2:
        if method == "GET":
            ds = state.datasets.get(ds_id)
            if ds is None:
                return _Resp({"code": 102, "message": "dataset not found"}, 404)
            return _Resp({"code": 0, "data": ds})
        if method == "PUT":
            ds = state.datasets.setdefault(ds_id, {"id": ds_id, "name": None, "document_count": 0, "chunk_count": 0})
            for k in ("name", "description", "permission"):
                if (kwargs.get("json") or {}).get(k) is not None:
                    ds[k] = kwargs["json"][k]
            return _Resp({"code": 0, "data": {"id": ds_id}})
    if len(parts) == 3 and parts[2] == "documents":
        if method == "GET":
            docs = state.documents.get(ds_id, [])
            params = kwargs.get("params") or {}
            page = int(params.get("page") or 1)
            size = int(params.get("page_size") or 30)
            start = (page - 1) * size
            return _Resp({"code": 0, "data": {"docs": docs[start : start + size], "total": len(docs)}})
        if method == "POST":
            filename = (kwargs.get("files") or {}).get("file", ("?",))[0]
            doc = {"id": state.next_id("doc"), "name": filename, "run": "UNSTART"}
            state.documents.setdefault(ds_id, []).append(doc)
            if ds_id in state.datasets:
                state.datasets[ds_id]["document_count"] = len(state.documents[ds_id])
            return _Resp({"code": 0, "data": [doc]})
    if len(parts) == 3 and parts[2] == "chunks" and method == "POST":
        ids = (kwargs.get("json") or {}).get("document_ids") or []
        for d in state.documents.get(ds_id, []):
            if d["id"] in ids:
                d["run"] = "RUNNING"
        return _Resp({"code": 0})
    return _Resp({"code": 102, "message": f"unmatched {method} {path}"}, 404)


class _FakeAsyncClient:
    """httpx.AsyncClient 替身（同 _CaptureHttp：async 上下文管理器 + async 动词）。"""

    def __init__(self, state, *args, **kwargs):
        self._state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        return _dispatch(self._state, "GET", url, kwargs)

    async def post(self, url, **kwargs):
        return _dispatch(self._state, "POST", url, kwargs)

    async def put(self, url, **kwargs):
        return _dispatch(self._state, "PUT", url, kwargs)

    async def patch(self, url, **kwargs):
        return _dispatch(self._state, "PATCH", url, kwargs)


@pytest.fixture
def ragflow_env(monkeypatch, tmp_path):
    """fake httpx + config.json 隔离（crud._config_path → tmp_path）。返回 (state, client)。"""
    state = _State()
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: _FakeAsyncClient(state, *a, **kw))
    monkeypatch.setattr(cpa_crud, "_config_path", lambda: str(tmp_path / "config.json"))
    return state, RAGFlowClient(api_key="ragflow-test-token")


def _async_returning(value):
    async def _fn(*a, **kw):
        return value

    return _fn


@pytest.fixture(autouse=True)
def _fresh_init_lock():
    """asyncio.Lock 首次 acquire 即绑定事件循环（py3.12），而 pytest-asyncio 每测
    换新循环 → 模块级锁必须每测换新，否则第二个 async 测试报
    "bound to a different event loop"。生产网关单循环，锁常驻不受影响。"""
    ragflow_setup._INIT_LOCK = asyncio.Lock()
    yield


# ---- ensure_initialized ------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_initialized_creates_missing_datasets(ragflow_env):
    state, client = ragflow_env
    out = await ragflow_setup.ensure_initialized(client)
    assert [r["status"] for r in out] == ["created", "created"]
    creates = state.posts("/datasets")
    assert len(creates) == 2
    by_name = {c["json"]["name"]: c["json"] for c in creates}
    assert set(by_name) == {ragflow_setup.DATASET_CONTRACT, ragflow_setup.DATASET_GOODS_TABLE}
    for payload in by_name.values():
        assert payload["permission"] == "team"
        assert payload["embedding_model"] == ragflow_setup.EMBEDDING_MODEL
        assert payload["parse_type"] == 1
        assert payload["parser_id"] == "naive"


@pytest.mark.asyncio
async def test_ensure_initialized_persists_config_and_round_trips(ragflow_env):
    state, client = ragflow_env
    out = await ragflow_setup.ensure_initialized(client)
    by_name = {r["name"]: r for r in out}
    cfg = cpa_crud.load_config()
    assert cfg.ragflow_contract_dataset_id == by_name[ragflow_setup.DATASET_CONTRACT]["dataset_id"]
    assert cfg.ragflow_goods_dataset_id == by_name[ragflow_setup.DATASET_GOODS_TABLE]["dataset_id"]
    assert cfg.ragflow_initialized_at  # ISO 时间戳
    # 落盘往返：重新 load（新实例）字段仍在
    assert cpa_crud.load_config().ragflow_contract_dataset_id == cfg.ragflow_contract_dataset_id


@pytest.mark.asyncio
async def test_ensure_initialized_idempotent_second_run_aligned(ragflow_env):
    state, client = ragflow_env
    first = await ragflow_setup.ensure_initialized(client)
    assert [r["status"] for r in first] == ["created", "created"]
    creates_after_first = len(state.posts("/datasets"))
    second = await ragflow_setup.ensure_initialized(client)
    assert [r["status"] for r in second] == ["aligned", "aligned"]
    assert len(state.posts("/datasets")) == creates_after_first  # 零新增 create 调用
    assert [r["dataset_id"] for r in second] == [r["dataset_id"] for r in first]


# ---- collect_status ----------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_status_connected_reports_counts(ragflow_env):
    state, client = ragflow_env
    await ragflow_setup.ensure_initialized(client)
    for ds in state.datasets.values():
        ds["document_count"] = 3
        ds["chunk_count"] = 42
    out = await ragflow_setup.collect_status(client)
    assert out["available"] is True
    assert [d["name"] for d in out["datasets"]] == [
        ragflow_setup.DATASET_CONTRACT,
        ragflow_setup.DATASET_GOODS_TABLE,
    ]
    for d in out["datasets"]:
        assert d["status"] == "connected"
        assert d["document_count"] == 3
        assert d["chunk_count"] == 42
    assert "initialized_at" in out  # 前端「初始化于 …」footer 字段（ensure_initialized 落盘后非 None）
    assert out["initialized_at"]


@pytest.mark.asyncio
async def test_collect_status_unreachable_degrades_without_raising(ragflow_env):
    state, client = ragflow_env
    state.available = False
    out = await ragflow_setup.collect_status(client)
    assert out == {"available": False, "datasets": [], "error": "ragflow unreachable"}


@pytest.mark.asyncio
async def test_collect_status_reports_missing_when_no_datasets(ragflow_env):
    state, client = ragflow_env
    out = await ragflow_setup.collect_status(client)
    assert out["available"] is True
    assert [d["status"] for d in out["datasets"]] == ["missing", "missing"]
    assert out["initialized_at"] is None  # 键恒在（未初始化时为 None）


# ---- sync_file ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_file_auto_inits_uploads_and_parses(ragflow_env):
    state, client = ragflow_env
    out = await ragflow_setup.sync_file(client, filename="合同A.pdf", content=b"%PDF-1.7")
    assert out["status"] == "synced"
    assert out["ragflow_document_id"]
    # 决策 A：sync 隐式 ensure_initialized（两个 create 先行）
    assert len(state.posts("/datasets")) == 2
    # 上传进的是「合同知识库」（配置里的 contract dataset id）
    uploads = state.posts("/documents")
    assert [u["path"] for u in uploads] == [f"/datasets/{out['dataset_id']}/documents"]
    assert cpa_crud.load_config().ragflow_contract_dataset_id == out["dataset_id"]
    parses = state.posts("/chunks")
    assert len(parses) == 1
    assert parses[0]["json"] == {"document_ids": [out["ragflow_document_id"]]}


@pytest.mark.asyncio
async def test_sync_file_already_exists_skips_upload(ragflow_env):
    state, client = ragflow_env
    await ragflow_setup.sync_file(client, filename="合同A.pdf", content=b"%PDF-1.7")
    uploads_after_first = len(state.posts("/documents"))
    out = await ragflow_setup.sync_file(client, filename="合同A.pdf", content=b"%PDF-1.7")
    assert out["status"] == "already_exists"
    assert len(state.posts("/documents")) == uploads_after_first  # 零 upload


@pytest.mark.asyncio
async def test_sync_file_dedupes_existing_name_on_page_two(ragflow_env):
    """150 文档（第一页 100 + 第二页 50）：重名文档在第 2 页也能查出 → already_exists
    （钉住 _list_all_documents 翻页循环，page_size=100 上游上限）。"""
    state, client = ragflow_env
    ds_id = "ds-seed-150"
    state.datasets[ds_id] = {
        "id": ds_id,
        "name": ragflow_setup.DATASET_CONTRACT,
        "description": "",
        "document_count": 150,
        "chunk_count": 0,
    }
    state.documents[ds_id] = [{"id": f"doc-{i:03d}", "name": f"旧合同-{i:03d}.pdf", "run": "DONE"} for i in range(150)]
    state.documents[ds_id][104]["name"] = "合同A.pdf"  # 索引 104 ∈ 第 2 页（100–149）

    out = await ragflow_setup.sync_file(client, filename="合同A.pdf", content=b"%PDF-1.7")

    assert out["status"] == "already_exists"
    assert out["ragflow_document_id"] == "doc-104"
    assert state.posts("/documents") == []  # 零上传
    gets = [c for c in state.calls if c["method"] == "GET" and c["path"].endswith("/documents")]
    assert [g["params"]["page"] for g in gets] == [1, 2]  # 真实翻页: 第一页取满 100 才取第二页


# ---- 配置 schema 往返（ConfigOut 新增字段经 load/save 不丢） -------------------


def test_config_schema_round_trips_ragflow_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(cpa_crud, "_config_path", lambda: str(tmp_path / "config.json"))
    cfg = cpa_crud.load_config()
    cfg.ragflow_contract_dataset_id = "ds-1"
    cfg.ragflow_goods_dataset_id = "ds-2"
    cfg.ragflow_initialized_at = "2026-10-17T00:00:00+00:00"
    cpa_crud.save_config(cfg)
    got = cpa_crud.load_config()
    assert got.ragflow_contract_dataset_id == "ds-1"
    assert got.ragflow_goods_dataset_id == "ds-2"
    assert got.ragflow_initialized_at == "2026-10-17T00:00:00+00:00"


# ---- 服务身份（loud-failure 契约，无共享 key 静默回退） -----------------------


@pytest.mark.asyncio
async def test_get_service_client_unconfigured_secret_raises(monkeypatch):
    """EAI_SSO_SHARED_SECRET 未配置 → RuntimeError 直接上抛（get_service_client 真身）。"""
    monkeypatch.setattr("app.extensions.config._extensions_config", None)
    monkeypatch.delenv("EAI_SSO_SHARED_SECRET", raising=False)
    from app.extensions.ragflow_sso.service import get_service_client

    with pytest.raises(RuntimeError, match="EAI_SSO_SHARED_SECRET"):
        await get_service_client(db=None)


# ---- 端点编排（直调路由函数，镜像 test_contract_price_library.py） --------------


def test_router_exposes_ragflow_area():
    from app.extensions.contract_price import router

    paths = {r.path for r in router.routes}
    base = "/api/extensions/contract-price"
    assert f"{base}/ragflow/init" in paths
    assert f"{base}/ragflow/status" in paths
    assert f"{base}/library/files/{{file_id}}/ragflow-sync" in paths
    assert f"{base}/documents/{{doc_id}}/ragflow-sync-items" in paths


@pytest.mark.asyncio
async def test_init_endpoint_returns_initialized_and_connectivity(ragflow_env, monkeypatch):
    state, client = ragflow_env
    monkeypatch.setattr(ragflow_setup, "get_service_client", _async_returning(client))
    out = await init_contract_ragflow(db=None, _=None)
    assert out["status"] == "ok"
    assert [r["status"] for r in out["initialized"]] == ["created", "created"]
    assert out["connectivity"]["available"] is True
    assert [d["status"] for d in out["connectivity"]["datasets"]] == ["connected", "connected"]


@pytest.mark.asyncio
async def test_status_endpoint_degrades_when_service_unconfigured(monkeypatch):
    async def _raise(db):
        raise RuntimeError("EAI_SSO_SHARED_SECRET not configured")

    monkeypatch.setattr(ragflow_setup, "get_service_client", _raise)
    out = await contract_ragflow_status(db=None, _=None)
    assert out["available"] is False
    assert "EAI_SSO_SHARED_SECRET" in out["error"]


@pytest.mark.asyncio
async def test_init_endpoint_service_failure_returns_503(monkeypatch):
    """服务身份失败（RuntimeError，如 SSO 未配置）→ 503 + detail（非裸 500, Task2 review M4）。"""

    async def _raise(db):
        raise RuntimeError("EAI_SSO_SHARED_SECRET not configured")

    monkeypatch.setattr(ragflow_setup, "get_service_client", _raise)
    with pytest.raises(HTTPException) as ei:
        await init_contract_ragflow(db=None, _=None)
    assert ei.value.status_code == 503
    assert "EAI_SSO_SHARED_SECRET" in ei.value.detail


@pytest.mark.asyncio
async def test_init_endpoint_unreachable_returns_503(ragflow_env, monkeypatch):
    """RAGFlow 不可达（httpx 连接错误穿透 create 链路）→ /ragflow/init 503 + detail。"""
    state, client = ragflow_env
    state.available = False
    monkeypatch.setattr(ragflow_setup, "get_service_client", _async_returning(client))
    with pytest.raises(HTTPException) as ei:
        await init_contract_ragflow(db=None, _=None)
    assert ei.value.status_code == 503
    assert "connection refused" in ei.value.detail


@pytest.mark.asyncio
async def test_sync_endpoint_502_when_service_unconfigured(monkeypatch):
    """sync 链路 RuntimeError → 502（前端 toast 按 502 文案；与 /init 的 503 区分）。"""
    lf = SimpleNamespace(id=uuid.uuid4(), file_name="合同A.pdf", storage_key="library/f1/abc_合同A.pdf", file_type="pdf")
    monkeypatch.setattr(cpa_crud, "get_library_file", _async_returning(lf))
    monkeypatch.setattr(cpa_storage, "get_object", lambda key: b"%PDF-1.7")

    async def _raise(db):
        raise RuntimeError("EAI_SSO_SHARED_SECRET not configured")

    monkeypatch.setattr(ragflow_setup, "get_service_client", _raise)
    with pytest.raises(HTTPException) as ei:
        await ragflow_sync_library_file(file_id=lf.id, db=None, _=None)
    assert ei.value.status_code == 502
    assert "EAI_SSO_SHARED_SECRET" in ei.value.detail


@pytest.mark.asyncio
async def test_ensure_initialized_race_loser_deletes_duplicate_and_aligns(tmp_path, monkeypatch):
    """并发首建竞态兜底: create 成功后按名复核发现另一进程的胜者 → 删本方副本、
    对齐胜者 id（status aligned）。stub client 不走 httpx（config 隔离用 tmp_path）。"""
    monkeypatch.setattr(cpa_crud, "_config_path", lambda: str(tmp_path / "config.json"))

    class _RacingClient:
        def __init__(self):
            self.created = []
            self.deleted = []
            self._by_name = {}

        async def get_dataset_by_name(self, name):
            return self._by_name.get(name)

        async def create_dataset(self, name, **_kw):
            mine_id = f"mine-{len(self.created)}"
            self.created.append(name)
            if len(self.created) == 2:  # 第二个库 create 后: 另一进程的胜者同名凭空出现
                self._by_name[name] = {"id": "winner-ds", "name": name}
            return {"data": {"id": mine_id}}

        async def delete_dataset(self, dataset_id):
            self.deleted.append(dataset_id)

    rc = _RacingClient()
    out = await ragflow_setup.ensure_initialized(rc)
    assert out[0] == {"name": ragflow_setup.DATASET_CONTRACT, "status": "created", "dataset_id": "mine-0"}
    assert out[1] == {"name": ragflow_setup.DATASET_GOODS_TABLE, "status": "aligned", "dataset_id": "winner-ds"}
    assert rc.deleted == ["mine-1"]  # 本方副本被删，胜者保留
    assert cpa_crud.load_config().ragflow_goods_dataset_id == "winner-ds"  # 落盘的是胜者 id


@pytest.mark.asyncio
async def test_sync_endpoint_404_when_file_missing(monkeypatch):
    monkeypatch.setattr(cpa_crud, "get_library_file", _async_returning(None))
    with pytest.raises(HTTPException) as ei:
        await ragflow_sync_library_file(file_id=uuid.uuid4(), db=None, _=None)
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_sync_endpoint_syncs_library_file(ragflow_env, monkeypatch):
    state, client = ragflow_env
    lf = SimpleNamespace(
        id=uuid.uuid4(),
        file_name="合同A.pdf",
        storage_key="library/f1/abc_合同A.pdf",
        file_type="pdf",
    )
    monkeypatch.setattr(cpa_crud, "get_library_file", _async_returning(lf))
    monkeypatch.setattr(cpa_storage, "get_object", lambda key: b"%PDF-1.7")
    monkeypatch.setattr(ragflow_setup, "get_service_client", _async_returning(client))
    out = await ragflow_sync_library_file(file_id=lf.id, db=None, _=None)
    assert out["status"] == "synced"
    assert len(state.posts("/documents")) == 1
    assert len(state.posts("/chunks")) == 1


# ---- 库上传通道逐文件同步（ragflow_sync 表单字段, EAI-CUSTOM） -----------------


class _UpFile:
    """UploadFile 桩: 文件名 + 内容（镜像 test_contract_price_library.py 的 _F）。"""

    def __init__(self, filename, content=b"%PDF-1.7 stub"):
        self.filename = filename
        self.content_type = "application/pdf"
        self._content = content

    async def read(self):
        return self._content


class _DbNoFolders:
    """db.get(CpaLibraryFolder, fid) → None（folder_id="" 时本就不会走到）。"""

    async def get(self, model, obj_id):
        return None


def _stub_library_storage(monkeypatch):
    """无重复 + create_library_file 落行 + upload_bytes 空转（MinIO 不出网）。"""
    created = []
    monkeypatch.setattr(cpa_crud, "find_library_duplicate", _async_returning(None))

    async def _create(db, **kw):
        row = SimpleNamespace(id=uuid.uuid4(), **kw)
        created.append(row)
        return row

    monkeypatch.setattr(cpa_crud, "create_library_file", _create)
    monkeypatch.setattr(cpa_storage, "upload_bytes", lambda key, data, *a: None)
    return created


@pytest.mark.asyncio
async def test_upload_ragflow_sync_syncs_each_stored_file(monkeypatch):
    """ragflow_sync=true → 每个成功入库文件逐个 sync_file（文件名+原字节），
    条目携带 ragflow 结果；未勾选的错误条目（非法扩展名）不触发同步。"""
    created = _stub_library_storage(monkeypatch)
    client = object()  # 仅验证 get_service_client → sync_file 传参链路
    monkeypatch.setattr(ragflow_setup, "get_service_client", _async_returning(client))
    synced = []

    async def _sync(cl, filename, content):
        synced.append((cl, filename, content))
        return {"status": "synced", "dataset_id": "ds-1", "ragflow_document_id": "doc-1"}

    monkeypatch.setattr(ragflow_setup, "sync_file", _sync)

    out = await upload_library_files(
        folder_id="",
        files=[_UpFile("合同A.pdf"), _UpFile("合同B.docx"), _UpFile("忽略.txt")],
        ragflow_sync=True,
        db=_DbNoFolders(),
        _=None,
    )
    assert [i["file_name"] for i in out["items"] if "ragflow" in i] == ["合同A.pdf", "合同B.docx"]
    assert all(i["ragflow"] == {"status": "synced"} for i in out["items"] if "ragflow" in i)
    assert [i["error"] for i in out["items"] if "error" in i] == ["仅接受 .pdf / .docx"]
    assert [s[1] for s in synced] == ["合同A.pdf", "合同B.docx"]  # 按入库文件名逐个调用
    assert all(s[0] is client for s in synced)
    assert [s[2] for s in synced] == [b"%PDF-1.7 stub", b"%PDF-1.7 stub"]
    assert len(created) == 2


@pytest.mark.asyncio
async def test_upload_ragflow_sync_failure_does_not_fail_upload(monkeypatch):
    """sync_file 抛 RuntimeError/HTTPError（安全类型, str() 仅含配置文案/状态码）
    → 上传照常成功（文件已落 MinIO+库），条目原样透传消息。"""
    _stub_library_storage(monkeypatch)
    monkeypatch.setattr(ragflow_setup, "get_service_client", _async_returning(object()))

    async def _boom(cl, filename, content):
        raise RuntimeError("EAI_SSO_SHARED_SECRET not configured")

    monkeypatch.setattr(ragflow_setup, "sync_file", _boom)

    out = await upload_library_files(
        folder_id="",
        files=[_UpFile("合同A.pdf")],
        ragflow_sync=True,
        db=_DbNoFolders(),
        _=None,
    )
    item = out["items"][0]
    assert item["file_id"] is not None and item["reused"] is False  # 上传本身成功
    assert item["ragflow"]["status"] == "error"
    assert "EAI_SSO_SHARED_SECRET" in item["ragflow"]["message"]


@pytest.mark.asyncio
async def test_upload_ragflow_sync_unknown_exception_sanitizes_message(monkeypatch):
    """未知异常（如 SQLAlchemy 异常串可能内嵌 api_token）→ 条目只给固定文案，
    原始异常细节不进响应（服务端日志仅记类型）。"""
    _stub_library_storage(monkeypatch)
    monkeypatch.setattr(ragflow_setup, "get_service_client", _async_returning(object()))

    async def _leak(cl, filename, content):
        raise SQLAlchemyError("INSERT ... api_token='ragflow-secret-token' ...")

    monkeypatch.setattr(ragflow_setup, "sync_file", _leak)

    out = await upload_library_files(
        folder_id="",
        files=[_UpFile("合同A.pdf")],
        ragflow_sync=True,
        db=_DbNoFolders(),
        _=None,
    )
    item = out["items"][0]
    assert item["file_id"] is not None and item["reused"] is False  # 上传本身成功
    assert item["ragflow"] == {"status": "error", "message": "RAGFlow 同步失败"}
    assert "ragflow-secret-token" not in json.dumps(out, default=str)  # 凭据不进响应体


@pytest.mark.asyncio
async def test_upload_without_ragflow_sync_skips_sync(monkeypatch):
    """默认（不勾选）→ sync_file 零调用，条目无 ragflow 键（行为与现状一致）。"""
    _stub_library_storage(monkeypatch)
    client_calls = []

    async def _client(db):
        client_calls.append(db)
        return object()

    async def _sync(cl, filename, content):  # pragma: no cover — 被调用即失败
        raise AssertionError("sync_file must not be called when ragflow_sync is false")

    monkeypatch.setattr(ragflow_setup, "get_service_client", _client)
    monkeypatch.setattr(ragflow_setup, "sync_file", _sync)

    out = await upload_library_files(
        folder_id="",
        files=[_UpFile("合同A.pdf")],
        ragflow_sync=False,  # 直调须显式传: 缺省的 Form(False) 对象本身为真值（同 paths 直调坑）
        db=_DbNoFolders(),
        _=None,
    )
    assert client_calls == []
    assert "ragflow" not in out["items"][0]
    assert out["items"][0]["reused"] is False and out["items"][0]["file_id"]


@pytest.mark.asyncio
async def test_upload_ragflow_sync_covers_reused_items(monkeypatch):
    """复用项（同文件夹同 hash）也逐个同步——sync_file 同名幂等 → already_exists。"""
    dup = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(cpa_crud, "find_library_duplicate", _async_returning(dup))
    monkeypatch.setattr(ragflow_setup, "get_service_client", _async_returning(object()))

    async def _sync(cl, filename, content):
        return {"status": "already_exists", "dataset_id": "ds-1", "ragflow_document_id": "doc-9"}

    monkeypatch.setattr(ragflow_setup, "sync_file", _sync)

    out = await upload_library_files(
        folder_id="",
        files=[_UpFile("已有合同.pdf")],
        ragflow_sync=True,
        db=_DbNoFolders(),
        _=None,
    )
    item = out["items"][0]
    assert item["reused"] is True and item["file_id"] == dup.id
    assert item["ragflow"] == {"status": "already_exists"}


# ---- 分项表手动同步（EAI-CUSTOM 决策 B: aggregate / ensure_goods_dataset /
#      sync_items_table / 端点） ---------------------------------------------------


def _item(**kw):
    """cpa_item 行桩（aggregate/sync 只消费这些字段;Numeric 列以 Decimal 出现）。"""
    base = dict(
        goods_name="镀锌钢管",
        spec_model="DN100",
        quantity=3.0,
        unit="米",
        unit_price=Decimal("85.50"),
        price_untaxed=Decimal("75.00"),
        tech_params=None,
        source_contract_no="HT-001",
        is_outlier=False,
        source_page=1,
        source_table_idx=0,
        source_row_idx=0,
        validation_status="ok",
        edit_note=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _DbDoc:
    """db.get(CpaDocument, doc_id) → doc（sync_items_table 的文档查询 seam,直调模式）。"""

    def __init__(self, doc):
        self._doc = doc

    async def get(self, model, obj_id):
        return self._doc


class _DbNone:
    async def get(self, model, obj_id):
        return None


def _stub_doc_items(monkeypatch, doc, items):
    """crud.list_items → (items, n)（document_id 断言钉住查询参数）。"""

    async def _list_items(session, *args, **kwargs):
        assert kwargs.get("document_id") == doc.id
        return list(items), len(items)

    monkeypatch.setattr(cpa_crud, "list_items", _list_items)


def _capture_upload_content(monkeypatch):
    """包一层真实 upload_document,顺手读落盘的 markdown 内容（fake httpx 不收文件体）。"""
    seen = {}
    real_upload = RAGFlowClient.upload_document

    async def _capture(self, dataset_id, file_path, file_name=None, **kw):
        with open(file_path, "rb") as f:
            seen["content"] = f.read().decode("utf-8")
        seen["name"] = file_name
        return await real_upload(self, dataset_id, file_path, file_name=file_name, **kw)

    monkeypatch.setattr(RAGFlowClient, "upload_document", _capture)
    return seen


def test_aggregate_items_markdown_formats_table():
    items = [
        _item(goods_name="镀锌钢管", quantity=3.0, unit_price=Decimal("85.5"), price_untaxed=None, source_contract_no="HT-001"),
        _item(
            goods_name="角钢",
            spec_model=None,
            quantity=2.555,
            unit="吨",
            unit_price=Decimal("4200.004"),
            price_untaxed=Decimal("3716.81"),
            tech_params={"材质": "Q235", "壁厚": "5mm"},
            source_contract_no=None,
            is_outlier=True,
            validation_status="adjusted",
        ),
        _item(goods_name="法兰盘", spec_model="DN100 PN16", quantity=12, unit="片", unit_price=None, price_untaxed=None, tech_params={}, source_contract_no="HT-002"),
        # 异常 + 人工编辑叠加: 品名前缀 ⚠✎;校验列 edit_note 优先于 validation_status
        _item(goods_name="水泵", quantity=1, unit="台", unit_price=Decimal("1200"), is_outlier=True, validation_status="adjusted", edit_note="人工改价 1200"),
    ]
    md = ragflow_setup.aggregate_items_markdown("合同A.pdf", items)
    lines = md.splitlines()
    assert lines[0] == "# 合同A.pdf 货物分项表"
    assert re.fullmatch(r"> 生成时间:\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC · 共 4 项", lines[2])
    assert "| 品名 | 规格型号 | 数量 | 单位 | 含税单价 | 不含税单价 | 来源合同号 | 校验 |" in lines
    assert "|---|---|---|---|---|---|---|---|" in lines
    assert "| 镀锌钢管 | DN100 | 3 | 米 | 85.50 | — | HT-001 | — |" in lines
    assert "| ⚠ 角钢 | — | 2.555 | 吨 | 4200.00 | 3716.81 | — | adjusted |" in lines
    assert "| 法兰盘 | DN100 PN16 | 12 | 片 | — | — | HT-002 | — |" in lines
    assert "| ⚠✎ 水泵 | DN100 | 1 | 台 | 1200.00 | 75.00 | HT-001 | ✎ 已人工编辑 |" in lines
    # tech_params 有值才进明细段;空 dict 不进
    assert "## 技术参数明细" in lines
    assert "- **角钢**:材质:Q235、壁厚:5mm" in lines
    assert "- **法兰盘**" not in md
    assert md.endswith("\n")
    # 空列表: 标题 + 计数 + 表头,无明细段
    empty = ragflow_setup.aggregate_items_markdown("空合同.pdf", [])
    assert "# 空合同.pdf 货物分项表" in empty
    assert "共 0 项" in empty
    assert "技术参数明细" not in empty


@pytest.mark.asyncio
async def test_ensure_goods_dataset_creates_only_goods_and_persists(ragflow_env):
    """单库版 ensure_initialized: 只建「合同货物分项表格」（permission=team + bge-m3）,
    goods id 落盘;contract id 不动、initialized_at 不冒领。二次调用 aligned 零 create。"""
    state, client = ragflow_env
    out = await ragflow_setup.ensure_goods_dataset(client)
    assert out["name"] == ragflow_setup.DATASET_GOODS_TABLE
    assert out["status"] == "created" and out["dataset_id"]
    creates = state.posts("/datasets")
    assert [c["json"]["name"] for c in creates] == [ragflow_setup.DATASET_GOODS_TABLE]
    assert creates[0]["json"]["permission"] == "team"
    assert creates[0]["json"]["embedding_model"] == ragflow_setup.EMBEDDING_MODEL
    assert cpa_crud.load_config().ragflow_goods_dataset_id == out["dataset_id"]
    assert not cpa_crud.load_config().ragflow_contract_dataset_id
    assert cpa_crud.load_config().ragflow_initialized_at is None
    second = await ragflow_setup.ensure_goods_dataset(client)
    assert second == {"name": ragflow_setup.DATASET_GOODS_TABLE, "status": "aligned", "dataset_id": out["dataset_id"]}
    assert len(state.posts("/datasets")) == 1  # 零新增 create


@pytest.mark.asyncio
async def test_sync_items_table_creates_uploads_and_parses(ragflow_env, monkeypatch):
    state, client = ragflow_env
    doc_id = uuid.uuid4()
    doc = SimpleNamespace(id=doc_id, file_name="合同A.pdf", parse_status="parsed")
    # 故意乱序传入（source_row_idx 2/0/1）——表格须按提取行序重排
    items = [
        _item(goods_name="第二行", source_row_idx=2),
        _item(goods_name="第零行", source_row_idx=0),
        _item(goods_name="第一行", source_row_idx=1, is_outlier=True),
    ]
    _stub_doc_items(monkeypatch, doc, items)
    seen = _capture_upload_content(monkeypatch)

    out = await ragflow_setup.sync_items_table(_DbDoc(doc), doc_id, client)

    assert out["status"] == "created"
    assert out["items_count"] == 3
    assert out["ragflow_document_id"]
    # 决策 B 隐式初始化: 只建分项库
    creates = state.posts("/datasets")
    assert [c["json"]["name"] for c in creates] == [ragflow_setup.DATASET_GOODS_TABLE]
    assert creates[0]["json"]["permission"] == "team"
    # 上传文件名固定 {文档名}-货物分项表.md,表格按行序排列且含标题
    assert seen["name"] == "合同A.pdf-货物分项表.md"
    body = seen["content"]
    assert "# 合同A.pdf 货物分项表" in body
    assert body.index("第零行") < body.index("第一行") < body.index("第二行")
    # 上传后触发解析（嵌入）
    parses = state.posts("/chunks")
    assert len(parses) == 1
    assert parses[0]["json"] == {"document_ids": [out["ragflow_document_id"]]}
    # goods id 落盘
    assert cpa_crud.load_config().ragflow_goods_dataset_id == out["dataset_id"]


@pytest.mark.asyncio
async def test_sync_items_table_replaces_existing_table_document(ragflow_env, monkeypatch):
    """替换式: 同名分项表文档已存在 → 删旧 → 重传,status "replaced"（库已在,零 create）。"""
    state, client = ragflow_env
    doc_id = uuid.uuid4()
    doc = SimpleNamespace(id=doc_id, file_name="合同A.pdf", parse_status="parsed")
    ds_id = "ds-goods-seed"
    state.datasets[ds_id] = {
        "id": ds_id,
        "name": ragflow_setup.DATASET_GOODS_TABLE,
        "description": "",
        "document_count": 1,
        "chunk_count": 0,
    }
    state.documents[ds_id] = [{"id": "doc-old", "name": "合同A.pdf-货物分项表.md", "run": "DONE"}]
    _stub_doc_items(monkeypatch, doc, [_item()])
    deleted = []

    async def _fake_delete(self, dataset_id, document_id):
        deleted.append((dataset_id, document_id))

    monkeypatch.setattr(RAGFlowClient, "delete_document", _fake_delete)  # delete 走 sync urllib,httpx seam 外

    out = await ragflow_setup.sync_items_table(_DbDoc(doc), doc_id, client)

    assert out["status"] == "replaced"
    assert out["items_count"] == 1
    assert deleted == [(ds_id, "doc-old")]
    assert len(state.posts("/datasets")) == 0
    assert len(state.posts("/documents")) == 1  # 删后重传
    assert len(state.posts("/chunks")) == 1


@pytest.mark.asyncio
async def test_sync_items_table_409_when_not_parsed(monkeypatch):
    """未解析（含 parse_status=None）→ 409「请先完成解析」,且不查分项。"""
    doc = SimpleNamespace(id=uuid.uuid4(), file_name="合同B.pdf", parse_status="pending")
    called = []

    async def _list_items(session, *a, **kw):
        called.append(kw)  # pragma: no cover — 409 必须先短路
        return ([_item()], 1)

    monkeypatch.setattr(cpa_crud, "list_items", _list_items)
    with pytest.raises(HTTPException) as ei:
        await ragflow_setup.sync_items_table(_DbDoc(doc), doc.id, client=object())
    assert ei.value.status_code == 409
    assert "请先完成解析" in ei.value.detail
    assert called == []


@pytest.mark.asyncio
async def test_sync_items_table_404_when_no_items(monkeypatch):
    doc = SimpleNamespace(id=uuid.uuid4(), file_name="合同C.pdf", parse_status="parsed")
    monkeypatch.setattr(cpa_crud, "list_items", _async_returning(([], 0)))
    with pytest.raises(HTTPException) as ei:
        await ragflow_setup.sync_items_table(_DbDoc(doc), doc.id, client=object())
    assert ei.value.status_code == 404
    assert "该文档暂无分项数据" in ei.value.detail


@pytest.mark.asyncio
async def test_sync_items_table_404_when_doc_missing():
    with pytest.raises(HTTPException) as ei:
        await ragflow_setup.sync_items_table(_DbNone(), uuid.uuid4(), client=object())
    assert ei.value.status_code == 404
    assert "文档不存在" in ei.value.detail


@pytest.mark.asyncio
async def test_sync_items_endpoint_returns_result(ragflow_env, monkeypatch):
    state, client = ragflow_env
    doc_id = uuid.uuid4()
    monkeypatch.setattr(ragflow_setup, "get_service_client", _async_returning(client))

    async def _sync(db, did, cl):
        assert did == doc_id and cl is client
        return {"status": "created", "dataset_id": "ds-1", "ragflow_document_id": "doc-1", "items_count": 3}

    monkeypatch.setattr(ragflow_setup, "sync_items_table", _sync)
    out = await ragflow_sync_items(doc_id=doc_id, db=None, _=None)
    assert out == {"status": "created", "dataset_id": "ds-1", "ragflow_document_id": "doc-1", "items_count": 3}


@pytest.mark.asyncio
async def test_sync_items_endpoint_runtime_error_returns_503(monkeypatch):
    """服务身份失败（RuntimeError）→ 503 + detail（对齐 /ragflow/init 语义,按钮场景给原因）。"""

    async def _raise(db):
        raise RuntimeError("EAI_SSO_SHARED_SECRET not configured")

    monkeypatch.setattr(ragflow_setup, "get_service_client", _raise)
    with pytest.raises(HTTPException) as ei:
        await ragflow_sync_items(doc_id=uuid.uuid4(), db=None, _=None)
    assert ei.value.status_code == 503
    assert "EAI_SSO_SHARED_SECRET" in ei.value.detail


@pytest.mark.asyncio
async def test_sync_items_endpoint_passes_through_http_exception(monkeypatch):
    """业务 409/404 原样透传,不被 503 分支吞掉。"""

    async def _sync(db, did, cl):
        raise HTTPException(status_code=409, detail="请先完成解析")

    monkeypatch.setattr(ragflow_setup, "get_service_client", _async_returning(object()))
    monkeypatch.setattr(ragflow_setup, "sync_items_table", _sync)
    with pytest.raises(HTTPException) as ei:
        await ragflow_sync_items(doc_id=uuid.uuid4(), db=None, _=None)
    assert ei.value.status_code == 409
