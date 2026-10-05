"""抽取任务 API——登记 kf_samples 已提取产物 → converter → ingest_extraction 入图（v1 产物消费路径）.

EAI-CUSTOM(2026-10-01 B2): 设计 docs/designs/2026-10-01-ontostudio-ux-governance.md §B2
（eng-review 终裁 D10-D13）。v1 不做文档直抽——源文件在 gateway 容器文件系统不可达，
任务输入 = kf_samples.sample_id，消费其 outline_json.ontology 已持久化抽取产物。

执行链：POST(queued) → BackgroundTasks runner（模块级 asyncio.Lock 串行；converter 纯 CPU
段入 asyncio.to_thread）→ 读 kf_samples.outline_json.ontology → converter 组装
EiaExtraction（mention 的 document_id 合成 "kf-sample:{id}"）→ 重跑=替换（ingest 前按
document_id 清旧 mention——dg_mentions 无唯一键，裸重跑必翻倍）→ ingest_extraction 装载
→ force_review 时**只把本任务新造的实体**置 pending_review（created_at > started_at——
不动自然键合并进来的既有 active 行，守住 ingest.py 的 promote-only 不变量）→ done。

语义四条（eng-review 终裁）：force_review 全量 pending_review（仅新造行）/ 重跑=替换 /
零命中=completed_empty（合法空结果非 failed）/ 启动清扫在 ensure_tables 同一 try/except
（main.py 调 sweep_orphan_tasks，42P01 no-op）。

进度=阶段枚举（queued→extracting→loading→done/completed_empty/failed/aborted），无百分比
（ingest_extraction 一次性持久化，无进度生产者——D3/2A 裁决）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.auth import CurrentUser, require_permission
from app.db import Base
from app.doc_graph.ingest import REVIEW_CONFIDENCE, ingest_extraction
from app.doc_graph.schemas import (
    EiaExtraction,
    EntityPayload,
    MentionPayload,
    RelationPayload,
)
from app.ontology.connectors import _ext_url

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/ingest-tasks", tags=["ingest-tasks"])

_TASK_LOCK = asyncio.Lock()  # 串行化 runner（Starlette BackgroundTasks 自身不串行）
_ACTIVE_STATES = ("queued", "extracting", "loading")


class IngestTask(Base):
    """抽取任务行（eng-review T2/T5；新表由 ensure_tables create_all 建出，无手工 DDL）."""

    __tablename__ = "ingest_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sample_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sample_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_id: Mapped[str] = mapped_column(String(200), nullable=False)  # 合成 "kf-sample:{id}"
    force_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    # server_default 必须带：router/清扫走裸 SQL INSERT，ORM 侧 default= 不生效（eng-review 实测 NotNullViolation）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CreateTaskBody(BaseModel):
    """POST /ingest-tasks 请求体（越界 422 而非 500）。"""

    sample_id: uuid.UUID
    force_review: bool = True


class UploadExtractBody(BaseModel):
    """POST /ingest-tasks/upload 请求体（G3 文件上传一体流）。"""

    force_review: bool = True


# ── 连接（照 ingest.py 既有模式：每操作自建引擎 + NullPool + 显式 dispose）──────────


def _engine():
    return create_async_engine(_ext_url(), poolclass=NullPool)


async def _fetch_row(conn, sql: str, params: dict) -> Any:
    return (await conn.execute(text(sql), params)).first()


async def _set_status(task_id: str, status: str, extra: str = "", params_extra: dict | None = None) -> None:
    engine = _engine()
    try:
        async with engine.begin() as conn:
            sets = "status = :status, updated_at = NOW()" + (", " + extra if extra else "")
            await conn.execute(
                text(f"UPDATE ingest_tasks SET {sets} WHERE id = CAST(:tid AS uuid)"),
                {"tid": str(task_id), "status": status, **(params_extra or {})},
            )
    finally:
        await engine.dispose()


# ── G3 直连抽取：源文件预取（创建时透传 Cookie 自 gateway 拉副本到内核卷）──────────

_KF_SRC_DIR = Path("/data/kernel/kf-src")

_UPLOADS_DIR = Path("/data/kernel/kf-uploads")
_ALLOWED_SOURCE_EXT = {".txt", ".docx"}


def _upload_extract_and_register(
    upload_path: Path, original_name: str, force_review: bool, user_id: str
) -> dict:
    """G3 上传一体流（CPU 段，后台执行）：kf_samples 行 → run_extract → outline_json → 建任务行。

    kf_samples 双写（同库同 schema， OntoStudio 上传入口 + EAI 向导入口双向可见）。
    规则抽取失败 → 样例行保留（status=failed_extract）+ 任务行 failed，文件不删（可重试）。
    """
    import hashlib

    from app.doc_graph.text_extract import ExtractSourceError, run_extract

    task_id = str(uuid.uuid4())
    engine = _engine()
    try:
        ext = upload_path.suffix.lower()
        file_hash = hashlib.sha256(upload_path.read_bytes()).hexdigest()[:32]
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO kf_samples (id, title, source_path, file_hash, scenario, status)
                    VALUES (CAST(:sid AS uuid), :title, :spath, :fhash, 'other', 'parsed')
                    ON CONFLICT (file_hash) DO UPDATE SET source_path = EXCLUDED.source_path, updated_at = NOW()
                    RETURNING id
                    """
                ).bindparams(),
                {"sid": uuid.uuid4(), "title": original_name, "spath": str(upload_path), "fhash": file_hash},
            )
        try:
            outline = run_extract(str(upload_path))
        except ExtractSourceError as exc:
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE kf_samples SET status = 'failed_extract', notes = :n WHERE source_path = :sp"),
                    {"n": str(exc)[:500], "sp": str(upload_path)},
                )
            raise
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE kf_samples SET outline_json = CAST(:o AS jsonb), status = 'parsed', updated_at = NOW() WHERE source_path = :sp"
                ),
                {"o": json.dumps(outline, ensure_ascii=False), "sp": str(upload_path)},
            )
        document_id = f"kf-sample:{file_hash[:8]}"
        asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _run_task_with_sample_uuid(task_id, _sample_uuid_for_hash(file_hash), document_id, force_review),
        )
        return {"task_id": task_id, "mode": "upload-direct", "file": original_name}
    except ExtractSourceError as exc:
        raise HTTPException(400, f"源文件不可读: {exc}") from exc


