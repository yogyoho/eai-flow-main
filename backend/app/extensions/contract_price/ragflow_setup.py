"""EAI-CUSTOM: 合同价格分析 × RAGFlow 知识库集成(初始化/状态/文件同步)— 本地定制,非上游.

并发约定: 首建由进程内 _INIT_LOCK 串行;跨进程竞态由 create 后按名复核兜底
(胜者同名 → 删本方副本、对齐胜者)。失败浮出: /library/files/{file_id}/ragflow-sync →
HTTP 502; /ragflow/init（服务身份/建库/RAGFlow 不可达）→ HTTP 503——前端提示按各自文案。
"""

import asyncio
import logging
import os
import tempfile
from datetime import UTC, datetime

from app.extensions.contract_price import crud
from app.extensions.ragflow_sso.service import get_service_client  # noqa: F401 — 端点经此模块取服务身份客户端（routers 引用 + tests monkeypatch 本命名空间）

logger = logging.getLogger(__name__)

# 共享租户固定知识库（服务身份统一创建, permission=team, v1.1 已上线验证）:
# embedding = 租户模型注册表里的 Ollama bge-m3; BuiltIn 管道 naive 分块。
DATASET_CONTRACT = "合同知识库"
DATASET_GOODS_TABLE = "合同货物分项表格"
EMBEDDING_MODEL = "bge-m3:latest@ollama@Ollama"
DATASET_DESCRIPTION = "EAI 合同价格分析共享知识库（EAI-CUSTOM 自动创建）"

DATASETS = [
    {"name": DATASET_CONTRACT, "key": "ragflow_contract_dataset_id"},
    {"name": DATASET_GOODS_TABLE, "key": "ragflow_goods_dataset_id"},
]

# 进程内首建串行锁: 并发 ensure_initialized/sync_file 不重复建库、config 落盘不互相
# 丢更新（锁贯穿检查+建库+落盘全程）。跨进程竞态锁不到，由锁内 create 后的按名复核兜底。
_INIT_LOCK = asyncio.Lock()


async def ensure_initialized(client) -> list[dict]:
    """幂等初始化共享租户的两个固定知识库，并把 dataset id 落入 config.json。

    锁内逐名: 按名查（存在 → aligned，不重建）; 缺失才创建（permission=team +
    Ollama bge-m3，BuiltIn naive —— create_dataset 内部两步化补 description）。
    create 成功后再按名复核一次: 并发方（另一协程/另一进程）已建成同名库时删掉
    本方副本（delete_dataset）→ 对齐胜者 id，status "aligned"。
    两个 dataset id 与 ragflow_initialized_at 均已与 config.json 一致时跳过落盘
    （per-sync 零写放大）。返回 [{name, status: created|aligned, dataset_id}, ...]。
    """
    async with _INIT_LOCK:
        results: list[dict] = []
        for entry in DATASETS:
            name = entry["name"]
            existing = await client.get_dataset_by_name(name)
            if existing and existing.get("id"):
                results.append({"name": name, "status": "aligned", "dataset_id": existing["id"]})
                continue
            result = await client.create_dataset(
                name=name,
                description=DATASET_DESCRIPTION,
                embedding_model=EMBEDDING_MODEL,
                chunk_method="naive",  # client 映射为 wire 的 parser_id="naive"（parse_type=1 恒置）
                permission="team",
            )
            dataset_id = (result.get("data") or {}).get("id") or ""
            if not dataset_id:
                raise RuntimeError(f"RAGFlow create_dataset 未返回 id: {name}")
            winner = await client.get_dataset_by_name(name) or {}
            winner_id = winner.get("id") or ""
            if winner_id and winner_id != dataset_id:
                try:
                    await client.delete_dataset(dataset_id)
                except Exception:  # noqa: BLE001 — 副本清理失败不阻塞对齐，两库 id 均留痕告警
                    logger.warning(
                        "ensure_initialized: 同名竞态副本删除失败（保留两库）name=%s mine=%s winner=%s",
                        name,
                        dataset_id,
                        winner_id,
                        exc_info=True,
                    )
                results.append({"name": name, "status": "aligned", "dataset_id": winner_id})
                continue
            results.append({"name": name, "status": "created", "dataset_id": dataset_id})

        cfg = crud.load_config()
        if cfg.ragflow_initialized_at and all(getattr(cfg, entry["key"], None) == res["dataset_id"] for entry, res in zip(DATASETS, results)):
            return results  # 已对齐且已落盘: 不再 load→mutate→save
        for entry, res in zip(DATASETS, results):
            setattr(cfg, entry["key"], res["dataset_id"])
        cfg.ragflow_initialized_at = datetime.now(UTC).isoformat()
        crud.save_config(cfg)
        return results


