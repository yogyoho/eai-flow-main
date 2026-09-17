"""End-to-end pipeline (v2: MinIO + eai-flow-ocr).

Flow: scan MinIO for changed contracts → OCR each via eai-flow-ocr → classify
tables (keep only goods/price) → validate prices (flag glued/implausible) →
DBSCAN cluster → per-cluster stats + outliers → persist cpa_ tables → Excel.

DB ops are best-effort: if postgres-ext is unreachable the pipeline still
parses/clusters/exports, skipping persistence (keeps it usable from host
during dev and testable without a live DB).
"""

import argparse
import asyncio
import base64
import json
import logging
import math
import os
import re
import time
from typing import Any, Optional

from scripts.clustering.engine import cluster_items
from scripts.config import get_config
from scripts.document_parser import from_cache, parse_document, to_cache
from scripts.document_scanner import scan_changed
from scripts.excel_generator import generate_excel
from scripts.price_validator import parse_qty, validate_price
from scripts.project_fields import extract_project_fields
from scripts.stats import compute_stats
from scripts.storage import ContractStore
from scripts.table_classifier import (
    _bboxes_usable,
    _collapse_header,
    _roles_x_from_data,
    classify,
    extract_items_seed,
    looks_like_continuation,
    match_seed,
    seed_category_tail,
)

logger = logging.getLogger(__name__)


async def _update_run_progress(run_id: str | None, progress: dict) -> None:
    """Write a live progress blob to cpa_run_history so the UI can poll it.

    No-op if run_id is unset (e.g. cli run standalone). Failures are swallowed
    (progress is best-effort; it must never abort the pipeline).
    """
    if not run_id:
        return
    try:
        from uuid import UUID

        from sqlalchemy import update

        from scripts.db import async_session
        from scripts.models import CpaRunHistory

        async with async_session() as session:
            await session.execute(
                update(CpaRunHistory).where(CpaRunHistory.id == UUID(run_id)).values(progress=progress)
            )
            await session.commit()
    except Exception as exc:
        logger.debug("progress update skipped: %s", exc)


def _load_seeds() -> list[dict]:
    """Load seed 定位规则(config.json 的 table_seeds;空则注入内置库)。
    与 price_table_keywords 同一配置文件/同一 CPA_CONFIG_JSON 通道。"""
    from scripts.seed_library import DEFAULT_TABLE_SEEDS, normalize_seeds

    path = os.environ.get(
        "CPA_CONFIG_JSON",
        "/app/backend/app/extensions/contract_price/config.json",
    )
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f).get("table_seeds")
        seeds = normalize_seeds(raw)
        if seeds:
            return seeds
    except Exception:
        pass
    return normalize_seeds(DEFAULT_TABLE_SEEDS)


async def _extract_project_fields_with_fallback(
    file_bytes: bytes | None,
    key: str,
    ocr_url: str,
    front_texts: dict,
    store: ContractStore | None = None,
) -> tuple:
    """元数据提取 + 末页兜底(设计 §3): 前3页正则 miss 乙方/签订日期时,
    补 OCR 末2页重试(签字页常在末尾,补充协议尤甚;仅 miss 触发,成本有界)。

    file_bytes 允许为 None(OCR 缓存命中路径不持有原文件): 仅当兜底真的需要
    发起时才经 store 惰性下载;两者皆无或下载失败则放弃兜底,维持前页结果。"""
    fields = extract_project_fields(front_texts)
    if fields[3] and fields[4]:  # supplier, sign_date 都有 → 不兜底
        return fields
    fb = file_bytes
    if fb is None and store is not None:
        try:
            fb = await asyncio.to_thread(store.get, key)
        except Exception as exc:
            logger.warning("metadata tail-OCR fetch failed: %s", exc)
            return fields
    if fb is None:
        return fields
    try:
        _, tail_texts, _ = await parse_document(fb, key, ocr_url, last_pages=2)
    except Exception as exc:
        logger.warning("metadata tail-OCR failed: %s", exc)
        return fields
    merged = dict(front_texts)
    merged.update(tail_texts)
    retry = extract_project_fields(merged)
    # 逐字段择优: 前页已取到的保留,缺的用末页补
    return tuple(f or r for f, r in zip(fields, retry))


def _size_from_quick_fp(quick_fp: str | None) -> int | None:
    """Pull the cached byte-size out of a quick_fp string ('{key}|{size}').

    Used as a cheap change pre-filter so scan_changed can skip re-downloading
    unchanged objects just to re-hash them (the old behavior downloaded the
    whole bucket on every scan — catastrophic at 1000 docs)."""
    if not quick_fp:
        return None
    try:
        return int(str(quick_fp).rsplit("|", 1)[-1])
    except (ValueError, IndexError):
        return None


async def _load_cached_meta() -> dict:
    """Load {minio_key: {"hash": file_hash, "size": int|None}} for incremental
    filtering. ``size`` (parsed from quick_fp) lets scan_changed skip the SHA-256
    download when the object size is unchanged."""
    try:
        from sqlalchemy import select

        from scripts.db import async_session
        from scripts.models import CpaDocument

        async with async_session() as session:
            rows = await session.execute(
                select(
                    CpaDocument.file_name,
                    CpaDocument.file_hash,
                    CpaDocument.quick_fp,
                    CpaDocument.parse_status,
                )
            )
            return {
                name: {"hash": h, "size": _size_from_quick_fp(fp), "parse_status": ps}
                for name, h, fp, ps in rows.all()
            }
    except Exception as exc:
        logger.warning("Could not load cached meta (DB unavailable): %s", exc)
        return {}


def _cell_bbox(table, row_idx: int, col_idx: int) -> list:
    """Read a cell's page-relative bbox from the table's cell_bboxes grid."""
    try:
        row = table.cell_bboxes[row_idx]
        if col_idx < len(row):
            return row[col_idx]
    except (IndexError, TypeError):
        pass
    return [0, 0, 0, 0]


_PURE_NUM = re.compile(r"^\d+(?:\.\d+)?$")
_PURE_NUM_BRACKET = re.compile(r"^[【(]?\d+(?:\.\d+)?[】)]?$")  # tolerate 【20】/（19)