def _sample_uuid_for_hash(file_hash: str) -> str:
    """file_hash → 稳定 uuid5（与 kf_samples id 列 uuid 类型对齐）。"""
    import uuid as _uuid

    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"kf-upload:{file_hash}"))


def _run_task_with_sample_uuid(task_id: str, sample_uuid: str, document_id: str, force_review: bool) -> None:
    _run_task(task_id, sample_uuid, document_id, force_review)


def _find_src_copy(task_id: str) -> Path | None:
    for f in _KF_SRC_DIR.glob(task_id + ".*"):
        return f
    return None


def _cleanup_src_copy(task_id: str) -> None:
    for f in _KF_SRC_DIR.glob(task_id + ".*"):
        f.unlink(missing_ok=True)


def _direct_extract_outline(path: str) -> dict:
    """G3 直连抽取：源文件副本 → 规则抽取大纲/实体候选/本体产物（run_extract 同构）。"""
    from .text_extract import run_extract

    return run_extract(path)

async def prefetch_source_file(
    gateway_base: str, sample_id: str, cookie: str, dest_no_ext: str
) -> str | None:
    """透传 Cookie 自 gateway 拉源文件副本 → /data/kernel/kf-src/<dest>.<ext>。

    返回落盘路径；404（源文件缺失）返回 None；其余 HTTP 错误抛 HTTPException——
    创建时快速失败，好过执行中才发现不可达。
    """
    import httpx

    url = f"{gateway_base}/api/extensions/eia-samples/{sample_id}/source-file"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(url, headers={"Cookie": f"access_token={cookie}"} if cookie else {})
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"源文件预取失败: {resp.text[:200]}")
    ctype = resp.headers.get("content-type", "")
    ext = ".docx" if "wordprocessingml" in ctype else ".txt"
    _KF_SRC_DIR.mkdir(parents=True, exist_ok=True)
    dest = _KF_SRC_DIR / (dest_no_ext + ext)
    dest.write_bytes(resp.content)
    return str(dest)


# ── converter：outline_json.ontology → EiaExtraction（纯函数，独立测试覆盖）──────────


