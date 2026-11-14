"""批廿六 M0:document_ast_schema.yaml 单一 schema 自检(EAI-CUSTOM)。

事实层契约:PM schema 与 TS 类型由本 yaml 经 editor_schema_gen.py 同源生成,
禁止手写两份(《Word 编辑器技术方案》§十四 风险三条之一)。
本文件钉:结构完整性 + codegen 产物漂移。
"""

from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
YAML_PATH = BACKEND / "app" / "extensions" / "bid_write" / "document_ast_schema.yaml"
GEN_PATH = (
    BACKEND.parents[0]
    / "frontend"
    / "src"
    / "extensions"
    / "bid-write"
    / "editor"
    / "schema.gen.ts"
)

# 15 项口径:13 节点(含 doc 根与 text)+ 2 mark
EXPECTED_NODES = {
    "doc",
    "section",
    "para",
    "locked_paragraph",
    "table",
    "table_row",
    "table_cell",
    "amount_cell",
    "enum_cell",
    "todo_block",
    "attachment_ref",
    "toc_entry",
    "text",
}
EXPECTED_MARKS = {"provenance", "status_mark"}


def _load():
    assert YAML_PATH.exists(), f"缺 document_ast_schema.yaml: {YAML_PATH}"
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))


def test_schema_has_15_entries():
    data = _load()
    node_names = {n["name"] for n in data["nodes"]}
    mark_names = {m["name"] for m in data["marks"]}
    assert node_names == EXPECTED_NODES, f"节点集漂移: {node_names ^ EXPECTED_NODES}"
    assert mark_names == EXPECTED_MARKS, f"mark 集漂移: {mark_names ^ EXPECTED_MARKS}"
    assert len(data["nodes"]) == 13 and len(data["marks"]) == 2


def test_schema_node_fields_complete():
    data = _load()
    for node in data["nodes"]:
        assert node.get("kind") in {"block", "inline"}, node["name"]
        assert isinstance(node.get("content", ""), str), node["name"]
        assert isinstance(node.get("attrs", []), list), node["name"]
        assert "tag" in node.get("to_dom", {}), f"{node['name']} 缺 to_dom"
        for attr in node.get("attrs", []):
            assert {"name", "type", "default"} <= set(attr), (node["name"], attr)
            assert attr["type"] in {"string", "int", "number", "bool", "enum", "list"}, attr
            if attr["type"] == "enum":
                assert isinstance(attr.get("values"), list) and attr["values"], attr
    for mark in data["marks"]:
        assert "tag" in mark.get("to_dom", {}), mark["name"]


def test_schema_version_format():
    data = _load()
    v = data["schema_version"]
    assert isinstance(v, str) and v.count(".") == 2, v


def test_codegen_output_in_sync():
    """codegen 漂移钉:生成文件存在、版本一致、每个 yaml 节点/mark 在产物中。"""
    assert GEN_PATH.exists(), f"缺 codegen 产物: {GEN_PATH}(跑 editor_schema_gen.py)"
    data = _load()
    gen = GEN_PATH.read_text(encoding="utf-8")
    assert "GENERATED" in gen, "生成文件缺 GENERATED 头"
    assert f'AST_SCHEMA_VERSION = "{data["schema_version"]}"' in gen, "版本漂移"
    for node in data["nodes"]:
        assert f'"{node["name"]}":' in gen, f"{node['name']} 未出现在 schema.gen.ts"
    for mark in data["marks"]:
        assert f'"{mark["name"]}":' in gen, f"mark {mark['name']} 未出现在 schema.gen.ts"
