"""Read-only query CLI over the cpa_ tables (agent-facing).

The pipeline (cli.py) WRITES cpa_documents / cpa_items / cpa_clusters. This
module is the READ path: it lets the agent answer user questions like
"多孔砖墙的单价是多少？均价/区间？" / "哪些货物价格异常？" / "供应商X的电缆价格对比"
directly from already-processed data — WITHOUT re-running the OCR pipeline.

Usage (inside the gateway container, or anywhere with DB access):
  python -m scripts.query --goods 多孔砖墙
  python -m scripts.query --goods 电缆 --summary
  python -m scripts.query --outliers
  python -m scripts.query --needs-review
  python -m scripts.query --cluster <cluster_uuid>

All queries are read-only SELECTs. Output is human-readable text the agent can
relay to the user verbatim. DB-unavailable → clear error message, exit 1.
"""

import argparse
import asyncio
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select

from scripts.db import async_session
from scripts.models import CpaCluster, CpaDocument, CpaItem
from scripts.stats import compute_stats

logger = logging.getLogger(__name__)


def _fmt_price(v) -> str:
    return f"{float(v):,.2f}" if v is not None else "—"


async def query_goods(name: str) -> None:
    """Fuzzy-match items by goods_name (ilike), print price stats + breakdown."""
    async with async_session() as s:
        rows = (
            await s.execute(
                select(CpaItem).where(CpaItem.goods_name.ilike(f"%{name}%")).order_by(CpaItem.created_at)
            )
        ).scalars().all()

    if not rows:
        print(f"未找到名称含「{name}」的分项货物。")
        return

    # group by exact goods_name for per-name stats
    by_name: dict[str, list[CpaItem]] = {}
    for it in rows:
        by_name.setdefault(it.goods_name, []).append(it)

    print(f"=== 查询「{name}」: 命中 {len(rows)} 条 / {len(by_name)} 个名称 ===\n")
    for gname, items in by_name.items():
        # price stats use only ok/corrected items (needs_review excluded, same rule as cluster stats)
        priced = [
            float(i.unit_price)
            for i in items
            if i.unit_price is not None and i.validation_status in ("ok", "corrected")
        ]
        stats = compute_stats(priced) if priced else None
        nr = sum(1 for i in items if i.validation_status == "needs_review")
        outliers = [i for i in items if i.is_outlier]
        contracts = sorted({(i.source_contract_no or "—") for i in items})

        print(f"■ {gname}  ({len(items)} 条)")
        if stats:
            print(f"  含税单价(仅已校验 {stats.get('count', 0)} 条): "
                  f"均值 {_fmt_price(stats.get('mean'))} · "
                  f"中位 {_fmt_price(stats.get('median'))} · "
                  f"区间 [{_fmt_price(stats.get('min'))}, {_fmt_price(stats.get('max'))}]")
        else:
            print("  含税单价: 无已校验数据(全部待核验)")
        print(f"  校验状态: 已校验 {sum(1 for i in items if i.validation_status == 'ok')} · "
              f"待核验 {nr} · 已修正 {sum(1 for i in items if i.validation_status == 'corrected')}")
        if outliers:
            print(f"  ⚠ 异常高价 {len(outliers)} 条: " + ", ".join(_fmt_price(i.unit_price) for i in outliers[:5]))
        print(f"  来源合同: {', '.join(contracts)}")
        # sample items
        for i in items[:3]:
            untaxed = f" 不含税{_fmt_price(i.price_untaxed)}" if i.price_untaxed else ""
            qty = f" · 工程量 {_fmt_price(i.quantity)}{i.unit or ''}" if i.quantity else ""
            print(f"    - {_fmt_price(i.unit_price)} ({i.validation_status}{untaxed}{qty})")
        if len(items) > 3:
            print(f"    … 余 {len(items) - 3} 条")
        print()


async def query_outliers() -> None:
    async with async_session() as s:
        rows = (
            await s.execute(
                select(CpaItem).where(CpaItem.is_outlier.is_(True)).order_by(CpaItem.unit_price.desc())
            )
        ).scalars().all()
    print(f"=== 异常高价分项: {len(rows)} 条 ===\n")
    for i in rows[:30]:
        print(f"  {i.goods_name}  {_fmt_price(i.unit_price)}  ({i.source_contract_no or '—'})")
    if len(rows) > 30:
        print(f"  … 余 {len(rows) - 30} 条")


