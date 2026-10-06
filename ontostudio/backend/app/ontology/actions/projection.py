"""提交后投影（EAI-CUSTOM, 2026-09-26 人审闭环切片 T2）——动作行 → 断言图.

REST（``routers._project_incrementally``）与 MCP（``executor.run_action_for_mcp``）
**双通道共用**本函数——此前两条通道各有一条假投影（REST 只 ``refresh()`` 从不读行、
MCP 是同一语义的 lambda），切片后统一到这里。

语义（eng-review T1A/T2A/T3A 决议，设计
``docs/designs/2026-09-26-ontostudio-review-loop-closure.md``）：

- **传入行，不复读 DB**（T1A）：executor 在 ``FOR UPDATE`` 锁定行、``UPDATE ... RETURNING``
  提交后，把「锁定行 ∪ RETURNING after」直接传进来。DB 层 async-only 而 ``project``
  被 executor 的同步契约钉死（docstring + 测试），投影内读库必撞同步/异步墙——
  数据已在内存里，没有理由再读一次。
- **断言图 = DB 全行忠实投影**（T2A）：确认 → ``force_status`` 翻转为 active；
  驳回 → 翻转为 rejected（实体/关系/mention 全保留，不做移除）。单行装载复用
  ``load_doc_graph_rows``（词表解析 / etype→类映射 / 幂等 upsert 全部现成），零新逻辑。
- **装载后 ``refresh()``**：闭包与规则重跑（store-global，秒级代价已被 eng-review OQ1
  接受；局部重跑未裁决前**不假装增量**——函数名如实叫 ``project_row``）。

异常**向外抛**（executor 记入 ``errors`` → degraded 响应；投影失败不回滚业务状态），
此处绝不吞——吞掉等于让 ``projected`` 恒 True。degraded 是自愈的：全量装载传
``force_status=True``（装载=对账），重跑 ``POST /formal/load`` 即治愈。

EAI-CUSTOM(2026-09-29 批量确认摊销): :func:`project_rows` 是同语义的**批量**版——
N 行合并行**一次**装载（单次 ``load_doc_graph_rows``）+ **一次** ``refresh()``，
供 ``POST /actions/invoke_batch`` 使用；代价从 O(N) 次 refresh 摊销为 O(1)
（单条确认 ≈ 全量 refresh 实测约 34s/条，批量 50 条的投影代价与其相当）。
行级跳过（缺 etype / 域词表未声明该 etype）不中止全批，以"未入返回集合"暴露，
由 executor 逐行记 degraded——与单条路径"投影失败不回滚业务状态"同一取向。
"""

from __future__ import annotations

import uuid
from typing import Any


def project_row(action_id: str, pk: uuid.UUID, row: dict[str, Any] | None) -> None:
    """把已提交的动作行投影进断言图（纯图侧、同步、可重入）.

    ``row`` 为 ``None`` 时跳过行装载、只 ``refresh()``（防御路径：正常 review 动作
    必有锁定行；保留 None 分支让既有「同步性/不吞异常」钉约测试可以无 DB 调用）。
    """
    from app.ontology.kernel.loader import load_doc_graph_rows
    from app.ontology.kernel.service import get_kernel
    from app.ontology.registry import get_registry

    kernel = get_kernel()
    if row is not None:
        if not row.get("etype"):
            # 今日全部动作 targeting dg_entities（行必有 etype）；未来 action 扩到
            # dg_relations 时这里会以 degraded 暴露，而不是静默装错形状。
            raise RuntimeError(f"动作行缺少 etype，无法投影（目标表非 dg_entities?）: action={action_id} pk={pk}")
        stats = load_doc_graph_rows(
            kernel.store,
            get_registry(),
            entity_rows=[dict(row)],
            relation_rows=[],
            mention_rows=[],
            domain=str(row.get("domain") or "core_graph"),
        )
        if stats.entities == 0:
            raise RuntimeError(f"动作行未投影（etype 未在 registry 声明或域词表缺失）: pk={pk} etype={row.get('etype')!r} domain={row.get('domain')!r}")
    kernel.refresh()


def project_rows(action_id: str, rows: dict[uuid.UUID, dict[str, Any]]) -> set[uuid.UUID]:
    """批量投影：全批已提交行一次装载 + 一次 ``refresh()``（批量确认摊销, EAI-CUSTOM 2026-09-29）.

    与 :func:`project_row` 的逐条语义对齐（T2A 断言图 = DB 全行忠实投影 + 装载后重推理），
    差异只在摊销：``rows``（pk → executor 的合并行）在**单次** ``load_doc_graph_rows`` 里
    全量装载，随后全批**仅一次** ``refresh()``——批内 N 行共享同一次闭包与规则重算。

    返回**成功入图**的 pk 集合；调用方（executor）对不在集合内的行逐行记 degraded：

    - 行缺 ``etype``：不进装载（与单条路径的 RuntimeError 同判，批量下行级隔离不中止全批）；
    - 装载被跳过（etype 未在域词表声明 / 域词表缺失）：``LoaderStats.skipped_entities``
      里点名，按"未投影"处理；
    - ``refresh()`` 抛异常：**向外抛**（不吞）——executor 接住后全批记 degraded，
      业务状态不回滚；重跑 ``POST /formal/load`` 自愈。

    ``rows`` 为空（全批行级写都失败）时直接返回空集、不触发装载与 refresh——
    没有已提交行时做全局重推理是纯浪费，且会让"全批失败"看起来像"投影失败"。
    """
    from app.ontology.kernel.loader import load_doc_graph_rows
    from app.ontology.kernel.service import get_kernel
    from app.ontology.registry import get_registry

    if not rows:
        return set()
    kernel = get_kernel()
    loadable = [dict(row) for row in rows.values() if row.get("etype")]
    if not loadable:
        return set()
    stats = load_doc_graph_rows(
        kernel.store,
        get_registry(),
        entity_rows=loadable,
        relation_rows=[],
        mention_rows=[],
        domain="core_graph",
    )
    if stats.entities == 0:
        # 与单条路径同语义（project_row 的 stats.entities == 0 → RuntimeError）：一行都没装进去
        # 说明声明/词表侧坏了，如实炸出（executor 全批记 degraded），不假装投影成功。
        raise RuntimeError(f"批量投影零行装载（etype 未在 registry 声明或域词表缺失）: action={action_id} rows={len(loadable)} skipped={[str(s) for s in stats.skipped_entities[:5]]}…")
    kernel.refresh()
    skipped = {str(s) for s in stats.skipped_entities}
    return {pk for pk, row in rows.items() if row.get("etype") and str(pk) not in skipped}
