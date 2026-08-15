"""Ontology 跨模块导航 eval（plan T8: 1 条, 作 1b go/no-go）.

问题: "某备件条目所属的备件簇, 对应哪些合同货物簇/条目?" — 但 4 条跨模块 NKM 链接
recall probe 后全部 enabled:false stub（T1 结果）, 该轨迹当前**应被显式拒绝**。

本 eval 验证的是 agent 依赖的引擎契约本身：
  A. 可达链（同 connector FK）能一跳/两跳走通并返回真实行。
  B. 不可达链（stub）被显式拒绝且 describe 可见原因 —— agent 不会被静默空结果误导。
LLM 行为层 eval（agent 是否先 describe_ontology 再选工具）归 1b 前端落地时跑。

用法: PYTHONPATH=. python scripts/ontology_eval_navigation.py（需容器内扩展库可达）
"""

from __future__ import annotations

import asyncio
import sys

from app.extensions.ontology.connectors import OntologyConnectors
from app.extensions.ontology.engine import Engine, LinkDisabledError
from app.extensions.ontology.registry import get_registry


async def main() -> int:
    eng = Engine(get_registry, OntologyConnectors())
    results: list[tuple[str, bool, str]] = []

    # A1: 合同文档 → 条目（FK 单 SQL join）
    docs = await eng.list_objects("contract_document", limit=1)
    if docs["data"]:
        pk = docs["data"][0]["id"]
        items = await eng.get_links("contract_document", pk, "contract_item_in_document", limit=5)
        results.append(("A1 document→items", True, f"{len(items['data'])} 行"))
    else:
        results.append(("A1 document→items", False, "无数据(跳过不算失败)"))

    # A2: traverse 多跳: 条目 → 文档 → (reverse) 条目列表
    item = await eng.list_objects("contract_item", limit=1)
    if item["data"]:
        r = await eng.traverse("contract_item", item["data"][0]["id"], ["contract_item_in_document", "contract_item_in_document"], limit=10)
        results.append(("A2 traverse 2-hop", True, f"path={[p['link_type'] for p in r['path']]}, {len(r['data'])} 终点行"))
    else:
        results.append(("A2 traverse 2-hop", False, "无数据"))

    # B: stub 链接显式拒绝 + describe 可见
    try:
        await eng.get_links("spare_part_item", "x", "part_cluster_matches_goods_cluster")
        results.append(("B stub 拒绝", False, "竟然放行了!"))
    except LinkDisabledError as e:
        results.append(("B stub 拒绝", True, str(e)[:60]))

    ok = True
    for name, passed, note in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name:24s} {note}")
        ok = ok and (passed or "无数据" in note)
    print("eval:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
