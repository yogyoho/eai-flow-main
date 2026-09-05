# EAI-CUSTOM: forked from app.extensions.contract_price.service (geo-sample-bank Phase 1).
# Phase 1 无 skill 依赖——解析/脱敏全部 in-process async；compile 子进程模式在 Phase 2 (T7) 落地。
# ⚡ 调整 1：storage 的阻塞 MinIO 调用一律 asyncio.to_thread（本仓库有 blocking-IO 门，
#   T3 质量审查指定；parsers 的 CPU 重活已在 parsers.parse_document 内部 to_thread）。
# ⚡ 调整 3（质量审查 Important）：except 路径先 rollback 再守护式 commit——原异常可能
#   本身就是 DB 故障（PendingRollbackError/InterfaceError），裸 commit 会二次抛并丢失失败落账。
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from . import crud, parsers, storage
from .redactor import redact_text

log = logging.getLogger("geo_samples.service")

# --- Phase 2 T7：模块级编译（子进程 bank_compile + RAGFlow 样例整体分发）的常量区 --------------
# 模板同 contract_price.service：skills 迁移目录必须与盘面一致，否则子进程静默失败（bug-526），
# 由 test_compile_skill_dir_guard 守护。parents[4]: geo_samples -> extensions -> app -> backend -> repo root。
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SKILL_DIR = _REPO_ROOT / "skills" / "public" / "geological-report"
_COMPILE_TIMEOUT_S = 1800.0  # bank_compile 含逐组 calibrate 子进程，长报告实测分钟级；30 分钟硬顶
_PUSH_BUDGET_S = 900.0  # RAGFlow 分发预算：与子进程相加 < 60min sweep 线，防长尾拖过互斥造成并发编译写共享 references
_RAGFLOW_DATASET_ENV = "GSB_RAGFLOW_DATASET_ID"
# 切片库固定名：/pipeline/init-ragflow 管理按钮按此幂等收敛（部署后手动点一次即可）；
# 分发解析链（resolve_ragflow_dataset_id）= env 覆写 > 同名库 > skipped。
GSB_RAGFLOW_DATASET_NAME = "geo-samples-slices"
_GSB_DATASET_SEED = {"chunk_method": "naive", "parser_config": {}}
# 系统知识库注册（/pipeline/init-ragflow 时同步写入 knowledge_bases 表；前端按名只读识别）
GEO_SLICES_KB_NAME = "固体矿产报告切片库"


def is_geo_slices_kb_name(name: str | None) -> bool:
    """知识库名是否为地质切片系统库（knowledge 文件列表投影分支 + 前端只读识别，与前端 helper 同源同取舍）。"""
    return name == GEO_SLICES_KB_NAME


# RAGFlow run 态 → 知识库文件列表 DocStatusBadge 三态（success/pending/failed）
_RUN_STATUS_MAP = {"DONE": "success", "RUNNING": "pending", "UNSTART": "pending", "FAIL": "failed"}


