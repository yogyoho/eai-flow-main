# EAI-CUSTOM: forked from contract-price-analysis/scripts/query.py(只读诊断 CLI)。
# 差异:part_name 字段;增 --customer / --compare 两种模式(④ 客户维度)。
"""备件价格分析只读查询 CLI(诊断用,非对话常规路径)。

MCP 工具不可用时的后备诊断入口(见 SKILL.md 步骤4)。直接查 csp_ 表,只读。
模式:
  --part NAME        按备件名模糊查含税单价统计(对应 query_part_price)
  --compare NAME     同一备件跨客户比价(对应 compare_part_price_by_customer)
  --customer NAME    某客户的备件 + 合同明细(对应 customer_parts_contracts)
  --outliers         异常高价项
  --needs-review     待核验项
  --cluster ID       某聚类组明细
  --summary          数据总览
"""
import argparse
import asyncio
import logging

from sqlalchemy import select

from scripts.db import async_session
from scripts.models import CspCluster, CspCustomer, CspItem
from scripts.stats import compute_stats

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

_VALID = ("ok", "corrected")  # 统计只用已校验项(同 MCP/聚类规则)


def _priced(items):
    return [float(i.unit_price) for i in items if i.unit_price is not None and i.validation_status in _VALID]


async def query_part(name: str):
    async with async_session() as s:
        rows = (await s.execute(select(CspItem).where(CspItem.part_name.ilike(f"%{name}%")))).scalars().all()
    if not rows:
        log.info("未找到名称含「%s」的备件", name)
        return
    by_name: dict[str, list] = {}
    for it in rows:
        by_name.setdefault(it.part_name, []).append(it)
    log.info("匹配 %d 条 / %d 种备件", len(rows), len(by_name))
    for gname, items in by_name.items():
        st = compute_stats(_priced(items))
        custs = sorted({(i.customer_name or "(未关联)") for i in items})
        log.info("  · %s | n=%d 已校验=%d | %s | 客户: %s",
                 gname, len(items), st["count"], st, custs)


async def query_compare(name: str):
    """④ 特色:同备件跨客户比价。各客户独立统计 + 偏离整体中位标记。"""
    async with async_session() as s:
        rows = (await s.execute(select(CspItem).where(CspItem.part_name.ilike(f"%{name}%")))).scalars().all()
    if not rows:
        log.info("未找到名称含「%s」的备件,无法跨客户比价", name)
        return
    all_median = compute_stats(_priced(rows)).get("median") or 0
    by_cust: dict[tuple, list] = {}
    for it in rows:
        key = (it.customer_name or "(未关联客户)",)
        by_cust.setdefault(key, []).append(it)
    log.info("匹配 %d 条 / %d 个客户 | 整体中位 %.2f", len(rows), len(by_cust), all_median)
    rows_out = []
    for (cname,), items in by_cust.items():
        st = compute_stats(_priced(items))
        mean = st.get("mean") or 0
        dev = "持平"
        if all_median > 0 and mean > 0:
            r = mean / all_median
            dev = "高于均值" if r >= 1.3 else ("低于均值" if r <= 0.77 else "持平")
        rows_out.append((cname, st.get("count", 0), mean, dev))
    for cname, cnt, mean, dev in sorted(rows_out, key=lambda x: -x[2]):
        log.info("  · %-20s n校验=%-3d 均价=%-10.2f %s", cname, cnt, mean, dev)


async def query_customer(name: str):
    async with async_session() as s:
        custs = (await s.execute(select(CspCustomer))).scalars().all()
        target = None
        for c in custs:
            if c.canonical_name == name or name in (c.aliases or []):
                target = c
                break
        if target is None:
            log.info("未找到客户「%s」(可能尚未认领归一)", name)
            return
        rows = (await s.execute(select(CspItem).where(CspItem.customer_id == target.id))).scalars().all()
    log.info("客户「%s」(id=%s, status=%s) | 备件分项 %d 条",
             target.canonical_name, target.id, target.status, len(rows))
    by_part: dict[str, list] = {}
    for it in rows:
        by_part.setdefault(it.part_name, []).append(it)
    for pname, items in sorted(by_part.items(), key=lambda kv: -(compute_stats(_priced(kv[1])).get("mean") or 0)):
        st = compute_stats(_priced(items))
        log.info("  · %-24s n=%d %s", pname, len(items), st)
    log.info("合同: %s", sorted({(i.source_contract_no or "(未关联)") for i in rows}))


async def query_outliers():
    async with async_session() as s:
        rows = (await s.execute(select(CspItem).where(CspItem.is_outlier.is_(True)).order_by(CspItem.unit_price.desc()))).scalars().all()
    log.info("异常高价 %d 条", len(rows))
    for r in rows[:50]:
        log.info("  · %-20s 单价=%-10.2f 客户=%s 合同=%s", r.part_name,
                 float(r.unit_price) if r.unit_price is not None else 0, r.customer_name, r.source_contract_no)


async def query_needs_review():
    async with async_session() as s:
        rows = (await s.execute(select(CspItem).where(CspItem.validation_status == "needs_review"))).scalars().all()
    log.info("待核验 %d 条", len(rows))
    for r in rows[:50]:
        log.info("  · %-20s 原值=%s 合同=%s", r.part_name, r.unit_price, r.source_contract_no)


async def query_cluster(cluster_id: str):
    async with async_session() as s:
        rows = (await s.execute(select(CspItem).where(CspItem.cluster_id == cluster_id))).scalars().all()
    log.info("聚类 %s | %d 条", cluster_id, len(rows))
    for r in rows[:50]:
        log.info("  · %-20s 单价=%s 客户=%s", r.part_name, r.unit_price, r.customer_name)


async def query_summary():
    async with async_session() as s:
        from sqlalchemy import func

        docs = await s.scalar(select(func.count()).select_from(select(CspItem.document_id).distinct().subquery())) or 0
        items = await s.scalar(select(func.count()).select_from(CspItem)) or 0
        clu = await s.scalar(select(func.count()).select_from(CspCluster)) or 0
        cust = await s.scalar(select(func.count()).select_from(CspCustomer)) or 0
        nr = await s.scalar(select(func.count()).select_from(
            select(CspItem).where(CspItem.validation_status == "needs_review").subquery())) or 0
        lo = await s.scalar(select(func.min(CspItem.unit_price)))
        hi = await s.scalar(select(func.max(CspItem.unit_price)))
    log.info("备件价格分析总览: 合同=%d 备件分项=%d 聚类=%d 客户=%d 待核验=%d 价格区间=[%s,%s]",
             docs, items, clu, cust, nr, lo, hi)


async def main():
    p = argparse.ArgumentParser(description="备件价格分析只读查询(诊断 CLI)")
    p.add_argument("--part", help="按备件名模糊查含税单价统计")
    p.add_argument("--compare", help="同备件跨客户比价(④ 特色)")
    p.add_argument("--customer", help="某客户的备件+合同明细")
    p.add_argument("--outliers", action="store_true", help="异常高价项")
    p.add_argument("--needs-review", action="store_true", help="待核验项")
    p.add_argument("--cluster", help="聚类组明细")
    p.add_argument("--summary", action="store_true", help="数据总览")
    a = p.parse_args()
    if a.part:
        await query_part(a.part)
    elif a.compare:
        await query_compare(a.compare)
    elif a.customer:
        await query_customer(a.customer)
    elif a.outliers:
        await query_outliers()
    elif a.needs_review:
        await query_needs_review()
    elif a.cluster:
        await query_cluster(a.cluster)
    else:
        await query_summary()


if __name__ == "__main__":
    asyncio.run(main())
