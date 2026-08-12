# EAI-CUSTOM: forked from contract-price-analysis/scripts/cli.py。
# 与 contract_price 的差异:
#   1. 客户维度(D3):extract_project_fields 多返 customer;_persist_one_doc 经
#      normalizer.resolve_customer 把脏 customer_name 归一到 customer_id,未命中建 pending。
#   2. 字段名:goods_name→part_name,spec_model→spec。
#   3. 去掉 excel_generator(④ MVP 不出 Excel,CspRunHistory 无 excel_path)。
#   4. CPA_* 环境变量 → CSP_*;bucket=csp-parts;默认关键词=备件域。
#   5. run_record 多 customers_resolved 计数。
# OCR 抗漂移逻辑(_rediscover_taxed_price_col / _is_hejia_magnitude / 续页继承)逐字保留。
"""End-to-end pipeline (备件价格体系分析:MinIO + eai-flow-ocr + 客户维度)。

Flow: 扫 MinIO 变更合同 → eai-flow-ocr 解析 → 表分类(只留备件/价格表)→ 价格校验
(标粘连/量级异常)→ 客户归一(脏名→customer_id,D3)→ DBSCAN 聚类 → 每簇统计 + 离群 →
持久化 csp_* 表。两阶段:parse(解析入库)+ cluster(聚类,无 confirm 门槛)。

DB 操作 best-effort:postgres-ext 不可达时管线仍解析/聚类,跳过持久化(便于从 host 调试、
无需活 DB 即可测试)。
"""

import argparse
import asyncio
import base64
import logging
import os
import re
import time
from typing import Optional

from scripts.clustering.engine import cluster_items
from scripts.config import get_config
from scripts.document_parser import parse_document
from scripts.document_scanner import scan_changed
from scripts.normalizer import resolve_customer
from scripts.price_validator import parse_qty, split_glued, validate_price
from scripts.project_fields import extract_project_fields
from scripts.stats import compute_stats
from scripts.storage import SparePartsStore
from scripts.table_classifier import _roles_x_from_data, classify, extract_items, looks_like_continuation

logger = logging.getLogger(__name__)


_DEFAULT_PRICE_KEYWORDS = ["备件清单", "配件清单", "零部件清单", "零件清单", "备品备件", "报价", "暂列"]


async def _update_run_progress(run_id: str | None, progress: dict) -> None:
    """Write a live progress blob to csp_run_history so the UI can poll it。

    run_id 未设(如 cli 单跑)时 no-op。失败吞掉(progress 是 best-effort,绝不中断管线)。
    """
    if not run_id:
        return
    try:
        from uuid import UUID

        from sqlalchemy import update

        from scripts.db import async_session
        from scripts.models import CspRunHistory

        async with async_session() as session:
            await session.execute(
                update(CspRunHistory).where(CspRunHistory.id == UUID(run_id)).values(progress=progress)
            )
            await session.commit()
    except Exception as exc:
        logger.debug("progress update skipped: %s", exc)


def _load_price_keywords() -> list[str]:
    """Load project-configured price-table keywords。

    读管理 API 的 config.json(由 SettingsView → ConfigOut 写),使前端编辑的关键词表真正
    到达分类。文件缺失/不可读(如在 gateway 容器外单跑 skill)时回退默认。
    """
    path = os.environ.get(
        "CSP_CONFIG_JSON",
        "/app/backend/app/extensions/spare_parts/config.json",
    )
    try:
        import json

        with open(path, encoding="utf-8") as f:
            kw = json.load(f).get("price_table_keywords")
        if isinstance(kw, list) and kw:
            return [str(k) for k in kw if k]
    except Exception:
        pass
    return list(_DEFAULT_PRICE_KEYWORDS)


def _size_from_quick_fp(quick_fp: str | None) -> int | None:
    """Pull the cached byte-size out of a quick_fp string ('{key}|{size}')。

    作廉价变更预过滤,让 scan_changed 跳过对未变对象的重下载+重 hash(旧行为每次扫
    全 bucket——1000 文档时灾难性)。
    """
    if not quick_fp:
        return None
    try:
        return int(str(quick_fp).rsplit("|", 1)[-1])
    except (ValueError, IndexError):
        return None


