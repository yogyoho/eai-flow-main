"""pyoxigraph 嵌入式三元组库封装（kernel P1）——图真源.

- 持久化目录模式（RocksDB）或内存模式（测试）。
- named graph 约定：graph:schema（本体 schema）/ graph:asserted（业务断言）/
  graph:alignment（sameAs 候选覆盖层）/ graph:entailment（owlrl 物化, P3）/
  graph:derived:<rule>（CONSTRUCT 派生, P3）。
- P1 仅装载/查询/导出；写路径语义（P2）在此之上实现。
"""

from __future__ import annotations

from pathlib import Path

import pyoxigraph as ox

SCHEMA_GRAPH = "graph:schema"
ASSERTED_GRAPH = "graph:asserted"
ALIGNMENT_GRAPH = "graph:alignment"
ENTAILMENT_GRAPH = "graph:entailment"


def named_graph(name: str) -> ox.NamedNode:
    return ox.NamedNode(name)


def _term_to_python(term: ox.Term) -> str | None:
    """查询结果项 → python 标量（IRI/字面值；空白节点给 _:id）。"""
    if term is None:
        return None
    if isinstance(term, ox.NamedNode):
        return term.value
    if isinstance(term, ox.BlankNode):
        return f"_:{term.value}"
    if isinstance(term, ox.Literal):
        return term.value
    return None  # pragma: no cover - quoted triple 等 P3+ 再扩


class OxStore:
    """pyoxigraph Store 薄封装。path=None → 内存模式（测试）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._store = ox.Store(str(path) if path is not None else None)

    def close(self) -> None:
        # pyoxigraph 0.5 Store 无显式 close：每事务同步落盘，引用释放即回收
        return None

    def __enter__(self) -> OxStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- 装载 / 导出 ----

    def load_turtle(self, ttl: str | bytes, graph_name: str = SCHEMA_GRAPH) -> None:
        self._store.load(
            input=ttl,
            format=ox.RdfFormat.TURTLE,
            to_graph=named_graph(graph_name),
        )

    def clear_graph(self, graph_name: str) -> None:
        self._store.clear_graph(named_graph(graph_name))

    def dump_turtle(self, graph_name: str = SCHEMA_GRAPH) -> str:
        # pyoxigraph 0.5：output 省略时直接返回 bytes
        data = self._store.dump(format=ox.RdfFormat.TURTLE, from_graph=named_graph(graph_name))
        return data.decode("utf-8")

    # ---- 查询 ----

    def query(self, sparql: str) -> list[dict[str, str | None]]:
        """SELECT 查询 → 行字典列表（变量名 → 字符串化值）。仅支持 SELECT。"""
        results: list[dict[str, str | None]] = []
        solutions = self._store.query(sparql)
        names = [str(var).lstrip("?") for var in solutions.variables]  # 0.5 变量名带 ? 前缀
        for solution in solutions:
            results.append({name: _term_to_python(solution[name]) for name in names})
        return results

    def count_quads(self, graph_name: str) -> int:
        rows = self.query(f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph_name}> {{ ?s ?p ?o }} }}")
        return int(rows[0]["n"] or 0) if rows else 0