def _drop_invalid(payload_dict: dict, domain_etypes: frozenset, domain_predicates: frozenset) -> dict:
    """防御性过滤：把 outline 产物里越域的 etype/predicate/悬空引用行剔除并计数.

    outline_json.ontology 由正则抽取器产出（etype/predicate 与 eia.yaml 枚举严格同名），
    但 schemas 域表与 registry 枚举存在双真源漂移风险（cerebrum 2026-09-29 谓词双真源分裂
    教训）——fail-closed 校验拒的是整个 payload，一颗老鼠屎坏一锅：这里先行剔除并计数，
    让合法主体照常入库。
    """
    entities = [e for e in payload_dict.get("entities", []) if e.get("etype") in domain_etypes]
    dropped_entities = len(payload_dict.get("entities", [])) - len(entities)
    names = {e["name"] for e in entities}
    relations = []
    for r in payload_dict.get("relations", []):
        if r.get("predicate") not in domain_predicates:
            continue
        if r.get("subject") not in names or r.get("object") not in names:
            continue
        relations.append(r)
    dropped_relations = len(payload_dict.get("relations", [])) - len(relations)
    return {
        "entities": entities,
        "relations": relations,
        "dropped": {"entities": dropped_entities, "relations": dropped_relations},
    }


def build_payload_from_outline(
    outline: dict | None,
    *,
    document_id: str,
    extracted_by: str,
    task_tag: str | None = None,
) -> tuple[EiaExtraction | None, dict]:
    """outline_json → (EiaExtraction | None, 统计)。零实体返回 (None, stats) → completed_empty。

    mention 合成（外部声音 #3）：正则产物无句子上下文——quote 留空、doc_span 空、
    document_id 统一 "kf-sample:{id}"（重跑=替换的删除锚点）。置信度原样透传
    （正则 0.80-0.95；force_review 的 pending 置换在 runner 后置 UPDATE，不在此改值）。
    task_tag：写入每个实体 attrs["ingest_task"]——force_review 后置 UPDATE 的匹配锚点
    （D11/11A；不写标记则 UPDATE 恒空转——eng-review 实测修复）。
    """
    stats: dict[str, Any] = {"entities": 0, "relations": 0, "dropped": {"entities": 0, "relations": 0}}
    onto = (outline or {}).get("ontology") or {}
    cleaned = _drop_invalid(onto, EiaExtraction.domain_etypes, EiaExtraction.domain_predicates)
    stats["dropped"] = cleaned["dropped"]
    if not cleaned["entities"]:
        return None, stats

    mention = MentionPayload(document_id=document_id)  # quote/doc_span 置空（无句子上下文）
    entities = [
        EntityPayload(
            etype=e["etype"],
            name=e["name"],
            attrs={**(e.get("attrs") or {}), **({"ingest_task": task_tag} if task_tag else {})},
            confidence=e.get("confidence", 1.0),
            mention=mention,
        )
        for e in cleaned["entities"]
    ]
    relations = [
        RelationPayload(
            predicate=r["predicate"],
            subject=r["subject"],
            object=r["object"],
            attrs=r.get("attrs") or {},
            confidence=r.get("confidence", 1.0),
            mention=mention,
        )
        for r in cleaned["relations"]
    ]
    stats["entities"] = len(entities)
    stats["relations"] = len(relations)
    payload = EiaExtraction(
        domain="eia",
        extracted_by=extracted_by[:100],
        entities=entities,
        relations=relations,
    )
    return payload, stats


# ── runner ───────────────────────────────────────────────────────────────────────


async def _task_alive(conn, task_id: str) -> bool:
    """aborted 后中途退出检查：任务行状态不再是 extracting/loading 即放弃后续步骤。"""
    row = await _fetch_row(conn, "SELECT status FROM ingest_tasks WHERE id = CAST(:tid AS uuid)", {"tid": task_id})
    return bool(row) and row.status in ("extracting", "loading")