async def _load_cached_meta() -> dict:
    """Load {minio_key: {"hash": file_hash, "size": int|None}} for incremental filtering。"""
    try:
        from sqlalchemy import select

        from scripts.db import async_session
        from scripts.models import CspDocument

        async with async_session() as session:
            rows = await session.execute(
                select(
                    CspDocument.file_name,
                    CspDocument.file_hash,
                    CspDocument.quick_fp,
                    CspDocument.parse_status,
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
    """Read a cell's page-relative bbox from the table's cell_bboxes grid。"""
    try:
        row = table.cell_bboxes[row_idx]
        if col_idx < len(row):
            return row[col_idx]
    except (IndexError, TypeError):
        pass
    return [0, 0, 0, 0]


def _rediscover_taxed_price_col(rows: list, qty_col: int | None) -> int | None:
    """For a continuation page whose inherited 含税单价 column shifted to empty,
    rediscover it by arithmetic: 含税单价 × 工程量 ≈ 含税合价。

    续页继承的页级列索引可能差一(colspan 展开数不同)。合价 = 最右多数数值列
    (标准清单布局);含税单价 = 满足 单价 × qty ≈ 合价 的数值列。返回单价列索引,
    无置信匹配返回 None(调用方留 needs_review)。

    SAFE:错列不会通过逐行 单价×qty≈合价 交叉验证,故不会静默注入坏价——漏了就留 needs_review。
    """
    n = len(rows)
    if n < 2 or qty_col is None:
        return None
    maxcol = max((len(r) for r in rows), default=0)

    def num(cell) -> float | None:
        v = split_glued(cell or "")
        return v[0] if len(v) == 1 else None  # only clean single numbers

    def mostly_numeric(c: int) -> bool:
        if c >= maxcol:
            return False
        cnt = sum(1 for r in rows if c < len(r) and num(r[c]) is not None)
        return cnt >= max(2, n * 0.4)

    numeric_cols = [c for c in range(maxcol) if mostly_numeric(c) and c != qty_col]
    if len(numeric_cols) < 2:
        return None
    hejia_col = numeric_cols[-1]  # rightmost numeric = 含税合价
    best, best_frac = None, 0.0
    for c in numeric_cols:
        if c == hejia_col:
            continue
        match = tot = 0
        for r in rows:
            d = num(r[c]) if c < len(r) else None
            q = num(r[qty_col]) if qty_col < len(r) else None
            h = num(r[hejia_col]) if hejia_col < len(r) else None
            if d and q and h and q > 0:
                tot += 1
                if abs(d * q - h) <= max(h * 0.05, 0.5):
                    match += 1
        frac = match / tot if tot else 0
        if frac > best_frac:
            best, best_frac = c, frac
    return best if best_frac >= 0.5 else None


def _is_hejia_magnitude(rows: list, pt_col: int | None, untaxed_col: int | None) -> bool:
    """True if the pt column's values are 合价-magnitude — i.e. the inherited
    含税单价 column actually points at 含税合价 (large) not 含税单价 (small)。

    含税单价 ≈ 不含税单价 × 1.09 (<2×),故真单价列低于 不含税单价 列的 2×。合价列 =
    单价 × 工程量,典型 qty>2 时远超 2×。在 含税单价 粘连/缺失且算术交叉验证找不到干净
    单价时作兜底——防合价被当 unit_price 静默用。低 qty 项(合价≈单价)会漏(小错)。
    """
    if pt_col is None or untaxed_col is None:
        return False

    def col_med(c: int) -> float | None:
        vals = []
        for r in rows:
            if c < len(r):
                nums = split_glued(r[c] or "")
                if len(nums) == 1:
                    vals.append(nums[0])
        if len(vals) < 2:
            return None
        vals.sort()
        return vals[len(vals) // 2]

    pt_med = col_med(pt_col)
    ux_med = col_med(untaxed_col)
    return pt_med is not None and ux_med is not None and ux_med > 0 and pt_med > 2 * ux_med


def _find_hejia_col(rows: list, qty_col: int | None) -> int | None:
    """Rightmost mostly-numeric column = 含税合价 (清单布局:合价在末列)。用于含税单价
    缺失/异常粘连时反算 含税单价 = 合价/工程量。排除 qty。无置信数值列返回 None。"""
    n = len(rows)
    if n < 2:
        return None
    maxcol = max((len(r) for r in rows), default=0)
    for c in range(maxcol - 1, -1, -1):  # rightmost first
        if c == qty_col:
            continue
        cnt = sum(1 for r in rows if c < len(r) and len(split_glued(r[c] or "")) == 1)
        if cnt >= max(2, n * 0.4):
            return c
    return None


def _row_single_num(rows: list, row_idx: int, col: int) -> float | None:
    """Single clean number from rows[row_idx][col], else None。"""
    try:
        nums = split_glued(rows[row_idx][col] or "")
        return nums[0] if len(nums) == 1 else None
    except (IndexError, TypeError):
        return None


_PURE_NUM = re.compile(r"^\d+(?:\.\d+)?$")
_PURE_NUM_BRACKET = re.compile(r"^[【(]?\d+(?:\.\d+)?[】)]?$")  # tolerate 【20】/（19)


def _rediscover_name_col(rows: list, inherited: int | None) -> int | None:
    """Continuation pages can shift the name column: the inherited name index
    may land on 序号 (pure-numeric, e.g. col1='3') instead of 备件名称 (text,
    e.g. col2). If the inherited column is mostly pure-numeric (序号), shift
    right to the first mostly-text column (the real name). Returns the name
    column index.
    """
    if inherited is None:
        return None
    n = len(rows)
    if n < 2:
        return inherited

    def pure_num_frac(c: int) -> float:
        cnt = sum(
            1
            for r in rows
            if c < len(r) and (_PURE_NUM.match((r[c] or "").strip()) or _PURE_NUM_BRACKET.match((r[c] or "").strip()))
        )
        return cnt / n

    if pure_num_frac(inherited) < 0.4:
        return inherited  # inherited is text (备件名称) → correct
    # inherited is 序号 (numeric) → first mostly-text col to its right
    maxcol = max((len(r) for r in rows), default=0)
    for c in range(inherited + 1, maxcol):
        if pure_num_frac(c) < 0.4:
            return c
    return inherited


_DN_RE = re.compile(r"DN\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def _extract_tech_params(part_name: str) -> dict:
    """Extract structured tech params from the part name for clustering。

    DN(管径)是备件最常见的规格(管路/阀门类)——抽出它让参数向量把 DN40 与 DN50 分开
    (不同件),文本向量处理件型分离(阀 vs 管)。
    """
    params: dict = {}
    m = _DN_RE.search(part_name)
    if m:
        params["管径"] = m.group(1)
    return params


def _extract_from_tables(tables: list, doc_uri: str, keywords: list[str] | None = None) -> tuple:
    """Classify each table; from 备件/价格表 build item dicts。

    Returns (items, parse_meta)。Items 带溯源(页/bbox/行)+ validation_status。
    非备件表计入 parse_meta,绝不静默丢。

    跨页续表:布局检测把一张逻辑表切到多页;只有首页重复表头,故续页分类为 'unclassified'。
    我们把上一个备件表的列角色传播给"看起来像它续表的"无表头 unclassified 表(同列数、
    首行像数据),用 header_rows=0 抽取。
    """
    items: list[dict] = []
    meta: dict = {
        "tables_found": len(tables),
        "goods_tables": 0,
        "continuation_tables": 0,
        "rows_extracted": 0,
        "skipped": {},
    }
    active_roles: dict | None = None  # index roles propagated to continuation pages
    active_roles_x: dict | None = None  # x-bands propagated to continuation pages (drift-proof)
    active_col_count = 0
    for table in tables:
        ttype, roles, roles_x, header_rows = classify(table.rows, keywords, table.cell_bboxes)
        col_count = max((len(r) for r in table.rows), default=0)
        is_continuation = (
            ttype == "unclassified"
            and active_roles is not None
            and looks_like_continuation(
                table.rows, active_roles, active_col_count, table.cell_bboxes, active_roles_x
            )
        )
        hejia_col: int | None = None  # 含税合价 col (rightmost numeric) for 反算
        qty_col: int | None = None

        if ttype == "goods_price":
            meta["goods_tables"] += 1
            qty_col = roles.get("qty")
            hejia_col = _find_hejia_col(table.rows, qty_col)
            # 含税表头是合并格(colspan 跨 单价+合价),rapid-table 把它碎片化,故 含税单价
            # 叶标签常丢,_map_roles 抓到 含税合价。用铁律算术关系 含税单价×工程量≈含税合价
            # (数据驱动,与表头无关)覆盖 price_taxed。续页分支同法;此处修正使下游继承正确 x。
            new_pt = _rediscover_taxed_price_col(table.rows, qty_col)
            if new_pt is not None and new_pt != roles.get("price_taxed"):
                roles["price_taxed"] = new_pt
                if roles_x is not None:
                    roles_x = dict(roles_x)
                    fixed = _roles_x_from_data(
                        table.rows, table.cell_bboxes, {"price_taxed": new_pt}, header_rows
                    )
                    if fixed and "price_taxed" in fixed:
                        roles_x["price_taxed"] = fixed["price_taxed"]
            active_roles = roles
            active_roles_x = roles_x
            active_col_count = col_count
            # Goods (header) page: INDEX alignment over the (now corrected) roles.
            raw = extract_items(table.rows, roles, header_rows)
        elif is_continuation:
            meta["continuation_tables"] += 1
            cont_roles = dict(active_roles)
            # 继承的 含税单价 列索引在续页可能错:差一(→空列)或指向 含税合价(→大合价
            # 值被当 单价)。始终用算术交叉验证 含税单价×工程量≈含税合价 重推;若无干净
            # 单价且继承列是 合价量级(>2× 不含税单价),则真 含税单价 粘连/缺失 → 丢弃
            # (needs_review),不让合价冒充 unit_price。
            new_pt = _rediscover_taxed_price_col(table.rows, active_roles.get("qty"))
            if new_pt is not None:
                cont_roles["price_taxed"] = new_pt
            elif _is_hejia_magnitude(
                table.rows, active_roles.get("price_taxed"), active_roles.get("price_untaxed")
            ):
                cont_roles["price_taxed"] = None
            cont_roles_x = active_roles_x or roles_x
            qty_col = active_roles.get("qty")
            hejia_col = _find_hejia_col(table.rows, qty_col)
            raw = extract_items(table.rows, cont_roles, 0, table.cell_bboxes, cont_roles_x)
        else:
            meta["skipped"][ttype] = meta["skipped"].get(ttype, 0) + 1
            if ttype == "unclassified":
                active_roles = None  # break the propagation chain
                active_roles_x = None
            continue

        # price validation: glued/magnitude only. Outlier detection moved to
        # cluster level (_build_groups_db → compute_stats, same-part peers).
        for r in raw:
            # 乱行修复:抽出的 name 是纯数字(序号,因行首多了空格把本行右移),找真名 =
            # 该行首个文本格。逐行做因为列级启发在乱页失败(部分行移、部分不移)。
            nm = (r["name"] or "").strip()
            if _PURE_NUM.match(nm) or _PURE_NUM_BRACKET.match(nm):
                row = table.rows[r["row_idx"]] if r["row_idx"] < len(table.rows) else []
                for cell in row:
                    c = (cell or "").strip()
                    if c and not _PURE_NUM.match(c) and not _PURE_NUM_BRACKET.match(c):
                        r["name"] = c
                        break
            taxed, vstatus_t, reason_t = validate_price(r["price_taxed_raw"])
            # Only validate untaxed if a value exists. Contracts without a
            # 不含税单价 column produce price_untaxed_raw="" → validate_price
            # would return needs_review("无数字") → every item flagged even
            # though the 含税 price is correct. Skip when no untaxed value.
            if r.get("price_untaxed_raw"):
                untaxed, vstatus_u, reason_u = validate_price(r["price_untaxed_raw"])
            else:
                untaxed, vstatus_u, reason_u = None, "ok", ""
            # RECOVERY: 含税单价 missing/abnormal — cell 空 OR 不可拆粘连
            # ('9697.45556.99' = 税金+含税单价,无空格,非正常数)。用定义关系
            # 含税单价 = 含税合价 ÷ 工程量 (合价 = 最右数值列) 反算。
            if taxed is None and hejia_col is not None and qty_col is not None:
                h = _row_single_num(table.rows, r["row_idx"], hejia_col)
                q = parse_qty(r["qty_raw"])
                if h and q and q > 0:
                    taxed = round(h / q, 2)
                    vstatus_t, reason_t = "ok", "合价/工程量反算"
            # Skip price-less rows: no usable price (both taxed & untaxed empty)
            # → useless for price analysis. Covers work-content tables (no price
            # column) and OCR-miss rows. Don't store them as needs_review noise.
            if taxed is None and untaxed is None:
                continue
            vstatus = "needs_review" if "needs_review" in (vstatus_t, vstatus_u) else "ok"
            items.append(
                {
                    "part_name": r["name"],
                    "spec": r["spec"],
                    "tech_params": _extract_tech_params(r["name"]),
                    "quantity": parse_qty(r["qty_raw"]),
                    "unit": r["unit"],
                    "unit_price": taxed,  # 含税单价(统计)
                    "price_untaxed": untaxed,  # 不含税单价(审计)
                    "source_doc_uri": doc_uri,
                    "source_page": table.page_no,
                    "source_bbox": _cell_bbox(table, r["row_idx"], roles.get("name", 0) if ttype == "goods_price" else active_roles.get("name", 0)),
                    "source_table_idx": table.table_idx,
                    "source_row_idx": r["row_idx"],
                    "confidence": table.mean_confidence,
                    "validation_status": vstatus,
                    "price_reason": reason_t or reason_u,
                }
            )
        meta["rows_extracted"] += len(raw)
    return items, meta


def _build_groups_db(result, db_items: list) -> list:
    """Turn clustering output + DB items into cluster group dicts。

    Price stats 用 ONLY ok/corrected 项的 unit_price;needs_review 项仍按名聚类(与
    其备件同组)但其价格不计入 min/max/avg。is_outlier 由 ok/corrected 价格分布派生。
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
    """YYYY-MM-DD string → date object for the CspDocument.sign_date column。"""
    if not s:
        return None
    try:
        from datetime import date

        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


async def _persist_one_doc(doc: dict, items: list[dict], run_id: str | None = None) -> Optional[str]:
    """Persist a single document + its items immediately after parse (checkpoint)。

    Called from _process_one_doc so every completed doc is durable on disk even
    if the parse run crashes later. Re-parsing a doc deletes its old items first
    (fresh extraction replaces stale rows)。

    客户归一(D3):在本 session 内把 doc["customer_name"] 经 resolve_customer 归一为
    customer_id(命中复用/未命中建 pending),写到 CspDocument + 每条 CspItem。
    返回归一后的 customer_id(uuid 或 None)供上层计数。
    """
    try:
        from datetime import datetime, timezone

        from sqlalchemy import delete, select

        from scripts.db import async_session
        from scripts.models import CspDocument, CspItem

        async with async_session() as session:
            existing = (
                await session.execute(select(CspDocument).where(CspDocument.storage_uri == doc["storage_uri"]))
            ).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            # 客户归一:脏名 → customer_id(未命中建 pending,永不静默丢)
            customer_id, canonical_name, _created = await resolve_customer(session, doc.get("customer_name"))
            if existing is None:
                existing = CspDocument(
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
                    customer_id=customer_id,
                    customer_name=canonical_name or doc.get("customer_name"),
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
                existing.preview_prefix = doc.get("preview_prefix")
                existing.parsed_at = now
                if doc.get("project_name"):
                    existing.project_name = doc["project_name"]
                if doc.get("project_location"):
                    existing.project_location = doc["project_location"]
                if doc.get("contract_no"):
                    existing.contract_no = doc["contract_no"]
                if doc.get("supplier"):
                    existing.supplier = doc["supplier"]
                if doc.get("customer_name"):
                    existing.customer_id = customer_id
                    existing.customer_name = canonical_name or doc.get("customer_name")
                if doc.get("sign_date"):
                    existing.sign_date = _to_date(doc["sign_date"])
                await session.execute(delete(CspItem).where(CspItem.document_id == existing.id))
            doc_contract_no = doc.get("contract_no")
            for it in items:
                item_kwargs: dict = {
                    "document_id": existing.id,
                    "part_name": it["part_name"],
                    "spec": it.get("spec"),
                    "tech_params": it.get("tech_params"),
                    "quantity": it.get("quantity"),
                    "unit": it.get("unit"),
                    "unit_price": it.get("unit_price"),
                    "price_untaxed": it.get("price_untaxed"),
                    "customer_id": customer_id,
                    "customer_name": canonical_name or doc.get("customer_name"),
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
                session.add(CspItem(**item_kwargs))
            await session.commit()
        return str(customer_id) if customer_id else None
    except Exception as exc:
        logger.warning("Per-doc persist skipped (DB unavailable): %s", exc)
        return None


async def _persist_parse(run_record: dict, run_id: str | None = None) -> None:
    """Write the run-history record only。

    Documents and items are now persisted per-doc by _persist_one_doc() as each
    _process_one_doc() completes (checkpoint)。本函数只终结 run 记录,使 UI 显示该 run 完成/失败。
    """
    try:
        from scripts.db import async_session
        from scripts.models import CspRunHistory

        async with async_session() as session:
            session.add(
                CspRunHistory(**{k: v for k, v in run_record.items() if k in CspRunHistory.__table__.columns})
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Run record persist skipped (DB unavailable): %s", exc)


async def _persist_clusters(groups: list, run_record: dict) -> None:
    """Phase-2 persist: replace all clusters, reassign item.cluster_id/is_outlier,
    and mark confirmed/skipped docs as 'clustered'。"""
    try:
        from sqlalchemy import delete, update

        from scripts.db import async_session
        from scripts.models import CspCluster, CspDocument, CspItem, CspRunHistory

        async with async_session() as session:
            await session.execute(update(CspItem).values(cluster_id=None, is_outlier=False))
            await session.execute(delete(CspCluster))
            # 只在成功 run 上建簇 + 推文档到 'clustered'——失败 run 必须留它们在
            # confirmed/skipped 以便重试。
            if run_record.get("status") != "failed":
                for group in groups:
                    cluster = CspCluster(
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
                            update(CspItem)
                            .where(CspItem.id == m["id"])
                            .values(cluster_id=cluster.id, is_outlier=bool(m.get("is_outlier")))
                        )
                await session.execute(
                    update(CspDocument)
                    .where(CspDocument.confirm_status.in_(["confirmed", "skipped", "clustered"]))
                    .values(confirm_status="clustered")
                )
            session.add(
                CspRunHistory(**{k: v for k, v in run_record.items() if k in CspRunHistory.__table__.columns})
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Cluster persistence skipped (DB unavailable): %s", exc)


async def _process_one_doc(
    ch: dict,
    store: SparePartsStore,
    cfg,
    keywords: list[str],
    sem: asyncio.Semaphore,
    state: dict,
    run_id: str | None,
    total_docs: int,
) -> None:
    """Parse one changed contract under the concurrency semaphore。

    改共享 ``state``(documents/all_items/counters)。asyncio 单线程且这些只在 await 间改,
    故安全。单文档失败记为 failed document,绝不中断批次——这是离开顺序 for 循环的全部意义。
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
            # MinIO get is a sync blocking call — offload so concurrent docs
            # don't stall the event loop during download.
            file_bytes = await asyncio.to_thread(store.get, key)
            tables, page_texts = await parse_document(file_bytes, key, cfg.ocr_service_url)
            items, meta = _extract_from_tables(tables, doc_uri, keywords)
            customer, project_name, project_location, contract_no, supplier, sign_date = extract_project_fields(page_texts)
            # Persist preview PNGs for every page that has extracted items, so
            # the traceback UI can overlay bboxes. Derived directly from items'
            # source_page — guarantees every item's page has a preview.
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
            doc_dict = {
                "storage_uri": doc_uri,
                "file_name": key,
                "hash": ch["hash"],
                "type": os.path.splitext(key)[1].lstrip(".").lower() or "pdf",
                "quick_fp": f"{key}|{ch['size']}",
                "parse_mode": "ocr",
                # needs_review when nothing was extracted OR both project
                # fields are missing (regex couldn't anchor front-page labels
                # → human fills them via the management UI).
                "parse_status": "needs_review"
                if (not (items or meta["tables_found"]))
                or (not project_name and not project_location)
                else "parsed",
                "parse_meta": meta,
                "page_count": max((t.page_no for t in tables), default=None),
                "preview_prefix": preview_prefix,
                "project_name": project_name,
                "project_location": project_location,
                "contract_no": contract_no,
                "supplier": supplier,
                "customer_name": customer,
                "sign_date": sign_date,
            }
            # Checkpoint: persist doc + items immediately so a mid-run crash
            # doesn't lose already-parsed contracts. 客户归一在此完成。
            resolved_cust = await _persist_one_doc(doc_dict, items, run_id)
            state["docs_processed"] += 1
            state["items_extracted"] += len(items)
            if resolved_cust:
                state["customers_resolved"] += 1
            logger.info("Parsed %s: %d tables, %d items, customer=%s", key, meta["tables_found"], len(items), customer)
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


async def run_parse(trigger: str = "manual", run_id: str | None = None, force_key: str | None = None) -> int:
    """Phase 1: scan → OCR → classify → validate → customer-normalize → persist docs + items。

    无聚类(那是 run_cluster,在用户 confirm/skip 后)。返回处理的文档数。``run_id`` 启用
    实时进度轮询。``force_key``:按 key 重解析单个 MinIO 对象,绕过 hash 缓存(单文档重解析)。

    文档并发解析(asyncio.Semaphore)以喂饱 OCR 服务的 worker 池(OCR_WORKERS)——每文档
    的 OCR 调用是 async HTTP 等待,故事件循环重叠 N 个在途解析。并发默认取 OCR worker 数;
    经 CSP_PARSE_CONCURRENCY 调。单文档失败绝不中断批次。
    """
    started = time.monotonic()
    cfg = get_config()
    keywords = _load_price_keywords()

    try:
        from scripts.db import init_schema

        await init_schema()
    except Exception as exc:
        logger.warning("Schema init skipped (DB unavailable): %s", exc)

    store = SparePartsStore(cfg)
    cached = await _load_cached_meta()
    changed = scan_changed(store, cached, force_key=force_key)
    logger.info("Scan: %d changed / %d cached contracts", len(changed), len(cached))

    state: dict = {
        "docs_processed": 0,
        "items_extracted": 0,
        "failed_docs": 0,
        "customers_resolved": 0,
        "done": 0,
        "processing": set(),  # doc keys currently being parsed (for progress UI)
    }
    error: Optional[str] = None
    total_docs = len(changed)
    if run_id:
        await _update_run_progress(run_id, {"total": total_docs, "done": 0, "failed": 0, "phase": "parse"})

    concurrency = max(1, int(os.environ.get("CSP_PARSE_CONCURRENCY", "4")))
    sem = asyncio.Semaphore(concurrency)
    try:
        await asyncio.gather(
            *(_process_one_doc(ch, store, cfg, keywords, sem, state, run_id, total_docs) for ch in changed)
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
        "customers_resolved": state["customers_resolved"],
        "duration_ms": duration_ms,
        "error": error,
        "scope": {"engine": "ocr-v2", "phase": "parse", "concurrency": concurrency},
    }
    await _persist_parse(run_record, run_id)
    return state["docs_processed"]


async def run_cluster(trigger: str = "manual") -> int:
    """Phase 2: cluster items of all parsed docs (no confirm gate)。

    所有 item 按名聚类;价格统计只用 ok/corrected 项(needs_review 项聚类但价格不计入)。
    标这些文档为 'clustered' 使 UI 推进 已解析 → 已分组。返回形成的簇数。

    ④ MVP 不出 Excel(contract_price 的 excel 生成在此处省略——CspRunHistory 无 excel_path)。
    """
    started = time.monotonic()
    error: Optional[str] = None
    groups: list = []

    try:
        from sqlalchemy import select

        from scripts.db import async_session
        from scripts.models import CspDocument, CspItem

        async with async_session() as session:
            rows = (
                await session.execute(
                    select(CspItem)
                    .join(CspDocument, CspItem.document_id == CspDocument.id)
                    # 无 confirm 门槛:所有「已解析」(parsed/needs_review)文档的备件
                    # 都参与聚类。价格质量由 item 级 validation_status 把关(needs_review
                    # 归组但不计入均值),不再依赖 doc 级 confirm_status 门槛。
                    .where(CspDocument.parse_status.in_(["parsed", "needs_review"]))
                )
            ).scalars().all()
            db_items = [
                {
                    "id": r.id,
                    "part_name": r.part_name,
                    "tech_params": r.tech_params or {},
                    # Numeric(18,2) loads as decimal.Decimal; cast to float so
                    # compute_stats / outlier math (float-based) don't hit
                    # "float * Decimal" TypeErrors.
                    "unit_price": float(r.unit_price) if r.unit_price is not None else None,
                    "validation_status": r.validation_status,
                }
                for r in rows
            ]
        logger.info("Cluster phase: %d items from parsed docs", len(db_items))
        if db_items:
            samples = [(it["part_name"], it["tech_params"]) for it in db_items]
            result = cluster_items(samples)
            groups = _build_groups_db(result, db_items)
    except Exception as exc:
        error = repr(exc)
        logger.exception("Cluster phase failed")
        groups = []

    duration_ms = int((time.monotonic() - started) * 1000)
    run_record = {
        "trigger_type": trigger,
        "label": f"{'定时' if trigger == 'scheduled' else '手动'}聚类分析",
        "status": "failed" if error else "completed",
        "docs_processed": 0,
        "items_extracted": 0,
        "clusters_formed": len(groups),
        "customers_resolved": 0,
        "duration_ms": duration_ms,
        "error": error,
        "scope": {"engine": "ocr-v2", "phase": "cluster"},
    }
    await _persist_clusters(groups, run_record)
    return len(groups)


async def run_upload(directory: str) -> int:
    """Phase 0: batch upload .pdf/.docx files from a directory to MinIO + create
    pending document rows (parse_status=pending)。按内容 hash 去重(同内容已存在则跳)。
    上传后跑 `--phase parse` 抽取 items。"""
    import glob
    import hashlib

    cfg = get_config()
    store = SparePartsStore(cfg)
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
    from scripts.models import CspDocument

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
                        select(CspDocument).where(CspDocument.file_hash == digest).limit(1)
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
                        select(CspDocument).where(CspDocument.storage_uri == uri)
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        CspDocument(
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
    parser = argparse.ArgumentParser(description="Spare-parts price analysis pipeline (OCR, two-phase, customer dimension)")
    parser.add_argument("--phase", choices=["upload", "parse", "cluster"], default="parse")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--run-id", default=None, help="csp_run_history id for live progress polling")
    parser.add_argument("--force-key", default=None, help="re-parse a single MinIO object key (single-doc reparse, bypasses hash cache)")
    parser.add_argument("--dir", default=None, help="directory of .pdf/.docx to batch-upload (phase=upload)")
    args = parser.parse_args()
    if args.phase == "upload":
        if not args.dir:
            parser.error("--dir is required for --phase upload")
        n = asyncio.run(run_upload(args.dir))
        print(f"Done. Uploaded {n} file(s).")
    elif args.phase == "parse":
        n = asyncio.run(run_parse(trigger=args.trigger, run_id=args.run_id, force_key=args.force_key))
        print(f"Done. Parsed {n} document(s).")
    else:
        n = asyncio.run(run_cluster(trigger=args.trigger))
        print(f"Done. {n} cluster groups.")


if __name__ == "__main__":
    main()
