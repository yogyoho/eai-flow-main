"""EAI-CUSTOM: 合同价格分析 × RAGFlow 初始化/状态/文件同步 —— ragflow_setup 单测。

httpx seam 镜像 test_knowledge_client_payload.py（monkeypatch httpx.AsyncClient），
配置 seam 镜像 test_contract_price_seed_config.py（monkeypatch crud._config_path →
tmp_path）。真实 RAGFlowClient 走全链路（wire payload 断言含 parse_type/parser_id），
无 extensions DB、无网络；端点用直调路由函数模式（test_contract_price_library.py）。
"""

import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

import app.extensions.contract_price  # noqa: F401 — 导入即注册模型
from app.extensions.contract_price import crud as cpa_crud
from app.extensions.contract_price import ragflow_setup
from app.extensions.contract_price import storage as cpa_storage
from app.extensions.contract_price.routers import (
    contract_ragflow_status,
    init_contract_ragflow,
    ragflow_sync_library_file,
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
    path = url.split(API, 1)[1]
    state.calls.append({"method": method, "path": path, "json": kwargs.get("json"), "params": dict(kwargs.get("params") or {})})
    parts = [p for p in path.split("/") if p]
    if parts[0] != "datasets":
        return _Resp({"code": 102, "message": f"unknown route {path}"}, 404)
    if len(parts) == 1:
        if method == "GET":
            if not state.available:
                raise httpx.ConnectError("connection refused")
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
            return _Resp({"code": 0, "data": {"docs": docs, "total": len(docs)}})
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


@pytest.mark.asyncio
async def test_collect_status_unreachable_degrades_without_raising(ragflow_env):
    state, client = ragflow_env
    state.available = False
    out = await ragflow_setup.collect_status(client)
    assert out == {"available": False, "datasets": []}


@pytest.mark.asyncio
async def test_collect_status_reports_missing_when_no_datasets(ragflow_env):
    state, client = ragflow_env
    out = await ragflow_setup.collect_status(client)
    assert out["available"] is True
    assert [d["status"] for d in out["datasets"]] == ["missing", "missing"]


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
async def test_init_endpoint_propagates_service_failure(monkeypatch):
    async def _raise(db):
        raise RuntimeError("EAI_SSO_SHARED_SECRET not configured")

    monkeypatch.setattr(ragflow_setup, "get_service_client", _raise)
    with pytest.raises(RuntimeError):
        await init_contract_ragflow(db=None, _=None)


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
