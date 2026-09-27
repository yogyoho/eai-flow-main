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
            domain=str(row.get("domain") or "doc_graph"),
        )
        if stats.entities == 0:
            raise RuntimeError(f"动作行未投影（etype 未在 registry 声明或域词表缺失）: pk={pk} etype={row.get('etype')!r} domain={row.get('domain')!r}")
    kernel.refresh()