async def _run_task(task_id: str, sample_id: str, document_id: str, force_review: bool) -> None:
    """后台执行体（串行：_TASK_LOCK；阶段枚举推进；异常→failed 不静默）。"""
    extracted_by = f"ingest-task:{task_id}"[:100]
    async with _TASK_LOCK:
        engine = _engine()
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE ingest_tasks SET status='extracting', started_at=NOW(), updated_at=NOW(), stats = CAST(:s AS jsonb) WHERE id = CAST(:tid AS uuid)"),
                    {"tid": task_id, "s": json.dumps({"progress": {"stage": "extracting", "pct": 10}}, ensure_ascii=False)},
                )
                row = await _fetch_row(
                    conn,
                    "SELECT title, outline_json FROM kf_samples WHERE id = CAST(:sid AS uuid)",
                    {"sid": sample_id},
                )
            if row is None:
                await _set_status(
                    task_id,
                    "failed",
                    extra="error = :err, finished_at = NOW()",
                    params_extra={"err": "kf_samples 行不存在"},
                )
                return
            outline = row.outline_json if isinstance(row.outline_json, dict) else None

            # G3 直连抽取：任务创建时预取的源文件副本在 → 规则抽取补产物 → 写回 kf_samples
            # （与离线管线同构, 下游 converter 零改动）; 无副本走 v1 产物消费。
            src_copy = _find_src_copy(task_id)
            if src_copy:
                try:
                    outline_direct = await asyncio.to_thread(_direct_extract_outline, str(src_copy))
                    async with engine.begin() as conn:
                        await conn.execute(
                            text(
                                "UPDATE kf_samples SET outline_json = CAST(:o AS jsonb), updated_at = NOW() WHERE id = CAST(:sid AS uuid)"
                            ),
                            {"o": json.dumps(outline_direct, ensure_ascii=False), "sid": sample_id},
                        )
                    outline = outline_direct
                except Exception as exc:  # noqa: BLE001 - 直连抽取失败落行可见
                    await _set_status(
                        task_id,
                        "failed",
                        extra="error = :err, finished_at = NOW()",
                        params_extra={"err": f"直连抽取失败: {exc}"},
                    )
                    _cleanup_src_copy(task_id)
                    return

            # converter 纯 CPU 段入线程池（P1 裁决 1A：不在事件循环跑 CPU 密集段）
            payload, stats = await asyncio.to_thread(
                build_payload_from_outline,
                outline,
                document_id=document_id,
                extracted_by=extracted_by,
                task_tag=task_id,
            )
            if payload is None:
                await _set_status(
                    task_id,
                    "completed_empty",
                    extra="stats = CAST(:stats AS jsonb), finished_at = NOW()",
                    params_extra={"stats": json.dumps(stats, ensure_ascii=False)},
                )
                return

            alive = await _alive_check(task_id)
            if not alive:
                return  # aborted——用户已放弃本任务
            total = len(payload.entities) + len(payload.relations)

            async def _set_progress(done: int, total: int) -> None:
                """G6 进度：loading 阶段经独立连接写 stats jsonb（主事务外可见；失败静默）。"""
                engine3 = _engine()
                try:
                    async with engine3.begin() as conn:
                        await conn.execute(
                            text("UPDATE ingest_tasks SET stats = CAST(:s AS jsonb), updated_at = NOW() WHERE id = CAST(:tid AS uuid)"),
                            {
                                "s": json.dumps({"progress": {"stage": "loading", "done": done, "total": total, "pct": 30 + int(60 * done / total) if total else 100}}, ensure_ascii=False),
                                "tid": str(task_id),
                            },
                        )
                except Exception:  # noqa: BLE001 - 进度写失败不碰任务主流程
                    pass
                finally:
                    await engine3.dispose()

            await _set_progress(0, total)
            await _set_status(task_id, "loading")

            # 重跑=替换（D12/12A）：dg_mentions 无唯一键，先清同文档旧产物再入库
            engine2 = _engine()
            try:
                async with engine2.begin() as conn:
                    await conn.execute(text("DELETE FROM dg_mentions WHERE document_id = :doc"), {"doc": document_id})
            finally:
                await engine2.dispose()

            # force_review（D11 终裁 v2）：下沉为 ingest_extraction 的 force_pending——新行直接 pending、
            # 冲突行覆盖 promote-only 提升；后置 UPDATE 补丁废弃（重跑时 created_at 窗口挡不住
            # ingest 提升路径，两不变量打架——eng-review 演练实测）
            def _progress_cb(done: int, total: int) -> None:
                asyncio.create_task(_set_progress(done, total))

            counts = await ingest_extraction(payload, force_pending=force_review, progress_cb=_progress_cb)

            await _set_status(
                task_id,
                "done",
                extra="stats = CAST(:stats AS jsonb), finished_at = NOW()",
                params_extra={"stats": json.dumps({**stats, **counts}, ensure_ascii=False)},
            )
            _cleanup_src_copy(task_id)  # G3: 直连抽取的源文件副本用毕即清
        except Exception as exc:  # noqa: BLE001——任务失败必须落行可见，不静默
            await _set_status(
                task_id,
                "failed",
                extra="error = :err, finished_at = NOW()",
                params_extra={"err": str(exc)[:2000]},
            )
        finally:
            await engine.dispose()