async def query_needs_review() -> None:
    async with async_session() as s:
        rows = (
            await s.execute(
                select(CpaItem).where(CpaItem.validation_status == "needs_review")
            )
        ).scalars().all()
    print(f"=== 待核验分项: {len(rows)} 条 ===\n")
    # group by reason-ish: just list with price reason fields if any
    for i in rows[:30]:
        print(f"  {i.goods_name}  单价={_fmt_price(i.unit_price)}  状态={i.validation_status}  来源页={i.source_page}")
    if len(rows) > 30:
        print(f"  … 余 {len(rows) - 30} 条")


async def query_cluster(cluster_id: UUID) -> None:
    async with async_session() as s:
        c = await s.get(CpaCluster, cluster_id)
        if c is None:
            print(f"聚类 {cluster_id} 不存在。")
            return
        items = (
            await s.execute(
                select(CpaItem).where(CpaItem.cluster_id == cluster_id).order_by(CpaItem.unit_price)
            )
        ).scalars().all()
    print(f"=== 聚类: {c.representative_name} ===")
    print(f"类别 {c.category} · {c.item_count} 项 · 状态 {c.status} · v{c.version}")
    if c.stats:
        st = c.stats
        print(f"均价 {_fmt_price(st.get('mean'))} · 中位 {_fmt_price(st.get('median'))} · "
              f"区间 [{_fmt_price(st.get('min'))}, {_fmt_price(st.get('max'))}]")
    print()
    for i in items[:20]:
        flag = " ⚠" if i.is_outlier else ""
        print(f"  {i.goods_name}  {_fmt_price(i.unit_price)}{flag}")
    if len(items) > 20:
        print(f"  … 余 {len(items) - 20} 条")


async def query_summary() -> None:
    async with async_session() as s:
        docs = await s.scalar(select(func.count()).select_from(CpaDocument)) or 0
        items = await s.scalar(select(func.count()).select_from(CpaItem)) or 0
        clusters = await s.scalar(select(func.count()).select_from(CpaCluster)) or 0
        pending = await s.scalar(
            select(func.count()).select_from(
                select(CpaCluster).where(CpaCluster.status == "pending").subquery()
            )
        ) or 0
        nr = await s.scalar(
            select(func.count()).select_from(
                select(CpaItem).where(CpaItem.validation_status == "needs_review").subquery()
            )
        ) or 0
        lo = await s.scalar(select(func.min(CpaItem.unit_price)))
        hi = await s.scalar(select(func.max(CpaItem.unit_price)))
        avg = await s.scalar(select(func.avg(CpaItem.unit_price)))
    print("=== 合同价格分析 · 数据总览 ===")
    print(f"合同 {docs} · 分项 {items} · 聚类 {clusters}(待审 {pending}) · 待核验 {nr}")
    print(f"含税单价全量区间: [{_fmt_price(lo)}, {_fmt_price(hi)}] · 均值 {_fmt_price(avg)}")
    print("\n提示: 用 --goods <名称> 查指定货物的价格统计；--outliers 看异常高价；--needs-review 看待核验。")


async def main_async(args) -> None:
    try:
        if args.goods:
            await query_goods(args.goods)
            if args.summary:
                await query_summary()
        elif args.cluster:
            await query_cluster(args.cluster)
        elif args.outliers:
            await query_outliers()
        elif args.needs_review:
            await query_needs_review()
        else:
            await query_summary()
    except Exception as exc:  # noqa: BLE001
        logger.error("query failed: %s", exc, exc_info=True)
        print(f"查询失败(DB 不可达或查询出错): {exc}")
        raise SystemExit(1)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Read-only query over cpa_ tables (agent-facing)")
    p.add_argument("--goods", default=None, help="按货物名称模糊查(含税单价统计)")
    p.add_argument("--cluster", default=None, help="按聚类 UUID 查")
    p.add_argument("--outliers", action="store_true", help="列出异常高价分项")
    p.add_argument("--needs-review", action="store_true", help="列出待核验分项")
    p.add_argument("--summary", action="store_true", help="附加数据总览(与 --goods 同用)")
    args = p.parse_args()
    cluster_uuid: Optional[UUID] = None
    if args.cluster:
        try:
            cluster_uuid = UUID(args.cluster)
        except ValueError:
            print(f"无效的聚类 UUID: {args.cluster}")
            raise SystemExit(1) from None
    asyncio.run(main_async(argparse.Namespace(**{**vars(args), "cluster": cluster_uuid})))


if __name__ == "__main__":
    main()
