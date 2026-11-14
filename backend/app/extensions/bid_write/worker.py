"""bid_write worker(批十九 T4)——F1 单管线:created→parsing→extracting→
matrix_ready/failed。解析复用 bid_review.parse(save_raw/parse_raw/build_ocr_fn/
docs_from_entries,材料目录按 (owner_id, task_id) 隔离,task id 不冲突);抽取
复用 bid_review.engine.extract 分片/归一/quote 核验原语,**字段路径限商务子集**
(contracts.COMMERCIAL_TENDER_SUBSET;tender-only,无 bid docs)。

M0 简化(诚实记账):routers 直推单跑,无 claimer 重投循环(失败终态 failed
落因,重投面挂批二十与生成管线同批);模型函数镜像 bid_review.worker._default_
extract_fn 归并逻辑(子集版,首见非 null 采纳同口径)。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.bid_write import contracts, crud, matrix
from app.extensions.bid_write.models import WriteTask

logger = logging.getLogger(__name__)


def _default_extract_fn():
    """生产 LLM 抽取接线(子集版):复用 bid_review.worker 的模型解析/重试核
    (_resolve_model_name/_invoke_json)与 extract 分片 prompt 原语;归并=首见非
    null 采纳(同审查端口径,spec D7)。无可用模型抛 ExtractNotConfigured→
    advance 落 failed(诚实,不假交付)。同步函数,advance 以 to_thread 卸载。"""
    from app.extensions.bid_review import worker as review_worker
    from app.extensions.bid_review.engine.extract import build_extract_prompt, shard_docs

    name = review_worker._resolve_model_name()
    if not name:

        def _fn(docs: list[dict], field_paths: list[str]) -> dict:
            raise review_worker.ExtractNotConfigured("config.yaml 无可用模型(商务要素抽取未执行)")

        return _fn

    from deerflow.models.factory import create_chat_model

    model = create_chat_model(name)
    cap = review_worker._extract_max_tokens()
    if cap:
        model = model.bind(max_tokens=cap)
    logger.info("bid_write tender extraction using model %s(max_tokens=%s)", name, cap or "config")

    def _fn(docs: list[dict], field_paths: list[str]) -> dict:
        merged: dict[str, Any] = {}
        merged_prov: dict[str, dict] = {}
        merged_conf: dict[str, float] = {}
        for shard in shard_docs(docs) or [[]]:
            payload = review_worker._invoke_json(model, build_extract_prompt(shard, field_paths), "商务要素提取")
            f_raw = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload
            if isinstance(f_raw, dict):
                for k, v in f_raw.items():
                    if k in field_paths and merged.get(k) is None and v is not None:
                        merged[k] = v
            prov = payload.get("provenance") if isinstance(payload, dict) else None
            if isinstance(prov, dict):
                for k, v in prov.items():
                    if k in field_paths and k not in merged_prov and isinstance(v, dict):
                        merged_prov[k] = v
            conf = payload.get("confidence") if isinstance(payload, dict) else None
            if isinstance(conf, dict):
                for k, v in conf.items():
                    if k in field_paths:
                        merged_conf[k] = v
        return {"fields": merged, "provenance": merged_prov, "confidence": merged_conf}

    return _fn


def run_tender_extract(docs: list[dict], extract_fn) -> tuple[dict, dict, dict]:
    """(fields, fields_conf, provenance) 三件组:子集路径抽取→归一→quote 核验。
    与 review build_baseline 同构但限子集(审查端零改动;bid.* 路径不入 prompt)。"""
    from app.extensions.bid_review.engine.extract import normalize_fields, normalize_provenance, verify_quotes

    field_paths = list(contracts.COMMERCIAL_TENDER_SUBSET)
    raw = extract_fn(docs, field_paths)
    if not isinstance(raw, dict):
        raise TypeError(f"extract_fn 须返回 dict,得到 {type(raw).__name__}")
    fields_raw = raw.get("fields") if isinstance(raw.get("fields"), dict) else raw
    fields = normalize_fields(fields_raw, field_paths)
    doc_ids = {str(d.get("doc_id") or "doc") for d in docs}
    role_map = {str(d.get("role")): str(d.get("doc_id") or "doc") for d in docs if d.get("role")}
    provenance = normalize_provenance(raw.get("provenance"), field_paths, doc_ids, role_map)
    provenance = {k: v for k, v in provenance.items() if fields.get(k) is not None}
    conf_raw = raw.get("confidence") if isinstance(raw.get("confidence"), dict) else {}
    verified = verify_quotes(provenance, docs)
    fields_conf = {p: {"conf": conf_raw.get(p), "verified": bool(verified.get(p, False))} for p in field_paths if fields.get(p) is not None}
    return fields, fields_conf, provenance


async def advance_write_task(db: AsyncSession, task_id: str, owner_id: str, extract_fn=None) -> WriteTask:
    """状态机单步:created→parsing→extracting→matrix_ready/failed。仅 created
    可推进(直推单跑;并发二跑=状态非 created 直接返回,无双跑)。"""
    from app.extensions.bid_review import parse

    task = await crud.get_task(db, task_id, owner_id)
    if task is None:
        raise ValueError(f"bid_write task {task_id} not found for owner {owner_id}")
    if task.status != "created":
        return task  # 并发方已领走/已终态,本侧退出
    try:
        await crud.set_status(db, task, "parsing", progress={"stage": "parsing", "pct": 10, "msg": "解析招标文件"})
        raw_entries = [e for e in ((task.engine_meta or {}).get("docs") or []) if isinstance(e, dict) and e.get("status") == "raw"]
        if not raw_entries:
            raise RuntimeError("任务无招标文件(上传面缺 raw 条目)")
        ocr_fn = await parse.build_ocr_fn(db)
        parsed = [await parse.parse_raw(owner_id, task.id, entry, ocr_fn) for entry in raw_entries]
        # Persist the parsed manifest before docs_from_entries: it skips every
        # entry still marked raw, which silently produced an empty matrix.
        meta = dict(task.engine_meta or {})
        by_slug = {str(item.get("slug")): item for item in parsed}
        meta["docs"] = [by_slug.get(str(entry.get("slug")), entry) for entry in meta.get("docs") or [] if isinstance(entry, dict)]
        task.engine_meta = meta
        await db.commit()
        await db.refresh(task)
        docs = parse.docs_from_entries(owner_id, task.id, [e for e in (task.engine_meta or {}).get("docs") or [] if isinstance(e, dict)])
        await crud.set_status(db, task, "extracting", progress={"stage": "extracting", "pct": 50, "msg": "商务要素提取中(tender-only)"})
        if extract_fn is None:
            extract_fn = _default_extract_fn()
        fields, fields_conf, provenance = await asyncio.to_thread(run_tender_extract, docs, extract_fn)
        meta = dict(task.engine_meta or {})
        meta["schema_version"] = contracts.SCHEMA_VERSION
        meta["provenance"] = provenance
        meta["fields_conf"] = fields_conf
        meta["fields"] = fields  # 批廿一 M2:生成/预审查消费面(抽取快照持久化)
        task.engine_meta = meta
        await db.commit()
        await db.refresh(task)
        rows = matrix.assemble_matrix(fields, fields_conf)
        await crud.replace_matrix(db, task.id, rows)
        try:  # 批廿一 M2:matrix_ready 落库即自动预审查(material M0 缺省空→诚实 blocked)
            await generate_and_record(db, task, owner_id, knobs=meta.get("knobs") or {})
            await ensure_generated_document(db, task, owner_id)
        except Exception:  # noqa: BLE001  预审查/生成非致命:主状态不回滚不落 failed
            logger.exception("bid_write task %s auto precheck failed (non-fatal)", task_id)
        n_star = sum(1 for r in rows if r["star"])
        n_blocked = sum(1 for r in rows if r["status"] == "blocked")
        return await crud.set_status(db, task, "matrix_ready", progress={"stage": "matrix_ready", "pct": 100, "msg": f"响应矩阵 {len(rows)} 行(★{n_star}/blocked {n_blocked})"})
    except Exception as exc:  # noqa: BLE001  M0 单跑无重投:终态 failed 落因(重投面挂批二十)
        logger.exception("bid_write task %s advance failed", task_id)
        await db.rollback()
        task = await crud.get_task(db, task_id, owner_id)
        if task is not None:
            return await crud.set_status(db, task, "failed", error=str(exc)[:2000])
        raise


async def _infra_fail(task_id: str, exc: Exception, owner_hint: str | None = None) -> None:
    """直推包装崩溃兜底(routers._advance_background 用):独立短会话落 failed。"""
    from app.extensions.database import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        task = await crud.get_task(db, task_id, owner_hint) if owner_hint else None
        if task is None:
            return
        await crud.set_status(db, task, "failed", error=str(exc)[:2000])


async def build_task_ctx(db: AsyncSession, task: WriteTask, owner_id: str, *, knobs: dict | None = None) -> dict:
    """批廿一 M2:meta.fields+矩阵行(排除 status=blocked 卡点行,批十九禁入生成
    面)+knobs 合并 → executor 契约 ctx(纯装配;material=M0 缺省空=诚实降级面
    BL-001)。生成器消费键白名单:clause_id/kind/source_path/requirement/star/
    strategy/target_section/evidence_refs/status。"""
    from app.extensions.bid_write.generate import build_ctx as assemble_ctx

    meta = dict(task.engine_meta or {})
    rows = await crud.list_matrix(db, task.id, owner_id)
    row_dicts = [
        {
            "clause_id": r.clause_id,
            "kind": r.kind,
            "source_path": r.source_path,
            "requirement": r.requirement,
            "star": r.star,
            "strategy": r.strategy,
            "target_section": r.target_section,
            "evidence_refs": r.evidence_refs or [],
            "status": r.status,
        }
        for r in rows
        if r.status != "blocked"
    ]
    k = dict(meta.get("knobs") or {})
    k.update(knobs or {})
    pol = await crud.get_policy(db, owner_id)  # 批廿三 P1-β:policy 透传(缺→{}=零 policy 现行为)
    ld = pol.get("letter_defaults") or {}
    return assemble_ctx(
        dict(meta.get("fields") or {}),
        row_dicts,
        await crud.collect_material(db, owner_id),  # 批廿二 P1-α:素材库装配(meta 面废除)
        unit_prices=k.get("unit_prices"),
        sign_date=k.get("sign_date") or "",
        price_note=k.get("price_note") or "",
        general_commitments=k.get("general_commitments"),
        page_estimates=k.get("page_estimates"),
        total_pages=k.get("total_pages"),
        tax_rate=float(pol["tax_rate"]) if pol.get("tax_rate") is not None else 0.13,
        price_adjust_mechanism=bool(pol["price_adjust_mechanism"]) if pol.get("price_adjust_mechanism") is not None else True,
        letter_defaults=ld or None,
        warranty_period=str(k.get("warranty_period") or ""),  # 批廿五 P1-δ:knobs 直通(L4-001 输入面)
    )


def _l4_model_fn():
    """L4 语义审查模型接线(批廿四 P1-γ;镜像 bid_review.worker._default_model_fn
    先例):模型选择同 extraction(_resolve_model_name→EAI_BID_REVIEW_MODEL/config
    首项,写侧不另设 env=同一把模型尺);ainvoke 异步禁同步堵环;无可用模型返回
    恒抛闭包,L4 逐规则隔离降级 ERROR→水印保持,绝不静默假绿。"""
    from app.extensions.bid_review import worker as review_worker
    from app.extensions.bid_review.worker import ModelNotConfigured

    name = review_worker._resolve_model_name()
    if not name:

        def _fn(messages):
            raise ModelNotConfigured("config.yaml 无可用模型(L4 语义审查逐规则降级 ERROR→水印保持)")

        return _fn

    from deerflow.models.factory import create_chat_model

    model = create_chat_model(name)
    logger.info("bid_write L4 semantic review using model %s", name)

    async def _fn(messages):
        return await model.ainvoke(messages)

    return _fn


async def ensure_generated_document(db: AsyncSession, task: WriteTask, owner_id: str) -> bool:
    """首次生成后把 products 装配成正文 AST 落库(批三十四)。

    只在任务尚无正文、且没有任何审批修订时落库,绝不覆盖人工编辑或冻结快照。
    返回 True=本次创建;False=已有正文/修订或装配失败(非致命,生成门禁仍以
    verdict 为准)。装配失败只记日志,不让生成主流程假成功或假失败。
    """
    existing = await crud.get_document(db, task_id=task.id, owner_id=owner_id)
    if existing is not None:
        return False
    latest = await crud.latest_revision(db, task.id, owner_id)
    if latest is not None:
        return False
    try:
        from app.extensions.bid_write.generate.ast import products_to_ast

        ctx = await build_task_ctx(db, task, owner_id)
        ast = products_to_ast(ctx.get("products") or {})
        await crud.put_document(
            db,
            task_id=task.id,
            owner_id=owner_id,
            ast=ast,
            schema_version=contracts.DOCUMENT_AST_SCHEMA_VERSION,
        )
        return True
    except Exception:  # noqa: BLE001  正文装配非致命;生成门禁/审批仍按事实面
        logger.exception("bid_write task %s materialize document failed (non-fatal)", task.id)
        return False


async def generate_and_record(db: AsyncSession, task: WriteTask, owner_id: str, *, knobs: dict | None = None) -> dict:
    """批廿一 M2:装配→断言+规则预审查→导出门禁→skill_run 落库。返回 verdict=
    run_export_gate 全形(blocked/reasons/watermark/results/双计数),gaps 断言
    维度直接消费。批廿三 P1-β:计时+compute_metrics 落 verdict["metrics"]
    (无新表;聚合端点 crud.list_skill_runs 消费)。"""
    import time

    from app.extensions.bid_write.metrics import compute_metrics
    from app.extensions.bid_write.precheck import run_export_gate

    t0 = time.perf_counter()
    ctx = await build_task_ctx(db, task, owner_id, knobs=knobs)
    export = await run_export_gate(ctx, l4_model_fn=_l4_model_fn())  # 批廿四 P1-γ:L4 语义审查面(advisory;无承诺→参与卡空零模型调用)
    rows = await crud.list_matrix(db, task.id, owner_id)  # 批廿五 P1-δ:manual_edit_ratio 采样源(确认态占比)
    export["metrics"] = compute_metrics(
        ctx,
        export,
        duration_ms=round((time.perf_counter() - t0) * 1000),
        manual_confirmed=sum(1 for r in rows if r.status == "confirmed"),
        rows_total=len(rows),
    )
    await crud.record_skill_run(db, task.id, owner_id, verdict=export, skills="ALL", schema_version=contracts.SCHEMA_VERSION, blocked=export["blocked"])
    return export
