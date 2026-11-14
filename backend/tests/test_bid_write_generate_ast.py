"""批三十四:products → 正文 AST 装配(真实生成物进入工作台)。

覆盖:四切片章节形状、金额/响应/附件行身份、确定性、与 executor 覆盖层同尺
(装配后的 AST 再跑 43 条断言应保持 green 闭环)。
"""

import json

from bid_write_generate_fixtures import closure_inputs

from app.extensions.bid_write.executor.editor import prepare_editor_ctx
from app.extensions.bid_write.executor.gate import gate_verdict
from app.extensions.bid_write.executor.runner import run_assertions
from app.extensions.bid_write.generate import build_ctx
from app.extensions.bid_write.generate.ast import products_to_ast


def _ctx(**overrides):
    fields, rows, material, knobs = closure_inputs(**overrides)
    return build_ctx(fields, rows, material, **knobs)


def _sections(ast):
    return [node for node in ast["content"] if node.get("type") == "section"]


def _table(ast, table_type):
    for section in _sections(ast):
        for node in section.get("content") or []:
            if node.get("type") == "table" and (node.get("attrs") or {}).get("table_type") == table_type:
                return node
    return None


def test_products_to_ast_has_four_real_sections():
    ast = products_to_ast(_ctx()["products"])
    titles = [(s.get("attrs") or {}).get("title") for s in _sections(ast)]
    assert titles == ["一、投标函", "二、开标一览表", "三、商务响应表", "四、附件索引"]
    assert _table(ast, "price") is not None
    assert _table(ast, "response") is not None
    assert _table(ast, "list") is not None


def test_price_and_response_rows_keep_identity():
    ctx = _ctx()
    ast = products_to_ast(ctx["products"])
    price_rows = [r for r in _table(ast, "price")["content"] if (r.get("attrs") or {}).get("row_id") != "PRICE-TOTAL"]
    assert [r["attrs"]["row_id"] for r in price_rows] == ["1.1", "1.2"]
    response_rows = _table(ast, "response")["content"]
    expected = [r["clause_id"] for r in ctx["products"]["response_table"]["rows"]]
    assert [r["attrs"]["row_id"] for r in response_rows] == expected


def test_assembled_ast_roundtrips_through_executor_overlay():
    ctx = _ctx()
    ast = products_to_ast(ctx["products"])
    overlaid, _meta = prepare_editor_ctx(ctx, ast)
    report = run_assertions(overlaid)
    fails = {r.assertion_id: r.status for r in report.results if r.status != "PASS"}
    assert fails == {}, fails
    assert gate_verdict(report)["blocked"] is False


def test_assembly_is_deterministic():
    products = _ctx()["products"]
    a = json.dumps(products_to_ast(products), sort_keys=True, ensure_ascii=False)
    b = json.dumps(products_to_ast(products), sort_keys=True, ensure_ascii=False)
    assert a == b