_DN_RE = re.compile(r"DN\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def _extract_tech_params(goods_name: str) -> dict:
    """Extract structured tech params from the goods name for clustering.
    DN (管径) is the most common spec in construction contracts — extracting it
    lets the param vector separate DN40 from DN50 (different products), while
    the text vector handles goods-type separation (阀 vs 管)."""
    params: dict = {}
    m = _DN_RE.search(goods_name)
    if m:
        params["管径"] = m.group(1)
    return params


_NUM_CLEAN_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _clean_cell_num(text: str):
    """轻量干净数值探测: 去千分位逗号后全串是单个数字才返回 float。
    空格/无分隔粘连锁、'9%'、文本一律 None(它们不做 unit/total 候选值)。"""
    t = (text or "").strip().replace(",", "")
    if not t or not _NUM_CLEAN_RE.fullmatch(t):
        return None
    return float(t)


def _qty_text_ok(text: str) -> bool:
    """量文本可信度(bug-3400 终轮守卫): 首个数字之前含字母/汉字的格('m2'、't 1.776')
    不作工程量——parse_qty 的「取首数」契约会把单位文本里的 2 当成数量,经反算污染单价
    (实测 1.31/2=0.66)。'100m2'(数字在前)与干净数/空格粘连锁仍接受。"""
    t = (text or "").strip()
    m = re.search(r"\d", t)
    if not m:
        return False
    return not re.search(r"[A-Za-z一-鿿]", t[: m.start()])


def _raw_price_usable(r: dict) -> bool:
    """finalize 可用性镜像(失败行判据,与下方 finalize 判定保持同步):
    单价/不含税任一可校验,或 合价可校验且工程量>0 可反算。"""
    if validate_price(r.get("price_unit_raw") or "")[0] is not None:
        return True
    if validate_price(r.get("price_untaxed_raw") or "")[0] is not None:
        return True
    total = validate_price(r.get("price_total_raw") or "")[0]
    if total and _qty_text_ok(r.get("qty_raw") or ""):
        q = parse_qty(r.get("qty_raw") or "")
        if q and q > 0:
            return True
    return False


def _rediscover_price_cols(table_rows, roles, header_rows, failing_row_idxs):
    """表级算术价列重推(bug-3400 终轮;重建旧 _rediscover_taxed_price_col 的类,Task5 曾删):
    表内 ≥2 行价格双失败时,扫全部有序列对 (unit=ui,total=tj),找「单价×工程量≈合价(±2%)」
    一致行最多的对。列资格: 干净数值率 ≥60%(粘连锁/税率/文本列出局);量取种子 qty 列,
    其余列按 parse_qty(粘连取首数,如 '824.79 1.20'→824.79)兜底。
    门槛(定案): 一致 ≥3 且 ≥50% 失败行;失败行恰为 2 时改要求 ≥60% 数据行。
    量级守卫: 合价 ≥ 单价 需 ≥80% 双解析行。并列取 total 更靠右、再 unit 更靠右。
    返回 (unit_col, total_col, qty_col) 或 None;调用方记 meta["price_rediscovery"]。"""
    data = table_rows[header_rows:]
    n = len(data)
    if n < 3 or len(failing_row_idxs) < 2:
        return None
    max_cols = max((len(r) for r in data), default=0)
    if max_cols == 0 or max_cols > 32:
        return None
    clean: dict = {}
    qvals: list = []
    for di, row in enumerate(data):
        qrow: list = []
        for ci in range(max_cols):
            cell = row[ci] if ci < len(row) else ""
            qrow.append(parse_qty(cell or ""))
        qvals.append(qrow)
    for ci in range(max_cols):
        vals = {}
        for di, row in enumerate(data):
            v = _clean_cell_num(row[ci] if ci < len(row) else "")
            if v is not None:
                vals[di] = v
        if len(vals) >= 0.6 * n:
            clean[ci] = vals
    if len(clean) < 2:
        return None
    cols = sorted(clean)
    qty_role_col = roles.get("qty") if roles else None
    failing_dis = {ri - header_rows for ri in failing_row_idxs}

    def _qty_hit(di, row, ui, tj):
        """该行 (unit=ui, total=tj) 是否 ±2% 一致;命中返回所用量列,否则 None。"""
        vu = clean[ui].get(di)
        vt = clean[tj].get(di)
        if vu is None or vt is None or vt <= 0 or vu <= 0:
            return None
        cand = []
        if qty_role_col is not None and qty_role_col != ui and qty_role_col != tj:
            cand.append(qty_role_col)
        cand.extend(c for c in cols if c != ui and c != tj and c != qty_role_col)
        for qc in cand:
            q = qvals[di][qc] if qc < len(qvals[di]) else None
            if q and q > 0 and abs(vu * q - vt) <= 0.02 * vt:
                return qc
        return None

    best = None  # (consistent, failing_hit, total_col, unit_col, qty_col)
    for ui in cols:
        for tj in cols:
            if ui == tj:
                continue
            consistent = 0
            failing_hit = 0
            qty_hits: dict = {}
            for di, row in enumerate(data):
                qc = _qty_hit(di, row, ui, tj)
                if qc is None:
                    continue
                consistent += 1
                if di in failing_dis:
                    failing_hit += 1
                qty_hits[qc] = qty_hits.get(qc, 0) + 1
            if len(failing_row_idxs) < 3:
                ok = consistent >= max(3, math.ceil(0.6 * n))
            else:
                ok = consistent >= 3 and failing_hit >= math.ceil(0.5 * len(failing_row_idxs))
            if not ok:
                continue
            # 量级守卫: total ≥ unit 于 ≥80% 双解析行
            both = [(clean[ui][di], clean[tj][di]) for di in clean[ui] if di in clean[tj]]
            if both and sum(1 for vu, vt in both if vt >= vu) < 0.8 * len(both):
                continue
            qty_col = sorted(qty_hits.items(), key=lambda kv: (-kv[1], kv[0] != qty_role_col, kv[0]))[0][0]
            key = (consistent, failing_hit, tj, ui)
            if best is None or key > best[:4]:
                best = (consistent, failing_hit, tj, ui, qty_col)
    if best is None:
        return None
    return best[3], best[2], best[4]


def _rediscover_row_price(row, learned):
    """失败行按学到的 (unit,total,qty) 列直接取价: 单价 validate(含空格粘连拆分);
    单价无效但 合价有效且 量>0 → 合价/量 反算。产出仍走 validate_price,
    失败返回 (None, '') 照旧丢弃——不强行注值。"""
    ui, ti, qi = learned
    unit_p, _, _ = validate_price(row[ui] if ui < len(row) else "")
    if unit_p is not None:
        return unit_p, "算术重推"
    total, _, _ = validate_price(row[ti] if ti < len(row) else "")
    q = parse_qty(row[qi] if qi < len(row) else "")
    if total and q and q > 0:
        return round(total / q, 2), "算术重推: 合价/工程量反算"
    return None, ""


def _lone_row_price(row, qty_col=None):
    """健康表单失败行回退(bug-3400 终轮 tol 边缘伴随,无表级状态,每行一次):
    行内干净数值对 (a,b),b≥a>0,以行内可解析量(种子 qty 列值优先,其余格
    parse_qty 左→右兜底)试 a×量≈b(±2%)→ 单价=a。失败返回 (None, '')。"""
    nums = []
    for ci, cell in enumerate(row):
        v = _clean_cell_num(cell)
        if v is not None:
            nums.append((ci, v))
    q0 = None
    if qty_col is not None and 0 <= qty_col < len(row):
        q0 = parse_qty(row[qty_col] or "")
    if q0 and q0 > 0:
        for ai, a in nums:
            for bi, b in nums:
                if ai == bi or a <= 0 or b < a:
                    continue
                if abs(a * q0 - b) <= 0.02 * b:
                    return a, "算术重推(单行)"
    for ai, a in nums:
        for bi, b in nums:
            if ai == bi or a <= 0 or b < a:
                continue
            for qi, cell in enumerate(row):
                if qi in (ai, bi):
                    continue
                if not _qty_text_ok(cell or ""):
                    continue
                q = parse_qty(cell or "")
                if q and q > 0 and abs(a * q - b) <= 0.02 * b:
                    return a, "算术重推(单行)"
    return None, ""


def _extract_from_tables(tables: list, doc_uri: str, seeds: list[dict] | None = None) -> tuple:
    """严格 seed-only 版分类提取(设计 §2/§3)。

    逐表: match_seed 确认 → extract_items_seed(含分类行传播) → 价格校验/反算。
    未匹配表: 零提取;形似数据表(≥4列)记 unmatched_tables 供 UI 建规则。
    续表: 无表头且形似上一命中表 → 继承其 seed/roles(x-band 抗漂移)。
    分类跨页续传: 表头重复页/续表页通过 initial_category 继承上一表尾部分类
    (多页清单的分类不能退化为页内局部——修订I2);尾态由 seed_category_tail
    对表行重放得出(表尾悬挂的分类行不产 item,extract 结果里看不到)。
    meta 新键: unmatched_tables[] / matched_seeds{}。"""
    items: list[dict] = []
    meta: dict = {
        "tables_found": len(tables),
        "goods_tables": 0,
        "continuation_tables": 0,
        "rows_extracted": 0,
        "skipped": {},
        "unmatched_tables": [],
        "matched_seeds": {},
    }
    active = None  # (seed, roles, roles_x, col_count, category_tail) 续表继承上下文
    for table in tables:
        rows = table.rows or []
        col_count = max((len(r) for r in rows), default=0)
        hit = match_seed(rows, seeds) if seeds else None
        is_cont = (
            hit is None
            and active is not None
            and looks_like_continuation(rows, active[1], active[3], table.cell_bboxes, active[2])
        )
        # 设计已知取舍: 跨 seed 续传优先防 OCR 噪声翻seed——上一表尾部分类可能
        # 泄入后续不同 seed 的表(跨 seed bleed 为已接受 trade-off,不加同 seed 守卫)。
        cat_in = active[4] if active is not None else None  # 上一表尾部分类
        if hit is not None:
            seed, roles, header_rows = hit
            meta["goods_tables"] += 1
            meta["matched_seeds"][seed["display_name"]] = meta["matched_seeds"].get(seed["display_name"], 0) + 1
            roles_x = None
            if _bboxes_usable(rows, table.cell_bboxes):
                roles_x = _roles_x_from_data(rows, table.cell_bboxes, roles, header_rows)
            # 表头重复页: 每页都会 match_seed 命中——initial_category 必须跨表续传,
            # 否则多页清单的分类退化为页内局部(修订I2)
            raw = extract_items_seed(rows, seed, roles, header_rows, table.cell_bboxes, roles_x, initial_category=cat_in)
            name_col = roles.get("name", 0)
            active = (
                seed,
                roles,
                roles_x,
                col_count,
                seed_category_tail(rows, roles, header_rows, table.cell_bboxes, roles_x, cat_in),
            )
        elif is_cont:
            seed, roles, roles_x, _, cat_in = active
            meta["continuation_tables"] += 1
            raw = extract_items_seed(rows, seed, roles, 0, table.cell_bboxes, roles_x, initial_category=cat_in)
            name_col = roles.get("name", 0)
            active = (seed, roles, roles_x, col_count, seed_category_tail(rows, roles, 0, table.cell_bboxes, roles_x, cat_in))
        else:
            ttype, sroles, sroles_x, sheader_rows = classify(rows, None, table.cell_bboxes)
            meta["skipped"][ttype] = meta["skipped"].get(ttype, 0) + 1
            active = None  # 断链:不匹配的表后不继承
            if ttype in ("unclassified", "goods_price") and col_count >= 4:
                # 候选数据表但无 seed 确认 → 记详情供 UI 建规则(设计 §1.2/§9.6);泛型标签判为 goods_price 的无 seed 表同样必须可见(否则 parsed+0提取静默零)
                header, _hr = _collapse_header(rows)
                title = ""
                for r in rows[:3]:
                    non_empty = [c for c in r if (c or "").strip()]
                    if len(non_empty) == 1:
                        title = non_empty[0].strip()
                        break
                meta["unmatched_tables"].append(
                    {
                        "page": table.page_no,
                        "table_idx": table.table_idx,
                        "title": title,
                        "header": [(c or "").strip() for c in header if (c or "").strip()],
                        "col_count": col_count,
                        "row_count": len(rows),
                    }
                )
            continue

        # 价格校验/finalize(seed 角色: price_unit_raw→unit_price, price_untaxed_raw→
        # price_untaxed)。Outlier detection stays at cluster level (_build_groups_db)。
        # bug-3400 终轮: 表级算术价列重推。触发=表内 ≥2 行价格双失败(健康表零触发);
        # 学到 (unit,total,qty) 列后失败行按学到的列直接取价;单失败行走单行回退。
        failing = [r for r in raw if not _raw_price_usable(r)]
        learned = None
        failing_set: set = set()
        lone_idx = None
        if len(failing) >= 2:
            failing_set = {r["row_idx"] for r in failing}
            learned = _rediscover_price_cols(
                table.rows, roles, header_rows, [r["row_idx"] for r in failing]
            )
            if learned is not None:
                meta.setdefault("price_rediscovery", []).append(
                    {
                        "unit_col": learned[0],
                        "total_col": learned[1],
                        "qty_col": learned[2],
                        "rows": len(failing),
                        "page": table.page_no,
                        "table_idx": table.table_idx,
                    }
                )
        elif len(failing) == 1:
            lone_idx = failing[0]["row_idx"]
        for r in raw:
            # Ragged-row fix: if the extracted name is pure-numeric (序号, because
            # a spurious leading empty cell shifted THIS row), find the real name
            # = the first text cell in the row. Per-row because column-level
            # heuristics fail on ragged pages (some rows shifted, others not).
            nm = (r["name"] or "").strip()
            if _PURE_NUM.match(nm) or _PURE_NUM_BRACKET.match(nm):
                row = table.rows[r["row_idx"]] if r["row_idx"] < len(table.rows) else []
                for cell_txt in row:
                    c = (cell_txt or "").strip()
                    if c and not _PURE_NUM.match(c) and not _PURE_NUM_BRACKET.match(c):
                        r["name"] = c
                        break
            unit_p, vstatus_u, reason_u = validate_price(r["price_unit_raw"])
            if r.get("price_untaxed_raw"):
                untaxed, vstatus_n, reason_n = validate_price(r["price_untaxed_raw"])
            else:
                untaxed, vstatus_n, reason_n = None, "ok", ""
            # 反算: 单价缺失/异常 → 合价÷工程量(seed 显式 price_total 列,定义关系
            # 单价 = 合价 ÷ 工程量)。错列不可能通过反算,零误注风险。
            if unit_p is None and r.get("price_total_raw"):
                total, _, _ = validate_price(r["price_total_raw"])
                q = parse_qty(r["qty_raw"] or "") if _qty_text_ok(r.get("qty_raw") or "") else None
                if total and q and q > 0:
                    unit_p = round(total / q, 2)
                    vstatus_u, reason_u = "ok", "合价/工程量反算"
            # bug-3400 终轮: 既有反算仍失败的行 → 学到的列直接取价 / 单行回退。
            # 产出同样经过 validate_price,失败照旧(不强行注值)。
            if unit_p is None and untaxed is None:
                if learned is not None and r["row_idx"] in failing_set:
                    row_cells = table.rows[r["row_idx"]] if r["row_idx"] < len(table.rows) else []
                    unit_p, reason_r = _rediscover_row_price(row_cells, learned)
                    if unit_p is not None:
                        vstatus_u, reason_u = "ok", reason_r
                elif learned is None and lone_idx is not None and r["row_idx"] == lone_idx:
                    row_cells = table.rows[r["row_idx"]] if r["row_idx"] < len(table.rows) else []
                    unit_p, reason_r = _lone_row_price(row_cells, qty_col=roles.get("qty"))
                    if unit_p is not None:
                        vstatus_u, reason_u = "ok", reason_r
            # Skip price-less rows: no usable price (both empty) → useless for
            # price analysis. Don't store them as needs_review noise.
            if unit_p is None and untaxed is None:
                continue
            vstatus = "needs_review" if "needs_review" in (vstatus_u, vstatus_n) else "ok"
            items.append(
                {
                    "goods_name": r["name"],
                    "spec_model": r["spec"],
                    "tech_params": _extract_tech_params(r["name"]),
                    "category": r.get("category"),
                    "quantity": parse_qty(r["qty_raw"] or "") if _qty_text_ok(r.get("qty_raw") or "") else None,
                    "unit": r["unit"],
                    "unit_price": unit_p,  # 含税单价(统计)
                    "price_untaxed": untaxed,  # 不含税单价(审计)
                    "source_doc_uri": doc_uri,
                    "source_page": table.page_no,
                    "source_bbox": _cell_bbox(table, r["row_idx"], name_col),
                    "source_table_idx": table.table_idx,
                    "source_row_idx": r["row_idx"],
                    "confidence": table.mean_confidence,
                    "validation_status": vstatus,
                    "price_reason": reason_u or reason_n,
                }
            )
        meta["rows_extracted"] += len(raw)
    return items, meta


def _cluster_sample_text(goods_name: str, tech_params: dict | None) -> str:
    """聚类样本文本 = 名称 + 分类(同名货物不同分类必须分簇,设计 §1.3)。"""
    cat = ((tech_params or {}).get("category") if isinstance(tech_params, dict) else None) or ""
    return f"{goods_name} {cat}".strip()


def _build_groups_db(result, db_items: list) -> list:
    """Turn clustering output + DB items into cluster group dicts.

    Price stats use ONLY ok/corrected items' unit_price; needs_review items
    still cluster by name (grouped with their goods) but their price is
    excluded from min/max/avg. is_outlier is derived from the ok/corrected
    price distribution.
    """
    groups: list[dict] = []
    for label in sorted(l for l in set(result.labels) if l != -1):
        idxs = [i for i, l in enumerate(result.labels) if l == label]
        members = [db_items[i] for i in idxs]
        prices = [
            m["unit_price"]
            for m in members
            if m.get("validation_status") in ("ok", "corrected")
            and m.get("unit_price") is not None
        ]
        stats = compute_stats(prices)
        threshold = stats.get("outlier_threshold")
        for m in members:
            p = m.get("unit_price")
            m["is_outlier"] = bool(threshold is not None and p is not None and p > threshold)
        groups.append(
            {"name": result.representatives[label], "category": "未分类", "stats": stats, "items": members}
        )
    return groups


def _to_date(s: str | None):
    """YYYY-MM-DD string → date object for the CpaDocument.sign_date column."""
    if not s:
        return None
    try:
        from datetime import date

        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


async def _persist_one_doc(doc: dict, items: list[dict], run_id: str | None = None) -> None:
    """Persist a single document + its items immediately after parse (checkpoint).

    Called from _process_one_doc so every completed doc is durable on disk even
    if the parse run crashes later. Re-parsing a doc deletes its old items first
    (fresh extraction replaces stale rows).
    """
    try:
        from datetime import datetime, timezone

        from sqlalchemy import delete, select

        from scripts.db import async_session
        from scripts.models import CpaDocument, CpaItem

        async with async_session() as session:
            existing = (
                await session.execute(select(CpaDocument).where(CpaDocument.storage_uri == doc["storage_uri"]))
            ).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if existing is None:
                existing = CpaDocument(
                    storage_uri=doc["storage_uri"],
                    file_name=doc["file_name"],
                    file_hash=doc["hash"],
                    file_type=doc["type"],
                    quick_fp=doc.get("quick_fp"),
                    parse_mode=doc.get("parse_mode", "ocr"),
                    parse_status=doc.get("parse_status", "parsed"),
                    confirm_status="pending",
                    parse_meta=doc.get("parse_meta"),
                    page_count=doc.get("page_count"),
                    preview_prefix=doc.get("preview_prefix"),
                    project_name=doc.get("project_name"),
                    project_location=doc.get("project_location"),
                    contract_no=doc.get("contract_no"),
                    supplier=doc.get("supplier"),
                    sign_date=_to_date(doc.get("sign_date")),
                    parsed_at=now,
                )
                session.add(existing)
                await session.flush()
            else:
                existing.file_hash = doc["hash"]
                existing.parse_status = doc.get("parse_status", "parsed")
                existing.confirm_status = "pending"
                existing.parse_meta = doc.get("parse_meta")
                # preview_prefix 只在真有新前缀时覆写: OCR 缓存命中路径 from_cache 的
                # page_preview_b64 恒为空串 → preview loop 不产出前缀,若无条件覆写会把
                # 首解析落好的 MinIO 预览抹成 None → 溯源接口 404。内容变更必然走
                # miss 路径并带全新前缀,故不存在旧前缀被冻结的 stale 风险。
                # 固有缺口: 缓存命中后新命中的规则页无预览 PNG,溯源需 --re-ocr 或全量重解析补齐。
                if doc.get("preview_prefix"):
                    existing.preview_prefix = doc["preview_prefix"]
                existing.parsed_at = now
                if doc.get("project_name"):
                    existing.project_name = doc["project_name"]
                if doc.get("project_location"):
                    existing.project_location = doc["project_location"]
                if doc.get("contract_no"):
                    existing.contract_no = doc["contract_no"]
                if doc.get("supplier"):
                    existing.supplier = doc["supplier"]
                if doc.get("sign_date"):
                    existing.sign_date = _to_date(doc["sign_date"])
                await session.execute(delete(CpaItem).where(CpaItem.document_id == existing.id))
            doc_contract_no = doc.get("contract_no")
            for it in items:
                item_kwargs: dict = {
                    "document_id": existing.id,
                    "goods_name": it["goods_name"],
                    "spec_model": it.get("spec_model"),
                    "category": it.get("category"),
                    "tech_params": it.get("tech_params"),
                    "quantity": it.get("quantity"),
                    "unit": it.get("unit"),
                    "unit_price": it.get("unit_price"),
                    "price_untaxed": it.get("price_untaxed"),
                    "is_outlier": bool(it.get("is_outlier")),
                    "source_page": it.get("source_page"),
                    "source_bbox": it.get("source_bbox"),
                    "source_table_idx": it.get("source_table_idx"),
                    "source_row_idx": it.get("source_row_idx"),
                    "confidence": it.get("confidence"),
                    "validation_status": it.get("validation_status", "ok"),
                    "source_contract_no": doc_contract_no,
                }
                if run_id:
                    from uuid import UUID as _UUID
                    item_kwargs["run_id"] = _UUID(run_id)
                session.add(CpaItem(**item_kwargs))
            await session.commit()
    except Exception as exc:
        logger.warning("Per-doc persist skipped (DB unavailable): %s", exc)


async def _persist_parse(documents: list, all_items: list, run_record: dict, run_id: str | None = None) -> None:
    """Write the run-history record only.

    Documents and items are now persisted per-doc by _persist_one_doc() as each
    _process_one_doc() completes (checkpoint). This function only finalizes the
    run record so the UI can show the run as completed/failed.
    """
    try:
        from scripts.db import async_session
        from scripts.models import CpaRunHistory

        async with async_session() as session:
            session.add(
                CpaRunHistory(**{k: v for k, v in run_record.items() if k in CpaRunHistory.__table__.columns})
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Run record persist skipped (DB unavailable): %s", exc)


async def _persist_clusters(groups: list, run_record: dict) -> None:
    """Phase-2 persist: replace all clusters, reassign item.cluster_id/is_outlier,
    and mark confirmed/skipped docs as 'clustered'."""
    try:
        from sqlalchemy import delete, update

        from scripts.db import async_session
        from scripts.models import CpaCluster, CpaDocument, CpaItem, CpaRunHistory

        async with async_session() as session:
            await session.execute(update(CpaItem).values(cluster_id=None, is_outlier=False))
            await session.execute(delete(CpaCluster))
            # only build clusters + advance docs to 'clustered' on a successful
            # run — a failed run must leave them confirmed/skipped for retry.
            if run_record.get("status") != "failed":
                for group in groups:
                    cluster = CpaCluster(
                        category=group["category"],
                        representative_name=group["name"],
                        status="pending",
                        stats=group["stats"],
                        item_count=len(group["items"]),
                    )
                    session.add(cluster)
                    await session.flush()
                    for m in group["items"]:
                        await session.execute(
                            update(CpaItem)
                            .where(CpaItem.id == m["id"])
                            .values(cluster_id=cluster.id, is_outlier=bool(m.get("is_outlier")))
                        )
                await session.execute(
                    update(CpaDocument)
                    .where(CpaDocument.confirm_status.in_(["confirmed", "skipped", "clustered"]))
                    .values(confirm_status="clustered")
                )
            session.add(
                CpaRunHistory(**{k: v for k, v in run_record.items() if k in CpaRunHistory.__table__.columns})
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Cluster persistence skipped (DB unavailable): %s", exc)


async def _process_one_doc(
    ch: dict,
    store: ContractStore,
    cfg,
    seeds: list[dict],
    sem: asyncio.Semaphore,
    state: dict,
    run_id: str | None,
    total_docs: int,
    re_ocr: bool = False,
) -> None:
    """Parse one changed contract under the concurrency semaphore.

    Mutates the shared ``state`` (documents/all_items/counters). Safe because
    asyncio is single-threaded and these mutate only between awaits. A per-doc
    failure is recorded as a failed document and NEVER aborts the batch — that
    isolation is the whole point of moving off the sequential for-loop.
    """
    async with sem:
        key = ch["key"]
        doc_uri = f"s3://{cfg.minio_bucket}/{key}"
        state["processing"].add(key)  # ponytail: track for progress visibility
        if run_id:
            await _update_run_progress(run_id, {
                "total": total_docs, "done": state["done"], "failed": state["failed_docs"],
                "processing": sorted(state["processing"]), "phase": "parse",
            })
        try:
            cache_key = f"ocr/{ch['hash']}.json"  # 内容寻址:同内容同键,免失效
            cached = None if re_ocr else await asyncio.to_thread(store.get_ocr_cache, cache_key)
            file_bytes = None  # 命中路径无原文件;兜底需要时才经 store 惰性下载
            if cached is not None:
                tables, page_texts, orient_fixed = from_cache(cached)
                logger.info("Cache hit %s: %d tables (skip OCR)", cache_key, len(tables))
            else:
                # MinIO get is a sync blocking call — offload so concurrent docs
                # don't stall the event loop during download.
                # Task 8 元数据末页兜底需 file_bytes 时必须在此分支惰性获取(命中路径无此变量)
                file_bytes = await asyncio.to_thread(store.get, key)
                tables, page_texts, orient_fixed = await parse_document(file_bytes, key, cfg.ocr_service_url)
                # 缓存写入是机会性的: MinIO 写失败绝不能让已成功提取的文档被标 failed。
                try:
                    await asyncio.to_thread(
                        store.put_ocr_cache, cache_key, to_cache(tables, page_texts, orient_fixed)
                    )
                except Exception as exc:
                    logger.warning("OCR cache write failed %s: %s", cache_key, exc)
            items, meta = _extract_from_tables(tables, doc_uri, seeds)
            # 方向归一化页号透传(设计 §3): 溯源提示这些页的预览/坐标来自纠偏后图像。
            meta["orientation_fixed_pages"] = orient_fixed or []
            # 元数据提取 + 末页兜底: 命中路径 file_bytes=None,兜底真的需要发起时
            # 才经 store 惰性下载原 PDF(Task 6 命中路径无 file_bytes 不变量)。
            project_name, project_location, contract_no, supplier, sign_date = (
                await _extract_project_fields_with_fallback(
                    file_bytes, key, cfg.ocr_service_url, page_texts, store=store
                )
            )
            # Persist preview PNGs for every page that has extracted items, so
            # the traceback UI can overlay bboxes. Derived directly from items'
            # source_page — guarantees every item's page has a preview. (The old
            # approach re-classified tables separately, which could disagree with
            # _extract_from_tables' classification → some item pages missed previews.)
            goods_pages: set[int] = set(
                it.get("source_page") for it in items if it.get("source_page")
            )

            preview_prefix = None
            for t in tables:
                if t.page_no in goods_pages and t.page_preview_b64 and not preview_prefix:
                    doc_id = ch["hash"][:8]
                    preview_prefix = store.put_preview(doc_id, t.page_no, base64.b64decode(t.page_preview_b64))
                elif t.page_no in goods_pages and preview_prefix and t.page_preview_b64:
                    store.put_preview(ch["hash"][:8], t.page_no, base64.b64decode(t.page_preview_b64))
            # 缓存命中路径: 预览 PNG 在首解析已按内容哈希落 MinIO,确定性重建指针
            # (修首次落库失败后纯命中重解析的 preview_prefix=None 窗口;新匹配页仍需 --re-ocr 补预览)
            if cached is not None and not preview_prefix:
                preview_prefix = f"previews/{ch['hash'][:8]}/"
            doc_dict = {
                "storage_uri": doc_uri,
                "file_name": key,
                "hash": ch["hash"],
                "type": os.path.splitext(key)[1].lstrip(".").lower() or "pdf",
                "quick_fp": f"{key}|{ch['size']}",
                "parse_mode": "ocr",
                # 严格 seed-only 三态(设计 §1.2): 0表=no_tables(不算失败);
                # 有表全未命中/首页字段缺失=needs_review;否则 parsed。
                "parse_status": (
                    "no_tables"
                    if not meta["tables_found"]
                    else (
                        "needs_review"
                        if (not meta["goods_tables"] and meta["unmatched_tables"])
                        or (not (items or meta["tables_found"]))
                        or (not project_name and not project_location)
                        else "parsed"
                    )
                ),
                "parse_meta": meta,
                "page_count": max((t.page_no for t in tables), default=None),
                "preview_prefix": preview_prefix,
                "project_name": project_name,
                "project_location": project_location,
                "contract_no": contract_no,
                "supplier": supplier,
                "sign_date": sign_date,
            }
            # Checkpoint: persist doc + items immediately so a mid-run crash
            # doesn't lose already-parsed contracts.
            await _persist_one_doc(doc_dict, items, run_id)
            state["docs_processed"] += 1
            state["items_extracted"] += len(items)
            logger.info("Parsed %s: %d tables, %d items", key, meta["tables_found"], len(items))
        except Exception as exc:
            state["failed_docs"] += 1
            logger.warning("Failed to parse %s: %s", key, exc)
            # Persist failed status so the UI shows it immediately.
            await _persist_one_doc(
                {
                    "storage_uri": doc_uri,
                    "file_name": key,
                    "hash": ch["hash"],
                    "type": os.path.splitext(key)[1].lstrip(".").lower() or "pdf",
                    "parse_mode": "ocr",
                    "parse_status": "failed",
                    "parse_meta": {"error": repr(exc)},
                },
                [],
                run_id,
            )
        finally:
            state["processing"].discard(key)
        state["done"] += 1
        if run_id:
            await _update_run_progress(
                run_id, {
                    "total": total_docs, "done": state["done"], "failed": state["failed_docs"],
                    "processing": sorted(state["processing"]), "phase": "parse",
                }
            )


async def run_parse(
    trigger: str = "manual", run_id: str | None = None, force_key: str | None = None, re_ocr: bool = False
) -> int:
    """Phase 1: scan → OCR → classify → validate → persist docs + items.

    No clustering (that is run_cluster, after the user confirms/skips). Returns
    the number of documents processed. ``run_id`` enables live progress polling.
    ``force_key``: re-parse a single MinIO object by key, bypassing the hash
    cache (single-document reparse; preserves doc_id via storage_uri upsert).
    ``re_ocr``: 强制重 OCR(默认读 ocr/{sha256}.json 内容寻址缓存,秒级重解析)。

    Documents are parsed CONCURRENTLY (asyncio.Semaphore) so the OCR service's
    worker pool (OCR_WORKERS) stays fed — each doc's OCR call is an async HTTP
    wait, so the event loop overlaps N in-flight parses. Concurrency defaults to
    the OCR worker count; tune via CPA_PARSE_CONCURRENCY. A single doc failing
    never aborts the batch.
    """
    started = time.monotonic()
    cfg = get_config()
    seeds = _load_seeds()

    try:
        from scripts.db import init_schema
        await init_schema()
    except Exception as exc:
        logger.warning("Schema init skipped (DB unavailable): %s", exc)

    store = ContractStore(cfg)
    cached = await _load_cached_meta()
    changed = scan_changed(store, cached, force_key=force_key)
    logger.info("Scan: %d changed / %d cached contracts", len(changed), len(cached))

    state: dict = {
        "docs_processed": 0,
        "items_extracted": 0,
        "failed_docs": 0,
        "done": 0,
        "processing": set(),  # doc keys currently being parsed (for progress UI)
    }
    error: Optional[str] = None
    total_docs = len(changed)
    if run_id:
        await _update_run_progress(run_id, {"total": total_docs, "done": 0, "failed": 0, "phase": "parse"})

    concurrency = max(1, int(os.environ.get("CPA_PARSE_CONCURRENCY", "4")))
    sem = asyncio.Semaphore(concurrency)
    try:
        await asyncio.gather(
            *(_process_one_doc(ch, store, cfg, seeds, sem, state, run_id, total_docs, re_ocr=re_ocr) for ch in changed)
        )
    except Exception as exc:
        error = repr(exc)
        logger.exception("Parse phase failed")

    duration_ms = int((time.monotonic() - started) * 1000)
    run_record = {
        "trigger_type": trigger,
        "label": f"{'定时' if trigger == 'scheduled' else '手动'}文档解析",
        "status": "failed" if error else "completed",
        "docs_processed": state["docs_processed"],
        "items_extracted": state["items_extracted"],
        "clusters_formed": 0,
        "duration_ms": duration_ms,
        "error": error,
        "scope": {"engine": "ocr-v2", "phase": "parse", "concurrency": concurrency},
    }
    await _persist_parse([], [], run_record, run_id)
    return state["docs_processed"]


async def run_cluster(trigger: str = "manual") -> int:
    """Phase 2: cluster items of all parsed docs (no confirm gate).

    All items cluster by name; price stats use only ok/corrected items
    (needs_review items cluster but their price is excluded). Marks those docs
    'clustered' so the UI advances 已解析 → 已分组. Returns the number of clusters
    formed.
    """
    started = time.monotonic()
    cfg = get_config()
    error: Optional[str] = None
    groups: list = []

    try:
        from sqlalchemy import select

        from scripts.db import async_session
        from scripts.models import CpaDocument, CpaItem

        async with async_session() as session:
            rows = (
                await session.execute(
                    select(CpaItem)
                    .join(CpaDocument, CpaItem.document_id == CpaDocument.id)
                    # 无 confirm 门槛:所有「已解析」(parsed/needs_review)文档的货物
                    # 都参与聚类。价格质量由 item 级 validation_status 把关(needs_review
                    # 归组但不计入均值),不再依赖 doc 级 confirm_status 门槛。
                    .where(CpaDocument.parse_status.in_(["parsed", "needs_review"]))
                )
            ).scalars().all()
            db_items = []
            for r in rows:
                # category 同时进 tech_params(聚类样本文本可见)与顶层键(Excel 读取)。
                tp = dict(r.tech_params or {})
                if r.category and "category" not in tp:
                    tp["category"] = r.category
                db_items.append(
                    {
                        "id": r.id,
                        "goods_name": r.goods_name,
                        "tech_params": tp,
                        "category": r.category,
                        # Numeric(18,2) loads as decimal.Decimal; cast to float so
                        # compute_stats / outlier math (float-based) don't hit
                        # "float * Decimal" TypeErrors.
                        "unit_price": float(r.unit_price) if r.unit_price is not None else None,
                        "validation_status": r.validation_status,
                    }
                )
        logger.info("Cluster phase: %d items from parsed docs", len(db_items))
        if db_items:
            samples = [(_cluster_sample_text(it["goods_name"], it["tech_params"]), it["tech_params"]) for it in db_items]
            result = cluster_items(samples)
            groups = _build_groups_db(result, db_items)
    except Exception as exc:
        error = repr(exc)
        logger.exception("Cluster phase failed")
        groups = []

    duration_ms = int((time.monotonic() - started) * 1000)
    excel_path: Optional[str] = None
    if groups and not error:
        try:
            os.makedirs(cfg.output_dir, exist_ok=True)
            out_path = os.path.join(cfg.output_dir, f"contract-price-{trigger}.xlsx")
            generate_excel(groups, out_path)
            excel_path = out_path
            logger.info("Excel written to %s", out_path)
        except Exception:
            logger.exception("Excel generation failed")

    run_record = {
        "trigger_type": trigger,
        "label": f"{'定时' if trigger == 'scheduled' else '手动'}聚类分析",
        "status": "failed" if error else "completed",
        "docs_processed": 0,
        "items_extracted": 0,
        "clusters_formed": len(groups),
        "duration_ms": duration_ms,
        "error": error,
        "scope": {"engine": "ocr-v2", "phase": "cluster"},
    }
    if excel_path:
        run_record["excel_path"] = excel_path
    await _persist_clusters(groups, run_record)
    return len(groups)


async def run_upload(directory: str) -> int:
    """Phase 0: batch upload .pdf/.docx files from a directory to MinIO + create
    pending document rows (parse_status=pending). Dedup by content hash (skip
    same-content files already uploaded under any filename). After upload, run
    `--phase parse` to extract items."""
    import glob
    import hashlib

    cfg = get_config()
    store = ContractStore(cfg)
    files = sorted(
        f
        for f in glob.glob(os.path.join(directory, "**", "*"), recursive=True)
        if os.path.isfile(f) and f.lower().endswith((".pdf", ".docx"))
    )
    if not files:
        logger.warning("Upload: no .pdf/.docx files found in %s", directory)
        return 0
    logger.info("Upload: %d files found in %s", len(files), directory)

    try:
        from scripts.db import init_schema

        await init_schema()
    except Exception as exc:
        logger.warning("Schema init skipped: %s", exc)

    from sqlalchemy import select

    from scripts.db import async_session
    from scripts.models import CpaDocument

    uploaded = skipped = failed = 0
    async with async_session() as session:
        for i, fpath in enumerate(files, 1):
            fname = os.path.basename(fpath)
            try:
                with open(fpath, "rb") as f:
                    data = f.read()
                if not data:
                    failed += 1
                    logger.warning("[%d/%d] Empty: %s", i, len(files), fname)
                    continue
                digest = hashlib.sha256(data).hexdigest()
                # Dedup: same content already exists under any filename?
                dup = (
                    await session.execute(
                        select(CpaDocument).where(CpaDocument.file_hash == digest).limit(1)
                    )
                ).scalar_one_or_none()
                if dup is not None:
                    skipped += 1
                    logger.info(
                        "[%d/%d] Skip duplicate: %s (already as %s)",
                        i, len(files), fname, dup.file_name,
                    )
                    continue
                # Upload to MinIO + create pending row
                uri = store.put_bytes(fname, data)
                ftype = os.path.splitext(fname)[1].lstrip(".").lower() or "pdf"
                existing = (
                    await session.execute(
                        select(CpaDocument).where(CpaDocument.storage_uri == uri)
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        CpaDocument(
                            storage_uri=uri,
                            file_name=fname,
                            file_hash=digest,
                            file_type=ftype,
                            quick_fp=f"{fname}|{len(data)}",
                            parse_mode="ocr",
                            parse_status="pending",
                            confirm_status="pending",
                        )
                    )
                else:
                    existing.file_hash = digest
                    existing.file_type = ftype
                    existing.quick_fp = f"{fname}|{len(data)}"
                    existing.parse_status = "pending"
                    existing.confirm_status = "pending"
                    existing.parse_meta = None
                    existing.error = None
                await session.commit()
                uploaded += 1
                logger.info(
                    "[%d/%d] Uploaded: %s (%.1fMB)", i, len(files), fname, len(data) / 1048576
                )
            except Exception as exc:
                failed += 1
                logger.warning("[%d/%d] Failed: %s: %s", i, len(files), fname, exc)

    logger.info(
        "Upload done: %d uploaded, %d skipped (dups), %d failed, %d total",
        uploaded, skipped, failed, len(files),
    )
    return uploaded


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Contract price analysis pipeline (v2: OCR, two-phase)")
    parser.add_argument("--phase", choices=["upload", "parse", "cluster"], default="parse")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--run-id", default=None, help="cpa_run_history id for live progress polling")
    parser.add_argument("--force-key", default=None, help="re-parse a single MinIO object key (single-doc reparse, bypasses hash cache)")
    parser.add_argument("--re-ocr", action="store_true", help="reparse 时强制重 OCR(默认读 MinIO OCR 缓存)")
    parser.add_argument("--dir", default=None, help="directory of .pdf/.docx to batch-upload (phase=upload)")
    args = parser.parse_args()
    if args.phase == "upload":
        if not args.dir:
            parser.error("--dir is required for --phase upload")
        n = asyncio.run(run_upload(args.dir))
        print(f"Done. Uploaded {n} file(s).")
    elif args.phase == "parse":
        n = asyncio.run(run_parse(trigger=args.trigger, run_id=args.run_id, force_key=args.force_key, re_ocr=args.re_ocr))
        print(f"Done. Parsed {n} document(s).")
    else:
        n = asyncio.run(run_cluster(trigger=args.trigger))
        print(f"Done. {n} cluster groups.")


if __name__ == "__main__":
    main()
