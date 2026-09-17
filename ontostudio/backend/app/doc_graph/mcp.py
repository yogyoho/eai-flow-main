"""doc_graph 写+计算 MCP Server——5 工具，ontology 只读 server 的构建侧补充.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-11-ontology-doc-graph-design.md §3.1 补全。
- ingest_extraction: LLM 抽取 JSON → fail-closed 校验 → 入库（幂等）
- list_pending_review: 低置信待复核实体
- merge_entities / unmerge: 消解合并与撤销（dg_merges 留痕）
- evaluate_rules: 真库事实 + 注册规则 → 前向链推理（现算现返, 零落库;
  reasoning/ 子包, 见 docs/superpowers/specs/2026-09-13-ontology-reasoning-rules-design.md）
查询走只读 ontology server 的 graph_* 对象——写路径与规则计算在本 server。
EAI-CUSTOM: 审核 SQL 已抽至 service.py（REST/MCP 共用，见 2026-09-13-ontology-semantic-map-v2-design.md §4）——本文件只保留 MCP 参数解析与 _ok/_err 包装。
"""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

_TOOLS_SPEC = [
    (
        "ingest_extraction",
        "把抽取出的投标实体/关系/证据入库（幂等：同名实体归并）。payload 须严格符合投标域抽取 schema（extra 字段会被拒绝）。",
        {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": ["bid"]},
                "extracted_by": {"type": "string"},
                "thread_id": {"type": "string"},
                "entities": {"type": "array", "minItems": 1, "items": {"type": "object"}},
                "relations": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["domain", "entities"],
        },
    ),
    (
        "list_pending_review",
        "列出低置信度待复核实体（status=pending_review），可请用户确认后用 merge_entities 合并。",
        {"type": "object", "properties": {"etype": {"type": "string", "description": "实体类型: project/bidder/goods/qualification"}, "limit": {"type": "integer"}}, "required": []},
    ),
    (
        "merge_entities",
        "把候选实体合并进规范实体（candidate 置 merged + dg_merges 留痕，可撤销）。",
        {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "canonical_id": {"type": "string"},
                "method": {"type": "string", "description": "合并依据: similarity | manual"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["candidate_id", "canonical_id"],
        },
    ),
    (
        "unmerge",
        "撤销一次合并（删留痕行，candidate 置回 active）。",
        {"type": "object", "properties": {"merge_id": {"type": "string"}}, "required": ["merge_id"]},
    ),
    (
        "evaluate_rules",
        "在真库图数据上跑注册规则的前向链推理（现算现返，零落库）。domain 选择事实域（eia=环评样例）。"
        "返回派生事实、每条规则的触发轨迹（哪些源事实触发了哪条规则）与统计；"
        "max_derived_reached/max_rule_fires_reached/max_iterations_reached=true 表示到达推理工作预算（不必然截断）。",
        {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "事实域: eia=环评样例（bid 暂无注册规则时零注册）"},
            },
            "required": ["domain"],
        },
    ),
]

TOOLS = [Tool(name=n, description=d, inputSchema=s) for n, d, s in _TOOLS_SPEC]


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _err(e: Exception) -> list[TextContent]:
    return _ok({"success": False, "error": f"{type(e).__name__}: {e}"})


async def _ingest_extraction(a: dict) -> list[TextContent]:
    from pydantic import ValidationError

    from app.doc_graph.ingest import REVIEW_CONFIDENCE, ingest_extraction
    from app.doc_graph.schemas import BidExtraction

    try:
        payload = BidExtraction.model_validate(a)
    except ValidationError as e:
        return _ok({"success": False, "error": f"schema 校验失败(fail-closed): {e.error_count()} 处", "detail": str(e)[:2000]})
    counts = await ingest_extraction(payload)
    return _ok({"success": True, **counts, "hint": f"confidence<{REVIEW_CONFIDENCE} 的实体已置 pending_review, 用 list_pending_review 查看"})


async def _list_pending_review(a: dict) -> list[TextContent]:
    from app.doc_graph.service import list_pending_review

    res = await list_pending_review(etype=a.get("etype"), limit=int(a.get("limit", 50)))
    return _ok({"success": True, **res})


async def _merge_entities(a: dict) -> list[TextContent]:
    from app.doc_graph.service import merge_entities

    candidate_id = a["candidate_id"]
    canonical_id = a["canonical_id"]
    try:
        res = await merge_entities(candidate_id, canonical_id, method=a.get("method", "manual"), confidence=a.get("confidence", 1.0))
    except KeyError as e:  # 资源不存在 → 结构化消息（现行为; IntegrityError 自合并 CHECK 不接, 上抛走 _err）
        return _ok({"success": False, "message": e.args[0]})
    return _ok({"success": True, **res})


async def _unmerge(a: dict) -> list[TextContent]:
    from app.doc_graph.service import unmerge

    merge_id = a["merge_id"]
    try:
        res = await unmerge(merge_id)
    except KeyError as e:  # 资源不存在 → 结构化消息（现行为）
        return _ok({"success": False, "message": e.args[0]})
    return _ok({"success": True, **res})


async def _evaluate_rules(a: dict) -> list[TextContent]:
    from app.doc_graph.reasoning.evaluate import evaluate_rules
    from app.doc_graph.reasoning.facade import RuleSyntaxError

    try:
        # 评审加固: MCP 面不透传 rules_dir——参数只在 Python API 层（测试/内部）可用。
        # 暴露给 agent = 规则注入通道（对抗文档→构造规则→误导性派生事实以"规则结论"名义呈现）
        # + 路径存在性/错误信息 oracle; schema 已删该属性, handler 也不再转发（双层封死）。
        res = await evaluate_rules(a["domain"])
    except RuleSyntaxError as e:  # 窄捕获优先: 规则注册校验失败 → 明确文案（不误吞无关 ValueError）
        return _ok({"success": False, "error": f"规则语法错误: {e}"})
    except ValueError as e:  # 其余值错误（防御面）→ 走通用 _err 结构化
        return _err(e)
    return _ok({"success": True, **res})


_HANDLERS = {
    "ingest_extraction": _ingest_extraction,
    "list_pending_review": _list_pending_review,
    "merge_entities": _merge_entities,
    "unmerge": _unmerge,
    "evaluate_rules": _evaluate_rules,
}

server = Server("doc-graph")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = _HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return await handler(arguments or {})
    except Exception as e:  # 结构化错误返回 agent, 不崩 server
        return _err(e)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
