"""标准序列化导出（kernel P1）——国标 GB/T 48000.3 §5.3 原生满足.

Turtle（推荐交付物）/ JSON-LD 1.1（互操作）。每日快照 = 备份 + 交付物（见 spec §4）。
"""

from __future__ import annotations

import json

from rdflib import Graph
from rdflib.compare import isomorphic


def to_turtle(graph: Graph) -> str:
    return graph.serialize(format="turtle")


def to_jsonld(graph: Graph) -> dict:
    """JSON-LD 文档（dict）；@graph 承载节点。"""
    return json.loads(graph.serialize(format="json-ld"))


def parse_turtle(ttl: str) -> Graph:
    graph = Graph()
    graph.parse(data=ttl, format="turtle")
    return graph


def graphs_isomorphic(left: Graph, right: Graph) -> bool:
    return isomorphic(left, right)