async def project_slices_as_documents(kb, skip: int = 0, limit: int = 50) -> tuple[list, int]:
    """切片库文件列表投影：切片只写 RAGFlow（绕过 knowledge documents 表），文件列表实时列 dataset（只读视图）。

    同法规库投影先例（law.service.project_laws_as_documents，spec 2026-09-05）：知识库详情页
    不因「documents 表无行」而显示空列表。RAGFlow 不可达/未配置时返回空页不抛错（只读视图，
    主数据在 RAGFlow 控制台可见）；状态不轮询——列表页自身会刷新。
    """
    from app.extensions.config import get_extensions_config
    from app.extensions.knowledge import client as ragflow_client_mod
    from app.extensions.schemas import DocumentResponse

    cfg = get_extensions_config().ragflow
    if not kb.ragflow_dataset_id or not cfg.api_key:
        return [], 0
    client = ragflow_client_mod.RAGFlowClient(api_key=cfg.api_key, base_url=cfg.base_url)
    try:
        resp = await client.list_documents(kb.ragflow_dataset_id, page=skip // max(limit, 1) + 1, size=limit)
    except Exception:  # noqa: BLE001 —— 只读投影是展示层，不可达不阻断详情页
        log.warning("slices kb projection: ragflow list failed (dataset=%s)", kb.ragflow_dataset_id)
        return [], 0
    payload = resp.get("data") or {}
    docs = payload.get("docs", []) if isinstance(payload, dict) else list(payload)
    total = int(payload.get("total") or 0) if isinstance(payload, dict) else len(docs)
    items = []
    for d in docs:
        created_ms = d.get("create_time")
        created = datetime.fromtimestamp(created_ms / 1000, UTC) if isinstance(created_ms, (int, float)) and created_ms > 0 else datetime.now(UTC)
        items.append(
            DocumentResponse(
                id=uuid.UUID(str(d.get("id"))),
                knowledge_base_id=kb.id,
                name=str(d.get("name") or ""),
                file_path="",
                file_size=int(d.get("size") or 0),
                file_type=None,
                ragflow_document_id=str(d.get("id")),
                status=_RUN_STATUS_MAP.get(str(d.get("run") or "").upper(), "pending"),
                error_message=None,
                created_at=created,
            )
        )
    return items, total


# ⚡ 调整 2：finish_run 走 best-effort 包装（Task 7 实测落定）。plan 原文在 try 内裸调
# crud.finish_run，run-history 记账失败会把已 commit 成功的 parsed/redacted 状态改写成
# failed（状态机被记账层污染），且 except 分支里的二次 finish_run 抛异常会击穿「后台任务
# 不抛出」契约。记账是可观测性元数据：失败只 log.exception，run 行停留在 running，
# 绝不回滚管线结论。（也使 plan 测试里未 patch finish_run 的两条用例可用 MagicMock db 通过。）
async def _finish_run(db: AsyncSession, run_id: str, status: str, detail: str | None) -> None:
    try:
        await crud.finish_run(db, run_id, status, detail)
    except Exception:  # noqa: BLE001 —— 记账 best-effort，绝不掩盖管线结论
        log.exception("finish_run accounting failed for %s (status=%s)", run_id, status)


async def run_parse(db: AsyncSession, document_id: str, run_id: str) -> None:
    """后台任务：raw → md（work/）。任何异常 → status=failed + run 落账，除 db 会话彻底不可用外不向调用方抛出。
    R2 三段式：get → commit 释放连接 → 重活（OCR 最长 1800s）→ 重取文档校验漂移再落 parsed。
    重取用 populate_existing 绕过 identity map（expire_on_commit=False 下普通 get 看不到他方
    会话已提交的改判）；守卫丢弃非 uploaded/failed/parsed 的漂移态（今日可达路径已被端点级
    has_running_run 闸门封闭，本守卫防护 Phase 2 新增状态写入者（compiled 等））；doc 消失
    （理论删除路径）→ failed run。"""
    doc = await crud.get_document(db, document_id)
    if doc is None:
        await _finish_run(db, run_id, "failed", "document not found")
        return
    raw_uri, file_name, report_id = doc.raw_uri, doc.file_name, doc.report_id
    await db.commit()  # R2：释放连接再进重活（OCR 最长 1800s，占池会楔死无关请求）
    try:
        raw = await asyncio.to_thread(storage.get_object, raw_uri)
        md, mode = await parsers.parse_document(file_name, raw)  # 重活（内含 to_thread/OCR）
        doc = await crud.get_document_fresh(db, document_id)  # 重活后重取——populate_existing 绕过 identity map 才见 DB 真值
        if doc is None or doc.status not in ("uploaded", "failed", "parsed"):
            await _finish_run(db, run_id, "failed", f"document state changed during parse: {doc.status if doc else 'gone'}")
            return
        doc.work_uri = await asyncio.to_thread(storage.put_work, doc.report_id, md.encode("utf-8"))
        doc.parse_mode = mode
        doc.status = "parsed"
        await db.commit()
        await _finish_run(db, run_id, "done", f"mode={mode}")
    except Exception as exc:  # noqa: BLE001 —— 后台任务必须吞异常落账
        log.exception("parse failed for %s (%s)", report_id, document_id)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            log.exception("rollback failed after parse failure (%s)", document_id)
        doc.status = "failed"
        doc.parse_mode = "failed"
        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            log.exception("failure-status commit failed (%s) — doc keeps prior status", document_id)
        await _finish_run(db, run_id, "failed", f"{type(exc).__name__}: {exc}")


async def run_redact(db: AsyncSession, document_id: str, run_id: str) -> None:
    """后台任务：work/parsed.md → 规则脱敏 → clean/source.md + 事件流水。
    事件与 doc 状态在同一 commit 原子落库（crud.add_redactions 不自行 commit）；
    异常 → status=failed + run 落账，除 db 会话彻底不可用外不向调用方抛出。
    R2 三段式（P5 ledger A 对齐 run_parse）：get → commit 释放连接 → 重活（下载+规则
    脱敏）→ get_document_fresh 重取校验漂移再落 redacted。守卫丢弃非 parsed 漂移态——
    今日可达路径已被端点级双重闸门封闭，本守卫防护未来的新增状态写入者；doc 消失
    （理论删除路径）→ failed run。"""
    doc = await crud.get_document(db, document_id)
    if doc is None:
        await _finish_run(db, run_id, "failed", "document not found")
        return
    work_uri = doc.work_uri
    await db.commit()  # R2：释放连接再进重活（同 run_parse——占池会楔死无关请求）
    try:
        text_bytes = await asyncio.to_thread(storage.get_object, work_uri)
        clean, events = redact_text(text_bytes.decode("utf-8"))
        doc = await crud.get_document_fresh(db, document_id)  # 重活后重取——populate_existing 绕过 identity map 才见 DB 真值
        if doc is None or doc.status != "parsed":
            await _finish_run(db, run_id, "failed", f"document state changed during redact: {doc.status if doc else 'gone'}")
            return
        doc.clean_uri = await asyncio.to_thread(storage.put_clean, doc.report_id, clean.encode("utf-8"))
        await crud.add_redactions(db, doc.id, events)
        summary: dict[str, int] = {}
        for e in events:
            summary[e["rule"]] = summary.get(e["rule"], 0) + 1
        doc.redaction_summary = json.dumps(summary, ensure_ascii=False)
        doc.status = "redacted"
        await db.commit()
        await _finish_run(db, run_id, "done", json.dumps(summary, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        log.exception("redact failed for %s (%s)", getattr(doc, "report_id", "?"), document_id)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            log.exception("rollback failed after redact failure (%s)", document_id)
        doc.status = "failed"
        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            log.exception("failure-status commit failed (%s) — doc keeps prior status", document_id)
        await _finish_run(db, run_id, "failed", f"{type(exc).__name__}: {exc}")


async def apply_review(db: AsyncSession, document_id: str, decision: str, note: str | None) -> None:
    """人工抽审闸门：approve → reviewed；reject → 退回 redacted 并留 note。"""
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise ValueError("document not found")
    if doc.status != "redacted":
        raise ValueError(f"仅 redacted 状态可审（当前 {doc.status}）")
    if decision not in ("approve", "reject"):
        raise ValueError("decision 必须是 approve/reject")
    doc.status = "reviewed" if decision == "approve" else "redacted"
    doc.review_note = note
    await db.commit()


# --- Phase 2 T7：模块级编译（POST /pipeline/compile 的后台编排） -----------------------------


def _prepare_compile_workspace(docs: list, wd: Path) -> list[dict]:
    """同步体（一律经 asyncio.to_thread 调用）：逐份下载 clean 正文到 <rid>/source.md 并写 manifest.json。

    manifest 条目 {report_id, stage, mineral, file_name}——report_id 已由 UploadMeta slug 约束保证
    目录名安全（bank_compile 侧另有非 slug 条目级跳过兜底）。返回条目列表供调用方复用。
    """
    entries: list[dict] = []
    for d in docs:
        body = storage.get_object(d.clean_uri)  # 阻塞 MinIO——只在线程内执行
        d_dir = wd / d.report_id
        d_dir.mkdir(parents=True, exist_ok=True)
        (d_dir / "source.md").write_bytes(body)
        entries.append({"report_id": d.report_id, "stage": d.stage, "mineral": d.mineral, "file_name": d.file_name})
    (wd / "manifest.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return entries


async def resolve_ragflow_dataset_id() -> str:
    """分发目标解析链：env GSB_RAGFLOW_DATASET_ID（部署级覆写）→ 按固定名查找
    （/pipeline/init-ragflow 按钮创建的库）→ 空串=未配置（调用方走 skipped 降级）。

    按名兜底让「初始化切片库」按钮建库后无需改 env 即生效；env 仍留给离线部署指向
    各环境自己的 dataset id。未配置 RAGFlow / 查找失败一律返回空串——分发是辅助通道
    （spec §7），解析失败绝不让编译 run 失败。
    """
    env_id = os.environ.get(_RAGFLOW_DATASET_ENV, "").strip()
    if env_id:
        return env_id
    from app.extensions.config import get_extensions_config  # lazy——同 push
    from app.extensions.knowledge import client as ragflow_client_mod

    cfg = get_extensions_config().ragflow
    if not cfg.api_key:
        return ""
    client = ragflow_client_mod.RAGFlowClient(api_key=cfg.api_key, base_url=cfg.base_url)
    try:
        ds = await client.get_dataset_by_name(GSB_RAGFLOW_DATASET_NAME)
    except Exception as exc:  # noqa: BLE001 —— RAGFlow 不可达 = 走 skipped 降级，不炸编译
        log.warning("resolve ragflow dataset by name failed (degrade to skip): %s", exc)
        return ""
    return (ds or {}).get("id") or ""


async def push_reports_to_ragflow(workdir: Path, dataset_id: str, report_ids: list[str]) -> int:
    """把每份样例的 clean 全文**整体**上传 RAGFlow（命名 <report_id>.md），返回上传份数。

    产品裁决（2026-09-05）：RAGFlow 分发单元=样例整体，分片交给数据集自身解析（naive）——
    不再按章节预切分入库。章节切分产物（references/samples_bank/）仍落 repo，供范文导航
    （bank_index）/SL3 指纹/ore_pack 抽取消费，只是不再是 RAGFlow 通道的入库单元。
    幂等契约同旧切片分发：分页 list_documents 建 name→id 映射，同名先删再传（重编译不滞留
    旧版），parse 触发服务端分片，绝不 wait_for_parsing_complete（>100 文档轮询恒超时）。
    workdir = _prepare_compile_workspace 产物（<rid>/source.md 已就位）；缺文件的报告跳过。
    """
    from app.extensions.config import get_extensions_config  # lazy——gateway 启动路径零 ragflow 依赖
    from app.extensions.knowledge import client as ragflow_client_mod

    cfg = get_extensions_config().ragflow
    client = ragflow_client_mod.RAGFlowClient(api_key=cfg.api_key, base_url=cfg.base_url)

    existing: dict[str, str] = {}
    page = 1
    while True:
        resp = await client.list_documents(dataset_id, page=page, size=100)
        payload = resp.get("data") or {}
        docs = payload.get("docs", []) if isinstance(payload, dict) else list(payload)
        if not docs:
            break
        existing.update({d["name"]: d["id"] for d in docs})
        total = payload.get("total") if isinstance(payload, dict) else None
        if total is None or page * 100 >= int(total):
            break
        page += 1

    pushed = 0
    for rid in report_ids:
        path = workdir / rid / "source.md"
        if not path.is_file():
            continue
        name = f"{rid}.md"
        if name in existing:
            await client.delete_document(dataset_id, existing[name])
        up = await client.upload_document(dataset_id, str(path), file_name=name)
        doc_id = (up.get("data") or {}).get("id")
        if not doc_id:
            raise RuntimeError(f"ragflow upload {name}: response missing document id")
        await client.parse_document(dataset_id, doc_id)
        pushed += 1
    return pushed


async def run_compile(db: AsyncSession, run_id: str, stage: str | None = None, mineral: str | None = None, document_id: str | None = None) -> None:
    """模块级编译后台任务（never-raise 契约同 run_parse）。

    编排链：reviewed 清单（document_id 给定时改单文档域：fresh 重取且须 reviewed；空 →
    failed 快速返回，不起子进程）→ commit 释放连接（R2 同款，下载/子进程阶段不占池）→
    to_thread 准备工作区（MinIO 下载 clean 到 <rid>/source.md + manifest.json）→ 子进程
    bank_compile（--workdir/--references/--python，cwd=技能目录，1800s wait_for 硬顶超时
    kill）→ RAGFlow 样例整体分发（辅助通道，900s 预算封顶：解析链未配置记 skipped；超预算/push
    异常只记 detail 不回滚编译结论，spec §7 降级链——子进程+分发相加恒 < 60min sweep 线，
    防长尾拖过互斥造成并发编译写共享 references）→ 按 manifest 批量写回：get_document_fresh
    读 DB 真值且仅 reviewed→compiled，漂移者记 detail 跳过 → commit → done。任何异常 →
    rollback（compile 无 doc 单体，失败不改任何 gsb_documents 状态）→ failed 落账。
    临时工作区 finally 清理。
    """
    wd: Path | None = None
    try:
        if document_id is not None:
            # 单文档域（逐行编译分发）：fresh 重取防端点→后台间隙状态漂移（run_redact 同款守卫）；
            # reviewed/compiled 均可（重编译幂等——compiled 行写回阶段本就仅 reviewed→compiled，状态不回退）
            doc = await crud.get_document_fresh(db, document_id)
            docs = [doc] if doc is not None and doc.status in ("reviewed", "compiled") else []
            if not docs:
                await _finish_run(db, run_id, "failed", "单文档编译：样例不存在或状态已漂移（须 reviewed/compiled）")
                return
        else:
            docs = await crud.list_reviewed(db, stage, mineral)
            if not docs:
                await _finish_run(db, run_id, "failed", "无 reviewed 状态的样例可编译")
                return
        await db.commit()  # R2：先释放连接再进重活——expire_on_commit=False 下 docs 属性仍可读，下载阶段不再占连接 idle-in-tx
        rid_to_id = {d.report_id: d.id for d in docs}  # writeback 用 get_document_fresh（按主键查）的换算表
        wd = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="gsb_compile_"))
        await asyncio.to_thread(_prepare_compile_workspace, docs, wd)
        refs = _SKILL_DIR / "references"
        cmd = [
            sys.executable,
            "-X",
            "utf8",
            str(_SKILL_DIR / "scripts" / "bank_compile.py"),
            "--workdir",
            str(wd),
            "--references",
            str(refs),
            "--python",
            sys.executable,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(_SKILL_DIR), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except (OSError, ValueError) as exc:  # 技能缺失/解释器不可执行（bug-526 同族），守护成 failed run
            await _finish_run(db, run_id, "failed", f"bank_compile spawn failed: {exc}")
            return
        try:
            _out, err = await asyncio.wait_for(proc.communicate(), timeout=_COMPILE_TIMEOUT_S)
        except TimeoutError:
            proc.kill()
            await proc.wait()  # 收尸防僵尸
            await _finish_run(db, run_id, "failed", "timeout")
            return
        if proc.returncode != 0:
            await _finish_run(db, run_id, "failed", f"bank_compile rc={proc.returncode}: {err.decode('utf-8', 'replace')[-500:]}")
            return
        manifest = json.loads(await asyncio.to_thread((wd / "manifest.json").read_text, encoding="utf-8"))
        detail = "slices ok"
        dataset_id = await resolve_ragflow_dataset_id()
        if not dataset_id:
            detail += "; ragflow skipped (dataset not configured——可在管理页点「初始化切片库」)"
        else:
            try:
                # 预算封顶（quality Important-1）：子进程 30min + push 15min < 60min sweep 线，
                # 防长尾 RAGFlow 拖过 sweep 开互斥 → 并发编译写共享 references。超预算与 push
                # 失败同 containment：编译产物已落盘，run 仍 done，只记 incomplete。
                pushed = await asyncio.wait_for(push_reports_to_ragflow(wd, dataset_id, [d.report_id for d in docs]), timeout=_PUSH_BUDGET_S)
                detail += f"; ragflow pushed={pushed}"
            except TimeoutError:
                log.exception("ragflow push budget exceeded (run %s)", run_id)
                detail += f"; ragflow push budget exceeded ({int(_PUSH_BUDGET_S)}s)——run done, push incomplete"
            except Exception as exc:  # noqa: BLE001 —— 分发是辅助通道：编译产物已落盘，失败不回滚结论
                log.exception("ragflow push failed (run %s)", run_id)
                detail += f"; ragflow push failed: {exc}"
        for entry in manifest:
            # 新鲜守卫（quality Minor-3）：get_document_fresh（T2）绕过 identity map 读 DB 真值，
            # 且仅 reviewed → compiled。30min 在途编译期间他方会话的新状态写入者（未来新增）
            # 不得被覆盖；漂移者记入 detail 跳过。该 helper 按主键 id 查——用 list_reviewed
            # 返回行的 report_id→id 映射换算（report_id 全局唯一，等价键）。
            doc = await crud.get_document_fresh(db, rid_to_id[entry["report_id"]])
            if doc is None:
                continue
            if doc.status == "reviewed":
                doc.status = "compiled"
            else:
                detail += f"; compiled skip (state drifted): {entry['report_id']}"
        await db.commit()
        await _finish_run(db, run_id, "done", detail)
    except Exception as exc:  # noqa: BLE001 —— 后台任务必须吞异常落账
        log.exception("compile failed (run %s)", run_id)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            log.exception("rollback failed after compile failure (run %s)", run_id)
        await _finish_run(db, run_id, "failed", f"{type(exc).__name__}: {exc}")
    finally:
        if wd is not None:
            try:
                await asyncio.to_thread(shutil.rmtree, wd, True)
            except Exception:  # noqa: BLE001
                log.exception("compile workspace cleanup failed (%s)", wd)