async def _alive_check(task_id: str) -> bool:
    engine = _engine()
    try:
        async with engine.connect() as conn:
            return await _task_alive(conn, task_id)
    finally:
        await engine.dispose()


async def sweep_orphan_tasks() -> None:
    """启动清扫（D4/3A）：重启丢队/丢运行态 → failed。

    必须在 ensure_tables() **之后**、同一 try/except 内被调（main.py lifespan）——
    表可能不存在（42P01），吞掉并 no-op；绝不硬化启动（保 tables_ready 降级语义）。
    """
    engine = _engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE ingest_tasks
                    SET status = 'failed', error = '服务重启中断', finished_at = NOW(), updated_at = NOW()
                    WHERE status IN ('queued', 'extracting', 'loading')
                    """
                )
            )
    except Exception as exc:  # noqa: BLE001——含 42P01（表未建），清扫失败不阻断启动
        _log.warning("ingest_tasks 启动清扫跳过（表未建或 DB 不可达）: %s", exc)
    finally:
        await engine.dispose()


# ── 路由（权限门= require_permission 现行语义，照 doc_graph/routers.py 惯例）─────────


@router.post("", status_code=201)
async def create_task(
    body: CreateTaskBody,
    background: BackgroundTasks,
    request: Request,
    _: CurrentUser = Depends(require_permission("system:access")),
) -> dict:
    """登记并触发抽取任务。同 sample 活动任务 409；sample 缺失 404。

    G3 双通道（2026-10-05）：样例已有产物 → v1 消费 outline_json；无产物但台账有
    source_path → 创建时透传 Cookie 预取源文件副本，执行期规则抽取补产物（直连）。
    """
    engine = _engine()
    try:
        async with engine.begin() as conn:
            dup = await _fetch_row(
                conn,
                "SELECT 1 FROM ingest_tasks WHERE sample_id = CAST(:sid AS uuid) AND status = ANY(:act)",
                {"sid": str(body.sample_id), "act": list(_ACTIVE_STATES)},
            )
            if dup:
                raise HTTPException(409, "该样例已有进行中的抽取任务")
            sample = await _fetch_row(
                conn,
                "SELECT title, outline_json, source_path FROM kf_samples WHERE id = CAST(:sid AS uuid)",
                {"sid": str(body.sample_id)},
            )
            if sample is None:
                raise HTTPException(404, "kf_samples 中不存在该样例")
            onto = (sample.outline_json or {}).get("ontology") if isinstance(sample.outline_json, dict) else None
            has_products = bool(onto and onto.get("entities"))
            source_path = getattr(sample, "source_path", None)
            if not has_products and not source_path:
                raise HTTPException(
                    422,
                    "该样例尚无已提取产物且台账无源文件路径——无法创建抽取任务",
                )
            task_id = str(uuid.uuid4())
            document_id = f"kf-sample:{body.sample_id}"
            await conn.execute(
                text(
                    """
                    INSERT INTO ingest_tasks (id, sample_id, sample_title, document_id, force_review, status)
                    VALUES (CAST(:tid AS uuid), CAST(:sid AS uuid), :title, :doc, :fr, 'queued')
                    """
                ),
                {"tid": task_id, "sid": str(body.sample_id), "title": sample.title, "doc": document_id, "fr": body.force_review},
            )
    finally:
        await engine.dispose()
    # G3 直连：无产物但台账有源文件 → 创建时透传 Cookie 预取源文件副本（用户在线, 快速失败）
    direct_mode = False
    if not has_products and source_path:
        cookie = request.cookies.get("access_token", "")
        await prefetch_source_file(
            os.environ.get("ONTOSTUDIO_GATEWAY_URL", "http://gateway:8001"),
            str(body.sample_id),
            cookie,
            task_id,
        )
        direct_mode = True
    background.add_task(_run_task, task_id, str(body.sample_id), document_id, body.force_review)
    return {"id": task_id, "status": "queued", "document_id": document_id, "mode": "direct" if direct_mode else "v1"}


@router.get("")
async def list_tasks(
    _: CurrentUser = Depends(require_permission("system:access")),
) -> dict:
    """任务队列（最新 50 条；聚合口径走 /stats——D7/6A 分口径）。"""
    engine = _engine()
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT id::text, sample_id::text, sample_title, status, error, stats,
                               force_review, created_at, started_at, finished_at
                        FROM ingest_tasks ORDER BY created_at DESC LIMIT 50
                        """
                    )
                )
            ).mappings().all()
        return {"tasks": [dict(r) for r in rows]}
    finally:
        await engine.dispose()