async def collect_status(client) -> dict:
    """连通性 + 两个固定知识库状态（配置 id 优先，失效自愈回退按名）。

    RAGFlow 不可达 → {"available": False, "datasets": [], "error": ...}，不抛
    （与 /ragflow/status 的降级分支形状一致，前端面板直读）。成功路径附带
    initialized_at（config 落盘的初始化时间，可能为 None——前端「初始化于 …」footer）。
    """
    if not await client.is_available():
        return {"available": False, "datasets": [], "error": "ragflow unreachable"}
    cfg = crud.load_config()
    datasets: list[dict] = []
    for entry in DATASETS:
        name = entry["name"]
        info: dict = {}
        dataset_id = getattr(cfg, entry["key"], None)
        if dataset_id:
            try:
                info = (await client.get_dataset(dataset_id)).get("data") or {}
            except Exception:  # noqa: BLE001 — id 失效/瞬断 → 回退按名，状态如实上报
                logger.warning("collect_status: dataset %s (%s) 查询失败，回退按名", dataset_id, name, exc_info=True)
                info = {}
        if not info.get("id"):
            info = await client.get_dataset_by_name(name) or {}
        if info.get("id"):
            datasets.append(
                {
                    "name": name,
                    "status": "connected",
                    "dataset_id": info["id"],
                    "document_count": int(info.get("document_count") or 0),
                    "chunk_count": int(info.get("chunk_count") or 0),
                }
            )
        else:
            datasets.append({"name": name, "status": "missing", "dataset_id": None, "document_count": 0, "chunk_count": 0})
    return {"available": True, "datasets": datasets, "initialized_at": cfg.ragflow_initialized_at}


async def sync_file(client, filename: str, content: bytes) -> dict:
    """把一个库文件同步进「合同知识库」（决策 A：隐式 ensure_initialized）。

    同名文档已存在 → already_exists（零上传）；否则 upload + parse（触发嵌入）。
    client.upload_document 按路径开文件（client.py 契约）→ content 落临时文件。
    失败以异常上抛 → /library/files/{file_id}/ragflow-sync 端点转 HTTP 502。
    """
    await ensure_initialized(client)
    cfg = crud.load_config()
    dataset_id = cfg.ragflow_contract_dataset_id or ""
    if not dataset_id:
        info = await client.get_dataset_by_name(DATASET_CONTRACT) or {}
        dataset_id = info.get("id") or ""
    if not dataset_id:
        raise RuntimeError(f"RAGFlow 数据集不可用: {DATASET_CONTRACT}")
    for doc in await _list_all_documents(client, dataset_id):
        if doc.get("name") == filename:
            return {"status": "already_exists", "dataset_id": dataset_id, "ragflow_document_id": doc.get("id")}
    safe = (filename or "file").replace("/", "_").replace("\\", "_")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, safe)
        with open(path, "wb") as f:
            f.write(content)
        result = await client.upload_document(dataset_id, path, file_name=filename)
    document_id = (result.get("data") or {}).get("id") or ""
    if not document_id:
        raise RuntimeError(f"RAGFlow upload_document 未返回文档 id: {filename}")
    await client.parse_document(dataset_id, document_id)
    logger.info("ragflow sync: %s → dataset %s doc %s", filename, dataset_id, document_id)
    return {"status": "synced", "dataset_id": dataset_id, "ragflow_document_id": document_id}


async def _list_all_documents(client, dataset_id: str) -> list[dict]:
    """dataset 全量文档（list_documents page_size 上限 100 → 翻页取全）。"""
    docs: list[dict] = []
    page = 1
    while True:
        data = (await client.list_documents(dataset_id, page=page, size=100)).get("data") or {}
        batch = data.get("docs") or []
        docs.extend(batch)
        total = data.get("total")
        if not batch or len(batch) < 100 or (isinstance(total, int) and len(docs) >= total):
            return docs
        page += 1