@router.get("/stats")
async def task_stats(_: CurrentUser = Depends(require_permission("system:access"))) -> dict:
    """任务计数（按状态）+ 任务通道实体的置信度分布（仪表盘「抽取活动」卡同源）。"""
    engine = _engine()
    try:
        async with engine.connect() as conn:
            by_status = {
                r.status: r.c
                for r in (
                    await conn.execute(text("SELECT status, COUNT(*) AS c FROM ingest_tasks GROUP BY status"))
                ).all()
            }
            conf_rows = (
                await conn.execute(
                    text(
                        """
                        SELECT CASE WHEN e.confidence >= 0.9 THEN 'high'
                                    WHEN e.confidence >= :rev THEN 'mid'
                                    ELSE 'low' END AS bucket, COUNT(*) AS c
                        FROM dg_entities e
                        WHERE e.id IN (SELECT entity_id FROM dg_mentions WHERE extracted_by LIKE 'ingest-task:%')
                        GROUP BY 1
                        """
                    ),
                    {"rev": REVIEW_CONFIDENCE},
                )
            ).all()
        return {
            "tasks_by_status": by_status,
            "confidence": {r.bucket: r.c for r in conf_rows},
        }
    finally:
        await engine.dispose()


@router.delete("/{task_id}")
async def delete_task(task_id: str, _: CurrentUser = Depends(require_permission("ontology:model"))) -> dict:
    """终态行删除；运行中置 aborted（runner 中途检查退出；不强杀进程——v1 契约）。"""
    engine = _engine()
    try:
        async with engine.begin() as conn:
            row = await _fetch_row(
                conn, "SELECT status FROM ingest_tasks WHERE id = CAST(:tid AS uuid)", {"tid": task_id}
            )
            if row is None:
                raise HTTPException(404, "任务不存在")
            if row.status in _ACTIVE_STATES:
                await conn.execute(
                    text("UPDATE ingest_tasks SET status='aborted', finished_at=NOW(), updated_at=NOW() WHERE id = CAST(:tid AS uuid)"),
                    {"tid": task_id},
                )
                return {"id": task_id, "result": "aborted"}
            await conn.execute(text("DELETE FROM ingest_tasks WHERE id = CAST(:tid AS uuid)"), {"tid": task_id})
            return {"id": task_id, "result": "deleted"}
    finally:
        await engine.dispose()


@router.get("/samples")
async def list_samples(_: CurrentUser = Depends(require_permission("system:access"))) -> dict:
    """可建任务的样例清单（G3 双通道：有已提取产物 → v1 消费；仅有源文件 → 直连抽取）."""
    engine = _engine()
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT id::text, title, status,
                               COALESCE(jsonb_array_length(outline_json->'ontology'->'entities'), 0) AS entity_count,
                               (source_path IS NOT NULL AND source_path <> '') AS has_source,
                               updated_at
                        FROM kf_samples
                        WHERE (outline_json->'ontology'->'entities' IS NOT NULL
                               AND jsonb_array_length(outline_json->'ontology'->'entities') > 0)
                           OR (source_path IS NOT NULL AND source_path <> '')
                        ORDER BY updated_at DESC LIMIT 100
                        """
                    )
                )
            ).mappings().all()
        return {"samples": [dict(r) for r in rows]}
    finally:
        await engine.dispose()


@router.get("/{task_id}")
async def get_task(task_id: str, _: CurrentUser = Depends(require_permission("system:access"))) -> dict:
    engine = _engine()
    try:
        async with engine.connect() as conn:
            row = await _fetch_row(
                conn,
                """
                SELECT id::text, sample_id::text, sample_title, document_id, force_review, status,
                       error, stats, created_at, started_at, finished_at
                FROM ingest_tasks WHERE id = CAST(:tid AS uuid)
                """,
                {"tid": task_id},
            )
        if row is None:
            raise HTTPException(404, "任务不存在")
        return dict(row._mapping)
    finally:
        await engine.dispose()
