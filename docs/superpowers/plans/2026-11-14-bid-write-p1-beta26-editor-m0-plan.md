# bid_write 批廿六(P1-M0)ProseMirror 正文编辑层骨架 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地《Word 编辑器技术方案》§15 下一步①②的 M0 骨架——`document_ast_schema.yaml` 单一 schema 双端同源 codegen + PM 编辑器最小可运行(挂载 WorkbenchView,演示文档,编辑/撤销/序列化真实可用)。

**Architecture:** 事实层 AST yaml(单一真源)→ Python codegen → 前端 `schema.gen.ts`(PM Schema + TS 类型,禁手写两份)→ hydrate/serialize + EditorState(history + meta.source 分层)→ React 组件挂 WorkbenchView 中栏。断言联动(liveAssert)挂 M2 批,编辑约束(lockedPara 只读等)挂 M1 批——本批 schema/toDOM 就位但**不设编辑约束**,诚实标注。

**Tech Stack:** prosemirror-model/state/view(已有直接依赖)+ 新增 prosemirror-history/keymap/commands;PyYAML(backend 已有);rstest node 环境;pytest drift-pin。

**权威设计:** 用户 2026-11-13 提供的《Word 编辑器技术方案》(§1-§15,未落库;要点已存 auto-memory `bid-write-editor-spec-pm.md`)。本计划 M0 范围 = 方案 §13 里程碑 M0(4 人日),**不含** §15② 的「改单价→金额只读刷新→liveAssert 标黄」链路(依赖 M1 约束 + M2 联动,挂批廿七/廿八)。

**M0 明确不做(诚实面):**
- 锁定段/金额格/枚举格**编辑约束**(filterTransaction 拦截)= M1;M0 仅 toDOM 视觉样式(灰底/红框虚线)。
- provenanceDecor/statusDecor/liveAssert 断言联动 = M2;M0 仅 schema 定义 mark。
- 后端文档 AST 存储与 GET/PUT 接口 = 后续批;M0 编辑器加载**演示文档**(徽标明示「演示数据」),保存=本地序列化。
- docx 导入导出、协同(y-prosemirror)、大表虚拟化 = 交付层/M3。

**schema 15 项口径(方案 §二「15 种节点」对齐):** 12 节点(doc 根 + section/para/locked_paragraph/table/table_row/table_cell/amount_cell/enum_cell/todo_block/attachment_ref/toc_entry)+ 2 mark(provenance/status_mark)+ text = 15。PM 节点名与 AST 类型名**同名零改名**(方案 §四 camelCase 为建议名,M0 弃用以消灭改名漂移层)。

**依赖变更警告:** package.json 变更需 `make rebuild-frontend` 重建前端镜像(node_modules 烘焙,Task 6)。

---

### Task 1: document_ast_schema.yaml 事实层单一 schema + 后端自检钉

**Files:**
- Create: `backend/app/extensions/bid_write/document_ast_schema.yaml`
- Test: `backend/tests/test_bid_write_editor_schema.py`

- [x] **Step 1: 写失败测试(schema 自检)**

```python
# backend/tests/test_bid_write_editor_schema.py
"""批廿六 M0:document_ast_schema.yaml 单一 schema 自检(EAI-CUSTOM)。

事实层契约:PM schema 与 TS 类型由本 yaml 经 editor_schema_gen.py 同源生成,
禁止手写两份(方案 §十四 风险三条之一)。本文件钉:结构完整性 + codegen 产物漂移。
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

# 15 项口径:12 节点(含 doc 根)+ 2 mark + text
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
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_write_editor_schema.py -v`
Expected: FAIL(yaml 缺失断言)

- [x] **Step 3: 写 document_ast_schema.yaml**

```yaml
# document_ast_schema.yaml — bid_write 正文文档 AST 事实层单一 schema
# (EAI-CUSTOM 2026-11-14,批廿六 M0;权威设计=《Word 编辑器技术方案》三层架构)
#
# 单一真源铁律(方案 §十四):PM schema 与 TS 类型必须由本文件生成
#   cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_write.editor_schema_gen
#   → frontend/src/extensions/bid-write/editor/schema.gen.ts
# 禁止手写两份;漂移由 test_bid_write_editor_schema.py 钉住。
#
# 15 项口径(方案 §二「15 种节点」):13 节点(含 doc 根与 text)+ 2 mark = 15。
# PM 节点名 == AST 类型名,零改名(方案 §四 lockedPara 等驼峰为建议名,M0 弃用)。
# 版本锚点:方案目标 shared_schema@2.4.0;当前仓库断言注册表 assertions/p0.yaml
# schema_version=1.0.0 独立演进,统一锚点挂后续批,本文件版本独立演进。
#
# M0 边界(诚实面):attrs 只定义不约束——锁定段/金额格编辑约束挂 M1 批;
# provenance/status_mark 的 decoration 回写挂 M2 批;parseDOM 不定义(hydrate 走
# nodeFromJSON,粘贴按纯文本落位,富文本粘贴清洗挂后续批)。
schema_version: "0.1.0"
layer: WR

nodes:
  - name: doc
    kind: block
    content: block+
    attrs: []
    to_dom: {tag: div, class: bwe-doc}

  - name: section
    kind: block
    content: block+
    attrs:
      - {name: level, type: int, default: 1, note: 标题级 1-4}
      - {name: title, type: string, default: "", note: 章节标题;M0 只展示,属性编辑入口挂 M1+}
      - {name: section_id, type: string, default: ""}
    to_dom: {tag: div, class: bwe-section, data_attrs: {data-title: title, data-level: level}}

  - name: para
    kind: block
    content: inline*
    attrs:
      - {name: slot_id, type: string, default: ""}
    to_dom: {tag: p, class: bwe-para}

  - name: locked_paragraph
    kind: block
    content: inline*
    attrs:
      - {name: template_id, type: string, default: ""}
      - {name: similarity_floor, type: number, default: 0.98, note: SK-BL-007 阈值;M0 仅展示}
    to_dom: {tag: div, class: bwe-locked, data_attrs: {data-template-id: template_id}}

  - name: table
    kind: block
    content: table_row+
    attrs:
      - {name: table_type, type: enum, values: [price, response, list], default: price}
    to_dom: {tag: table, class: bwe-table, wrap: [tbody]}

  - name: table_row
    kind: block
    content: (table_cell | amount_cell | enum_cell)+
    attrs:
      - {name: row_id, type: string, default: ""}
    to_dom: {tag: tr, class: bwe-row}

  - name: table_cell
    kind: block
    content: inline*
    attrs:
      - {name: col_role, type: enum, values: [name, qty, unit, remark], default: name, note: 角色驱动 M1 可编辑性;qty/unit 对齐 SK-PS-002 数量一致}
    to_dom: {tag: td, class: bwe-cell}

  - name: amount_cell
    kind: block
    content: inline*
    attrs:
      - {name: readonly, type: bool, default: true, note: M0 仅声明;filterTransaction 只读拦截挂 M1}
      - {name: computed_expr, type: string, default: "", note: 计算式,值由内核重算(方案 §5.3)}
      - {name: role, type: enum, values: [amount, subtotal, total_num, total_cn], default: amount}
    to_dom: {tag: td, class: bwe-amount}

  - name: enum_cell
    kind: block
    content: inline*
    attrs:
      - {name: enum_values, type: list, default: [], note: 候选枚举,来源 tender.*/policy;下拉禁自由输入挂 M1}
      - {name: current, type: string, default: ""}
    to_dom: {tag: td, class: bwe-enum}

  - name: todo_block
    kind: block
    atom: true
    content: ""
    attrs:
      - {name: missing, type: string, default: ""}
      - {name: pending_item_id, type: string, default: ""}
      - {name: level, type: enum, values: [D0, D1], default: D0}
      - {name: blocks_export, type: bool, default: true}
    to_dom: {tag: div, class: bwe-todo, data_attrs: {data-missing: missing, data-level: level}}

  - name: attachment_ref
    kind: inline
    atom: true
    content: ""
    attrs:
      - {name: attachment_no, type: string, default: ""}
      - {name: anchor, type: string, default: ""}
    to_dom: {tag: span, class: bwe-attach, data_attrs: {data-no: attachment_no}}

  - name: toc_entry
    kind: block
    atom: true
    content: ""
    attrs:
      - {name: title, type: string, default: ""}
      - {name: page_placeholder, type: string, default: "—", note: 页码为渲染期回填值(方案 §八)}
    to_dom: {tag: div, class: bwe-toc, data_attrs: {data-title: title, data-page: page_placeholder}}

  - name: text
    kind: inline
    content: ""
    attrs: []
    to_dom: {tag: span, class: ""}

marks:
  - name: provenance
    note: 溯源角标 mark(方案 §四 Mark 层);decoration widget 呈现挂 M2;导出投影剥离(§四)
    attrs:
      - {name: clause_id, type: string, default: ""}
      - {name: entity_id, type: string, default: ""}
      - {name: anchor, type: string, default: ""}
    to_dom: {tag: sup, class: bwe-prov, data_attrs: {data-clause: clause_id, data-entity: entity_id}}

  - name: status_mark
    note: D1 标黄 mark;liveAssert 回写挂 M2;导出投影剥离
    attrs:
      - {name: state, type: enum, values: [D0, D1, D2], default: D1}
      - {name: err_code, type: string, default: ""}
    to_dom: {tag: span, class: bwe-status, data_attrs: {data-state: state, data-err: err_code}}
```

- [x] **Step 4: 跑自检测试通过(除 codegen 钉)**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_write_editor_schema.py -v`
Expected: `test_codegen_output_in_sync` FAIL(产物未生成),其余 3 个 PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/extensions/bid_write/document_ast_schema.yaml backend/tests/test_bid_write_editor_schema.py
git commit -m "feat(bid-write): 批廿六 M0-a——document_ast_schema.yaml 事实层单一 schema(15 项=13 节点+2 mark;零改名;attrs 只定义不约束的 M0 诚实面)+ 结构自检钉"
```

---

### Task 2: codegen 脚本 + schema.gen.ts 同源产物

**Files:**
- Create: `backend/app/extensions/bid_write/editor_schema_gen.py`
- Create(generated): `frontend/src/extensions/bid-write/editor/schema.gen.ts`

- [x] **Step 1: 写 codegen 脚本**

```python
"""editor_schema_gen.py — document_ast_schema.yaml → PM Schema + TS 类型 codegen
(EAI-CUSTOM 批廿六 M0;单一 schema 双端同源,方案 §15 下一步①)。

用法:cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_write.editor_schema_gen
产物:frontend/src/extensions/bid-write/editor/schema.gen.ts(提交入库,前端无构建期 yaml 依赖)。
"""
from __future__ import annotations

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
YAML_PATH = HERE / "document_ast_schema.yaml"
OUT_PATH = (
    HERE.parents[2] / "frontend" / "src" / "extensions" / "bid-write" / "editor" / "schema.gen.ts"
)

HEADER = """// GENERATED by backend/app/extensions/bid_write/editor_schema_gen.py
// from document_ast_schema.yaml — DO NOT EDIT BY HAND.
// Regenerate: cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_write.editor_schema_gen
// EAI-CUSTOM 批廿六 M0(单一 schema 双端同源;漂移钉 backend/tests/test_bid_write_editor_schema.py)。
import { Schema } from "prosemirror-model";

export const AST_SCHEMA_VERSION = "{version}" as const;
export const AST_NODE_COUNT = {count} as const;

export const AST_NODE_TYPES = [
{node_types}] as const;
export type AstNodeType = (typeof AST_NODE_TYPES)[number];
export const AST_MARK_TYPES = [
{mark_types}] as const;
export type AstMarkType = (typeof AST_MARK_TYPES)[number];

/** AST JSON 树(与 PM doc JSON 同形;强类型随 M2 执行器契约再收紧)。 */
export interface AstJsonNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: AstJsonNode[];
  text?: string;
  marks?: {{ type: string; attrs?: Record<string, unknown> }}[];
}

/** yaml enum 候选(M1 枚举下拉的数据源)。 */
export const AST_ENUM_VALUES = {{
{enum_values}}} as const;

export const bidWriteSchema = new Schema({{
  nodes: {{
{nodes_spec}  }},
  marks: {{
{marks_spec}  }},
}});
"""

TYPE_MAP = {
    "string": 'type Attrs = Record<string, unknown>',
}


def _ts_str(value: object) -> str:
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def _ts_default(attr: dict) -> str:
    t = attr["type"]
    d = attr.get("default")
    if t == "string" or t == "enum":
        return _ts_str(d if d is not None else "")
    if t == "int" or t == "number":
        return str(d if d is not None else 0)
    if t == "bool":
        return "true" if d else "false"
    if t == "list":
        return "[]"
    raise ValueError(f"未知 attr 类型 {t}")


def _ts_attrs(attrs: list[dict]) -> str:
    if not attrs:
        return ""
    inner = ", ".join(f"{a['name']}: {_ts_default(a)}" for a in attrs)
    return f"attrs: {{ {inner} }}"


def _ts_to_dom(spec: dict, indent: str) -> str:
    tag = spec["tag"]
    cls = spec.get("class", "")
    data = spec.get("data_attrs", {})
    dom_attrs = []
    if cls:
        dom_attrs.append(f'class: {cls!r}')
    for k, attr_name in data.items():
        dom_attrs.append(f'{k}: node.attrs.{attr_name} ?? ""')
    attrs_js = "{ " + ", ".join(dom_attrs) + " }" if dom_attrs else "{}"
    wrap = spec.get("wrap", [])
    if wrap:
        inner = ", ".join(f'"{w}"' for w in wrap) + ", 0"
        arr = f'[{tag!r}, {attrs_js}, [{inner}]]'
    elif spec.get("hole", True) and not spec.get("atom"):
        arr = f'[{tag!r}, {attrs_js}, 0]'
    else:
        arr = f'[{tag!r}, {attrs_js}]'
    return f"toDOM: (node) => {arr},"


def _node_spec(node: dict, indent: str) -> str:
    lines = [f"{indent}\"{node['name']}\": {{"]
    kind = node.get("kind")
    if kind == "block":
        lines.append(f"{indent}  group: \"block\",")
    elif kind == "inline":
        lines.append(f"{indent}  group: \"inline\",")
    content = node.get("content", "")
    if content:
        lines.append(f"{indent}  content: {content!r},")
    if node.get("atom") or (content == "" and node["name"] not in {"text"}):
        lines.append(f"{indent}  atom: true,")
    attrs_js = _ts_attrs(node.get("attrs", []))
    if attrs_js:
        lines.append(f"{indent}  {attrs_js},")
    if node["name"] == "text":
        lines.pop()  # text 无 toDOM(PM 默认渲染)
    else:
        lines.append(f"{indent}  {_ts_to_dom(node['to_dom'], indent + '  ')}")
    lines.append(f"{indent}}},")
    return "\n".join(lines)


def _mark_spec(mark: dict, indent: str) -> str:
    lines = [f"{indent}\"{mark['name']}\": {{"]
    attrs_js = _ts_attrs(mark.get("attrs", []))
    if attrs_js:
        lines.append(f"{indent}  {attrs_js},")
    lines.append(f"{indent}  {_ts_to_dom(mark['to_dom'], indent + '  ')}")
    lines.append(f"{indent}}},")
    return "\n".join(lines)


def main() -> None:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    marks = data["marks"]
    enum_values = {}
    for node in nodes:
        for attr in node.get("attrs", []):
            if attr["type"] == "enum":
                enum_values[attr["name"]] = list(attr["values"])
    for mark in marks:
        for attr in mark.get("attrs", []):
            if attr["type"] == "enum":
                enum_values[attr["name"]] = list(attr["values"])

    node_types = "".join(f'  "{n["name"]}",\n' for n in nodes)
    mark_types = "".join(f'  "{m["name"]}",\n' for m in marks)
    enum_js = "".join(
        f"  {k}: [{', '.join(_ts_str(v) for v in vs)}],\n" for k, vs in enum_values.items()
    )
    nodes_spec = "".join(_node_spec(n, "    ") for n in nodes)
    marks_spec = "".join(_mark_spec(m, "    ") for m in marks)
    count = len(nodes) + len(marks)

    out = HEADER.format(
        version=data["schema_version"],
        count=count,
        node_types=node_types,
        mark_types=mark_types,
        enum_values=enum_js,
        nodes_spec=nodes_spec,
        marks_spec=marks_spec,
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(out, encoding="utf-8", newline="\n")
    print(f"written {OUT_PATH} ({count} entries, v{data['schema_version']})")


if __name__ == "__main__":
    main()
```

- [x] **Step 2: 生成产物并跑通 drift 钉**

Run: `cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_write.editor_schema_gen && PYTHONPATH=. uv run pytest tests/test_bid_write_editor_schema.py -v`
Expected: 4 PASS(含 test_codegen_output_in_sync)

- [x] **Step 3: 人工检查产物形态**

打开 `frontend/src/extensions/bid-write/editor/schema.gen.ts`:确认 `AST_SCHEMA_VERSION = "0.1.0"`、`AST_NODE_COUNT = 15`、`bidWriteSchema` 含 13 节点 + 2 mark、text 节点无 toDOM、amount_cell `readonly: true` 默认、`AST_ENUM_VALUES` 收敛 enum 候选。

- [x] **Step 4: 提交**

```bash
git add backend/app/extensions/bid_write/editor_schema_gen.py frontend/src/extensions/bid-write/editor/schema.gen.ts
git commit -m "feat(bid-write): 批廿六 M0-b——editor_schema_gen.py codegen(单一 schema 双端同源,方案 §15①)+ schema.gen.ts 产物入库(PM Schema+TS 类型+AST_ENUM_VALUES)"
```

---

### Task 3: prosemirror 依赖 + 前端 schema/往返/history 单测

**Files:**
- Modify: `frontend/package.json`(新增 3 依赖)
- Modify: `frontend/pnpm-lock.yaml`(pnpm add 自动)
- Test: `frontend/tests/unit/extensions/bid-write-editor-schema.test.ts`
- Test: `frontend/tests/unit/extensions/bid-write-editor-roundtrip.test.ts`(Task 4 一起跑)

- [x] **Step 1: 安装依赖(host,经 pnpm.py wrapper)**

Run: `cd frontend && python ../scripts/pnpm.py add prosemirror-history prosemirror-keymap prosemirror-commands`
Expected: package.json dependencies 出现 3 项;lockfile 更新。

- [x] **Step 2: 写 schema 单测(失败)**

```ts
// frontend/tests/unit/extensions/bid-write-editor-schema.test.ts
import { describe, expect, it } from "rstest";

import {
  AST_ENUM_VALUES,
  AST_MARK_TYPES,
  AST_NODE_COUNT,
  AST_NODE_TYPES,
  AST_SCHEMA_VERSION,
  bidWriteSchema,
} from "@/extensions/bid-write/editor/schema.gen";

describe("bid-write editor schema.gen", () => {
  it("15 项口径:13 节点 + 2 mark", () => {
    expect(AST_NODE_COUNT).toBe(15);
    expect(AST_NODE_TYPES).toHaveLength(13);
    expect(AST_MARK_TYPES).toHaveLength(2);
    expect(Object.keys(bidWriteSchema.nodes)).toHaveLength(13);
    expect(Object.keys(bidWriteSchema.marks)).toHaveLength(2);
  });

  it("关键节点在位且 attrs 默认正确", () => {
    expect(AST_NODE_TYPES).toContain("locked_paragraph");
    expect(AST_NODE_TYPES).toContain("amount_cell");
    const amount = bidWriteSchema.nodes.amount_cell;
    expect(amount.attrs.readonly.default).toBe(true);
    expect(bidWriteSchema.nodes.locked_paragraph.attrs.similarity_floor.default).toBe(
      0.98,
    );
    expect(bidWriteSchema.nodes.section.attrs.level.default).toBe(1);
  });

  it("toDOM 类名按 yaml 落位", () => {
    const doc = bidWriteSchema.nodeFromJSON({
      type: "doc",
      content: [
        {
          type: "section",
          attrs: { level: 1, title: "一、投标函", section_id: "S1" },
          content: [{ type: "para", content: [{ type: "text", text: "正文" }] }],
        },
      ],
    });
    const dom = doc.firstChild?.typeSpec.toDOM?.(doc.firstChild as never);
    expect(JSON.stringify(dom)).toContain("bwe-section");
    expect(JSON.stringify(dom)).toContain("data-title");
  });

  it("AST_ENUM_VALUES 收敛 yaml enum 候选", () => {
    expect(AST_ENUM_VALUES.table_type).toContain("price");
    expect(AST_ENUM_VALUES.role).toContain("amount");
  });

  it("版本常量随 yaml", () => {
    expect(AST_SCHEMA_VERSION).toBe("0.1.0");
  });
});
```

- [x] **Step 3: 跑 schema 单测**

Run: `cd frontend && python ../scripts/pnpm.py exec rstest tests/unit/extensions/bid-write-editor-schema.test.ts`
Expected: PASS(依赖 Task 2 产物已生成)。若 `typeSpec.toDOM` 形状不符,以实际 PM API 微调断言(看 `bidWriteSchema.nodes.section` 的 toDOM 是否函数)。

- [x] **Step 4: 提交**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/tests/unit/extensions/bid-write-editor-schema.test.ts
git commit -m "feat(bid-write): 批廿六 M0-c——prosemirror-history/keymap/commands 依赖 + schema.gen 前端单测(15 项/attrs 默认/toDOM 类名/enum 候选)"
```

---

### Task 4: hydrate/serialize + EditorState(meta.source 分层)+ 单测

**Files:**
- Create: `frontend/src/extensions/bid-write/editor/doc.ts`
- Create: `frontend/src/extensions/bid-write/editor/state.ts`
- Create: `frontend/src/extensions/bid-write/editor/demo.ts`
- Test: `frontend/tests/unit/extensions/bid-write-editor-roundtrip.test.ts`
- Test: `frontend/tests/unit/extensions/bid-write-editor-history.test.ts`

- [x] **Step 1: 写 doc.ts(hydrate/serialize)**

```ts
// frontend/src/extensions/bid-write/editor/doc.ts
// EAI-CUSTOM 批廿六 M0——AST↔PMdoc 同形映射(方案 §三;AST JSON 与 PM JSON 同形,
// nodeFromJSON 顺带校验 schema 合法性,未知类型抛错)。
import { type Node as PMNode } from "prosemirror-model";

import { type AstJsonNode, bidWriteSchema } from "./schema.gen";

export function hydrateAst(ast: AstJsonNode): PMNode {
  return bidWriteSchema.nodeFromJSON(ast);
}

export function serializeDoc(doc: PMNode): AstJsonNode {
  return doc.toJSON() as AstJsonNode;
}

/** 序列化文本投影(导出投影口径:marks 不进文本,方案 §四 剥离规则)。 */
export function docPlainText(doc: PMNode): string {
  return doc.textBetween(0, doc.content.size, "\n", "");
}
```

- [x] **Step 2: 写 state.ts(meta.source 分层 + history)**

```ts
// frontend/src/extensions/bid-write/editor/state.ts
// EAI-CUSTOM 批廿六 M0——事务分层 meta.source ∈ {user, system, decor}(方案 §七);
// 撤销栈只收用户编辑:system/decor 事务 setMeta("addToHistory", false)。
// M1 起系统/装饰事务经此二 helper 构造;用户输入默认 user 且入栈。
import { EditorState, type Transaction } from "prosemirror-state";
import { baseKeymap } from "prosemirror-commands";
import { history, redo, undo } from "prosemirror-history";
import { keymap } from "prosemirror-keymap";

import { hydrateAst } from "./doc";
import { type AstJsonNode } from "./schema.gen";

export type EditorTrSource = "user" | "system" | "decor";

export function systemTr(tr: Transaction): Transaction {
  tr.setMeta("source", "system");
  tr.setMeta("addToHistory", false);
  return tr;
}

export function decorTr(tr: Transaction): Transaction {
  tr.setMeta("source", "decor");
  tr.setMeta("addToHistory", false);
  return tr;
}

export function trSource(tr: Transaction): EditorTrSource {
  return (tr.getMeta("source") as EditorTrSource | undefined) ?? "user";
}

export function createBidWriteEditorState(ast: AstJsonNode): EditorState {
  return EditorState.create({
    doc: hydrateAst(ast),
    plugins: [
      history(),
      keymap({ "Mod-z": undo, "Mod-Z": redo, "Mod-y": redo }),
      keymap(baseKeymap),
    ],
  });
}
```

- [x] **Step 3: 写 demo.ts(演示文档)**

```ts
// frontend/src/extensions/bid-write/editor/demo.ts
// EAI-CUSTOM 批廿六 M0——M0 演示文档(后端正文存储未接入;方案 §15② 最小样例:
// section/para/locked_paragraph/amount_cell/enum_cell/todo_block/toc_entry 全露脸)。
import { type AstJsonNode } from "./schema.gen";

export function demoWorkbenchAst(): AstJsonNode {
  return {
    type: "doc",
    content: [
      {
        type: "toc_entry",
        attrs: { title: "目录", page_placeholder: "—" },
      },
      {
        type: "section",
        attrs: { level: 1, title: "一、投标函", section_id: "S-bid-letter" },
        content: [
          {
            type: "para",
            attrs: { slot_id: "bl-opening" },
            content: [
              {
                type: "text",
                text: "致 ",
              },
              {
                type: "text",
                text: "招标人",
                marks: [
                  {
                    type: "provenance",
                    attrs: {
                      clause_id: "B-014",
                      entity_id: "M-88",
                      anchor: "P.34",
                    },
                  },
                ],
              },
              {
                type: "text",
                text: ":根据贵方招标文件(编号 T-2026-118)要求,我方愿以人民币 ",
              },
              {
                type: "text",
                text: "1,280,000.00",
                marks: [
                  { type: "status_mark", attrs: { state: "D1", err_code: "SK-PS-003" } },
                ],
              },
              { type: "text", text: " 元(大写:壹佰贰拾捌万元整)的投标总价,按招标文件要求完成全部工程内容。" },
            ],
          },
          {
            type: "locked_paragraph",
            attrs: { template_id: "BID-LOCK-001", similarity_floor: 0.98 },
            content: [
              {
                type: "text",
                text: "本投标函自开标之日起 90 个日历日内有效,我方确认已理解并接受招标文件全部条款。",
              },
            ],
          },
        ],
      },
      {
        type: "section",
        attrs: { level: 1, title: "二、报价表", section_id: "S-price" },
        content: [
          {
            type: "table",
            attrs: { table_type: "price" },
            content: [
              {
                type: "table_row",
                attrs: { row_id: "R-1" },
                content: [
                  { type: "table_cell", attrs: { col_role: "name" }, content: [{ type: "text", text: "设备 A" }] },
                  { type: "table_cell", attrs: { col_role: "qty" }, content: [{ type: "text", text: "4" }] },
                  { type: "table_cell", attrs: { col_role: "unit_price" === undefined ? "unit" : "unit" }, content: [{ type: "text", text: "200,000.00" }] },
                  { type: "amount_cell", attrs: { readonly: true, computed_expr: "qty*unit_price", role: "amount" }, content: [{ type: "text", text: "800,000.00" }] },
                ],
              },
              {
                type: "table_row",
                attrs: { row_id: "R-2" },
                content: [
                  { type: "table_cell", attrs: { col_role: "name" }, content: [{ type: "text", text: "安装调试" }] },
                  { type: "table_cell", attrs: { col_role: "qty" }, content: [{ type: "text", text: "1" }] },
                  { type: "table_cell", attrs: { col_role: "unit" }, content: [{ type: "text", text: "460,000.00" }] },
                  { type: "amount_cell", attrs: { readonly: true, computed_expr: "qty*unit_price", role: "amount" }, content: [{ type: "text", text: "460,000.00" }] },
                ],
              },
              {
                type: "table_row",
                attrs: { row_id: "R-sum" },
                content: [
                  { type: "table_cell", attrs: { col_role: "name" }, content: [{ type: "text", text: "合计" }] },
                  { type: "enum_cell", attrs: { enum_values: ["完全响应", "正偏离", "负偏离"], current: "完全响应" }, content: [{ type: "text", text: "完全响应" }] },
                  { type: "amount_cell", attrs: { readonly: true, computed_expr: "sum(amount)", role: "total_num" }, content: [{ type: "text", text: "1,260,000.00" }] },
                  { type: "amount_cell", attrs: { readonly: true, computed_expr: "to_cn(total_num)", role: "total_cn" }, content: [{ type: "text", text: "壹佰贰拾陆万元整" }] },
                ],
              },
            ],
          },
        ],
      },
      {
        type: "section",
        attrs: { level: 1, title: "三、供货承诺", section_id: "S-supply" },
        content: [
          {
            type: "todo_block",
            attrs: {
              missing: "供货期承诺函(关联 SK-CMN-005)",
              pending_item_id: "P-101",
              level: "D0",
              blocks_export: true,
            },
          },
        ],
      },
    ],
  };
}
```

注意 Step 3 里 `col_role: "unit_price" === undefined ? "unit" : "unit"` 是**笔误占位**,写文件时改为 `col_role: "unit"`(yaml enum 候选含 unit;unit_price 不在候选,方案 §5.6 来源列只读——名字用 `unit`)。

- [x] **Step 4: 写往返单测(失败→实现已在 Step 1,直接验证)**

```ts
// frontend/tests/unit/extensions/bid-write-editor-roundtrip.test.ts
import { describe, expect, it } from "rstest";

import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { docPlainText, hydrateAst, serializeDoc } from "@/extensions/bid-write/editor/doc";
import { type AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";

describe("AST ↔ PMdoc 往返", () => {
  it("演示文档 hydrate→serialize 字节级一致(方案 §十二 Schema 往返口径)", () => {
    const ast = demoWorkbenchAst();
    const doc = hydrateAst(ast);
    const back = serializeDoc(doc);
    expect(JSON.stringify(back)).toBe(JSON.stringify(ast));
  });

  it("往返幂等:二次往返不再变化", () => {
    const once = serializeDoc(hydrateAst(demoWorkbenchAst()));
    const twice = serializeDoc(hydrateAst(once));
    expect(JSON.stringify(twice)).toBe(JSON.stringify(once));
  });

  it("未知节点类型被 schema 拒绝", () => {
    const bad = { type: "bogus_node" } as unknown as AstJsonNode;
    expect(() => hydrateAst(bad)).toThrow();
  });

  it("文本投影剥离 marks(provenance/status 不进文本)", () => {
    const doc = hydrateAst(demoWorkbenchAst());
    const text = docPlainText(doc);
    expect(text).toContain("1,280,000.00");
    expect(text).not.toContain("B-014");
    expect(text).not.toContain("SK-PS-003");
  });
});
```

Run: `cd frontend && python ../scripts/pnpm.py exec rstest tests/unit/extensions/bid-write-editor-roundtrip.test.ts`
Expected: PASS(toJSON/fromJSON 同形保证;若 attrs 键序差异失败,以对象相等断言替代字符串比较)

- [x] **Step 5: 写 history 分层单测**

```ts
// frontend/tests/unit/extensions/bid-write-editor-history.test.ts
import { describe, expect, it } from "rstest";
import { EditorState, TextSelection, Transaction } from "prosemirror-state";
import { redo, undo } from "prosemirror-history";

import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import {
  createBidWriteEditorState,
  decorTr,
  systemTr,
  trSource,
} from "@/extensions/bid-write/editor/state";

function type(state: EditorState, text: string): Transaction {
  const tr = state.tr;
  tr.setSelection(TextSelection.create(tr.doc, 1));
  tr.insertText(text);
  return tr;
}

describe("meta.source 事务分层(方案 §七 撤销栈口径)", () => {
  it("默认来源 user 且入撤销栈", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(type(s0, "X"));
    expect(trSource(s1.tr)).toBe("user");
    expect(undo(s1, undefined)).toBe(true);
  });

  it("system 事务不入撤销栈,undo 跳过系统内容", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(type(s0, "A"));
    const s2 = s1.apply(systemTr(type(s1, "B")));
    // 撤销:只回退用户插入的 "A","B" 保留
    expect(undo(s2, undefined)).toBe(true);
    const after = s2.apply(undo(s2));
    const text = after.doc.textBetween(0, after.doc.content.size, "\n", "");
    expect(text).not.toContain("A");
    expect(text).toContain("B");
    expect(redo(after, undefined)).toBe(true);
  });

  it("decor 事务同样不入栈", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(decorTr(type(s0, "D")));
    expect(undo(s1, undefined)).toBe(false);
  });

  it("trSource 缺省 user", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    expect(trSource(s0.tr)).toBe("user");
  });
});
```

Run: `cd frontend && python ../scripts/pnpm.py exec rstest tests/unit/extensions/bid-write-editor-history.test.ts`
Expected: PASS(若 undo(s, undefined) 语义不符,改用 dry-run 断言 `undo(s2)` 布尔 + apply 后文本断言,以实际为准)

- [x] **Step 6: 提交**

```bash
git add frontend/src/extensions/bid-write/editor/doc.ts frontend/src/extensions/bid-write/editor/state.ts frontend/src/extensions/bid-write/editor/demo.ts frontend/tests/unit/extensions/bid-write-editor-roundtrip.test.ts frontend/tests/unit/extensions/bid-write-editor-history.test.ts
git commit -m "feat(bid-write): 批廿六 M0-d——hydrate/serialize 同形映射+meta.source 事务分层(system/decor 不入撤销栈)+ 演示文档;往返/文本投影剥离/历史分层单测"
```

---

### Task 5: BidWriteEditor 组件 + bwe 编辑器样式

**Files:**
- Create: `frontend/src/extensions/bid-write/editor/BidWriteEditor.tsx`
- Modify: `frontend/src/app/bid-write/bid-write.css`(追加 `.bwe-*` 段)

- [x] **Step 1: 写组件**

```tsx
// frontend/src/extensions/bid-write/editor/BidWriteEditor.tsx
// EAI-CUSTOM 批廿六 M0——PM EditorView React 壳:useEffect 建观(SSR 安全)、
// 400ms 防抖 serialize 回调、undo/redo/serializeNow 命令柄(方案 §三/§六)。
"use client";

import { EditorView } from "prosemirror-view";
import { type Transaction, EditorState } from "prosemirror-state";
import { forwardRef, useImperativeHandle, useEffect, useRef, useState } from "react";
import { redo as redoCmd, undo as undoCmd } from "prosemirror-history";

import {
  createBidWriteEditorState,
} from "@/extensions/bid-write/editor/state";
import { serializeDoc } from "@/extensions/bid-write/editor/doc";
import { type AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";

export interface BidWriteEditorFlags {
  canUndo: boolean;
  canRedo: boolean;
}

export interface BidWriteEditorHandle {
  undo(): void;
  redo(): void;
  serializeNow(): AstJsonNode | null;
}

interface BidWriteEditorProps {
  initialAst: AstJsonNode;
  onDocChange?: (ast: AstJsonNode, flags: BidWriteEditorFlags) => void;
  debounceMs?: number;
  ariaLabel?: string;
}

export const BidWriteEditor = forwardRef<BidWriteEditorHandle, BidWriteEditorProps>(
  function BidWriteEditor({ initialAst, onDocChange, debounceMs = 400, ariaLabel = "投标正文编辑器" }, ref) {
    const placeRef = useRef<HTMLDivElement | null>(null);
    const viewRef = useRef<EditorView | null>(null);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [ready, setReady] = useState(false);

    useEffect(() => {
      const place = placeRef.current;
      if (!place) return;
      const state = createBidWriteEditorState(initialAst);
      const view = new EditorView(place, {
        state,
        dispatchTransaction(tr: Transaction) {
          view.updateState(view.state.apply(tr));
          if (timerRef.current) clearTimeout(timerRef.current);
          timerRef.current = setTimeout(() => {
            onDocChange?.(serializeDoc(view.state.doc), {
              canUndo: undoCmd(view.state, undefined),
              canRedo: redoCmd(view.state, undefined),
            });
          }, debounceMs);
        },
      });
      viewRef.current = view;
      setReady(true);
      return () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        view.destroy();
        viewRef.current = null;
        setReady(false);
      };
      // initialAst 由父级 useMemo 钉住;变更即重建视图(M0 无外部写入通道)
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialAst]);

    useImperativeHandle(
      ref,
      () => ({
        undo() {
          const view = viewRef.current;
          if (view) undoCmd(view.state, view.dispatch.bind(view));
        },
        redo() {
          const view = viewRef.current;
          if (view) redoCmd(view.state, view.dispatch.bind(view));
        },
        serializeNow() {
          const view = viewRef.current;
          return view ? serializeDoc(view.state.doc) : null;
        },
      }),
      [],
    );

    return (
      <div
        ref={placeRef}
        className="bwe-editor"
        role="textbox"
        aria-multiline="true"
        aria-label={ariaLabel}
        aria-busy={!ready}
      />
    );
  },
);
```

- [x] **Step 2: 追加 CSS 到 bid-write.css 末尾**

```css
/* ── M0 正文编辑器(bwe-*)——批廿六;约束视觉先行,编辑约束挂 M1 ─────────── */
.bwe-editor {
  border: 1px solid var(--line, #e5e7eb);
  border-radius: 8px;
  background: var(--bg, #fff);
  padding: 16px 20px;
  min-height: 320px;
  max-width: 900px;
  line-height: 1.7;
  font-size: 14px;
}
.bwe-editor:focus-visible { outline: 2px solid #2563eb33; outline-offset: 1px; }
.bwe-editor .bwe-doc { display: block; }
.bwe-editor .bwe-section { display: block; margin: 12px 0 4px; }
.bwe-editor .bwe-section::before {
  content: attr(data-title);
  display: block;
  font-weight: 600;
  font-size: 15px;
  margin: 8px 0 6px;
}
.bwe-editor .bwe-para { margin: 6px 0; }
.bwe-editor .bwe-locked {
  display: block;
  background: #f2f3f5;
  border: 1px solid #e0e2e6;
  border-radius: 6px;
  padding: 8px 12px;
  color: #4b5563;
  margin: 6px 0;
}
.bwe-editor .bwe-locked::before { content: "固定条款"; font-size: 11px; color: #6b7280; display: block; }
.bwe-editor table.bwe-table { border-collapse: collapse; width: 100%; margin: 8px 0; }
.bwe-editor table.bwe-table td { border: 1px solid #e5e7eb; padding: 4px 8px; }
.bwe-editor .bwe-amount { font-variant-numeric: tabular-nums; text-align: right; background: #f9fafb; }
.bwe-editor .bwe-enum { background: #f9fafb; }
.bwe-editor .bwe-todo {
  border: 1px dashed #d93026;
  border-radius: 6px;
  padding: 10px 12px;
  color: #b42318;
  background: #fef3f2;
  margin: 6px 0;
  font-size: 13px;
}
.bwe-editor .bwe-todo::before { content: "待补:" attr(data-missing) "(D" attr(data-level) ")"; display: block; }
.bwe-editor .bwe-attach::after { content: "[" attr(data-no) "]"; font-size: 12px; color: #2563eb; }
.bwe-editor .bwe-toc { color: #6b7280; font-size: 13px; margin: 4px 0; }
.bwe-editor .bwe-toc::after { content: attr(data-title) " … " attr(data-page); }
.bwe-editor sup.bwe-prov { font-size: 10px; color: #6b7280; cursor: default; }
.bwe-editor sup.bwe-prov::after { content: "[" attr(data-clause) "][" attr(data-entity) "]"; }
.bwe-editor .bwe-status { background: #fef6e0; border-radius: 3px; }

@media (prefers-color-scheme: dark) {
  .bwe-editor { background: #16181d; border-color: #2c2f36; color: #e5e7eb; }
  .bwe-editor .bwe-locked { background: #1f2228; border-color: #33373f; color: #9ca3af; }
  .bwe-editor table.bwe-table td { border-color: #2c2f36; }
  .bwe-editor .bwe-amount, .bwe-editor .bwe-enum { background: #1b1e24; }
  .bwe-editor .bwe-todo { background: #2a1512; border-color: #7f2d24; color: #f2b8b5; }
  .bwe-editor .bwe-status { background: #332a14; }
}
```

(类名/token 若与 bid-write.css 既有变量冲突,以既有变量为准替换硬编码色。)

- [x] **Step 3: 提交**

```bash
git add frontend/src/extensions/bid-write/editor/BidWriteEditor.tsx frontend/src/app/bid-write/bid-write.css
git commit -m "feat(bid-write): 批廿六 M0-e——BidWriteEditor React 壳(SSR 安全+400ms 防抖 serialize+undo/redo 柄)+ bwe 节点视觉(锁定灰底/金额等宽右对齐/TODO 红框虚线/溯源角标)"
```

---

### Task 6: WorkbenchView 挂载 + 工具栏接线 + 镜像重建

**Files:**
- Modify: `frontend/src/extensions/bid-write/components/WorkbenchView.tsx`

- [x] **Step 1: 挂载编辑器(替换 bw-empty-doc JSX,接真实命令柄)**

改动要点(整文件改后跑 lint):
- import 区加 `useRef` 与 `BidWriteEditor`/handle/demo:
  ```tsx
  import { useEffect, useMemo, useRef, useState } from "react";
  import {
    BidWriteEditor,
    type BidWriteEditorHandle,
  } from "@/extensions/bid-write/editor/BidWriteEditor";
  import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
  import type { AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";
  ```
- 组件体内:
  ```tsx
  const editorRef = useRef<BidWriteEditorHandle | null>(null);
  const [docAst, setDocAst] = useState<AstJsonNode | null>(null);
  const [flags, setFlags] = useState({ canUndo: false, canRedo: false });
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const initialAst = useMemo(() => demoWorkbenchAst(), []);
  const handleDocChange = useCallback(
    (ast: AstJsonNode, f: { canUndo: boolean; canRedo: boolean }) => {
      setDocAst(ast);
      setFlags(f);
    },
    [],
  );
  const handleSave = () => {
    const ast = editorRef.current?.serializeNow() ?? null;
    if (!ast) return;
    setDocAst(ast);
    setSavedAt(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
  };
  ```
  (`useCallback` 记得 import;防 render-prop 重挂陷阱用 `useMemo`/`useCallback` 钉引用。)
- card-h 右侧徽标:把 `<Lock/> 只读` 徽标换成
  ```tsx
  <span className="bw-doc-badge" title="M0 骨架:加载演示文档;后端正文存储与断言联动挂后续批">
    演示数据
  </span>
  ```
- ed-toolbar 接线:
  ```tsx
  <button type="button" onClick={() => editorRef.current?.undo()} disabled={!flags.canUndo} title="撤销(仅用户编辑入栈)">
    <Undo2 size={14} aria-hidden="true" />
  </button>
  <button type="button" onClick={() => editorRef.current?.redo()} disabled={!flags.canRedo} title="重做">
    <Redo2 size={14} aria-hidden="true" />
  </button>
  <span className="sep" />
  <button type="button" onClick={handleSave} title="保存=本地序列化;后端正文存储接口挂后续批">
    保存
  </button>
  <button type="button" disabled title="增量校验联动挂后续批(M2)">
    <RefreshCw size={14} aria-hidden="true" />
    重审受影响断言
  </button>
  <span className="ed-spacer" />
  <button type="button" disabled title="AI 建议挂后续批(M3)">
    <Sparkles size={14} aria-hidden="true" />
    查看 AI 建议
  </button>
  ```
- doc-body:删除 `bw-empty-doc` 整块 JSX,原位放
  ```tsx
  <BidWriteEditor ref={editorRef} initialAst={initialAst} onDocChange={handleDocChange} />
  {docAst ? (
    <p className="bw-muted bw-mt-sm" title="编辑器 AST 投影状态(唯一真值=AST)">
      AST 序列化 {docAst.content?.length ?? 0} 个顶层节点 · 撤销栈 {flags.canUndo ? "有步可撤" : "无"}
    </p>
  ) : null}
  ```
  (保留其后「当前章节的响应矩阵」表格不动。)
- banner info 文案改为:「正文编辑器 M0 骨架已接入(演示文档):结构化编辑/撤销/重做/本地序列化可用;编辑约束挂 M1,断言联动挂 M2,后端存储挂后续批。」
- PageHead subtitle 的「正文编辑器未接入」改为「正文编辑器 M0(演示文档)」。
- statusbar 在「预审查」段后加:
  ```tsx
  <span className="sep" />
  <span>{savedAt ? `已保存 ${savedAt}(本地)` : "未保存"}</span>
  ```

- [x] **Step 2: lint + typecheck**

Run: `cd frontend && python ../scripts/pnpm.py exec eslint src/extensions/bid-write --fix && python ../scripts/pnpm.py exec tsc --noEmit`
Expected: 0 error

- [x] **Step 3: 前端全量单测回归**

Run: `cd frontend && python ../scripts/pnpm.py exec rstest`
Expected: 0 failures(含既有 bid-write 用例不回归)

- [x] **Step 4: 提交**

```bash
git add frontend/src/extensions/bid-write/components/WorkbenchView.tsx
git commit -m "feat(bid-write): 批廿六 M0-f——WorkbenchView 挂载 PM 编辑器(演示文档徽标+undo/redo/本地保存接线;重审/AI 建议诚实置灰挂 M2/M3)+ statusbar 保存态"
```

- [x] **Step 5: 重建前端镜像(依赖变更,必须;后台跑)**

Run: `cd /d/eai/eai-flow-main && make rebuild-frontend`(run_in_background)
Expected: 镜像重建完成 → `docker compose -p eai-docker restart frontend`(make 目标内部处理);完成后浏览器 http://localhost:2026/bid-write → 工作台中栏出现可编辑演示文档(锁定段灰底/金额右对齐/TODO 红框),撤销/重做/保存真实可用。`make check-frontend-deps` 确认 host↔container 锁文件一致。

---

### Task 7: 后端回归 + wolf 四件套收口

**Files:**
- Modify: `.wolf/memory.md`,`.wolf/anatomy.md`,`.wolf/cerebrum.md`(视发现)
- Modify: `docs/superpowers/plans/2026-11-14-bid-write-p1-beta26-editor-m0-plan.md`(勾选)

- [x] **Step 1: 后端回归(全部 bid_write 用例含新 schema 钉)**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_write -v`
Expected: 全 PASS(0 fail;含 test_bid_write_editor_schema 4 例)

- [x] **Step 2: wolf 记账**

- `.wolf/memory.md` 追加批廿六落地行(时间/内容/commit/结果)
- `.wolf/anatomy.md` 补 `document_ast_schema.yaml`、`editor_schema_gen.py`、`schema.gen.ts`、`doc.ts`、`state.ts`、`demo.ts`、`BidWriteEditor.tsx` 条目
- `.wolf/cerebrum.md` 补 Key Learning:PM 节点名=AST 类型名零改名决策;addToHistory=false 是 prosemirror-history 官方分层闸;codegen 产物入库(前端无构建期 yaml 依赖)
- 前端依赖变更→镜像重建的老坑已在本计划 Task 6 重申,不另记 bug

- [x] **Step 3: 勾选本计划全部 checkbox 并提交**

```bash
git add -f docs/superpowers/plans/2026-11-14-bid-write-p1-beta26-editor-m0-plan.md
git add .wolf/memory.md .wolf/anatomy.md .wolf/cerebrum.md
git commit -m "docs(bid-write): 批廿六收口——plan 全勾+wolf 三件套(M0 骨架落地态:codegen 同源/分层历史/演示文档挂载;M1 约束/M2 联动/存储挂后续批)"
```

---

## Self-Review 记录

1. **Spec coverage**:方案 §15① (codegen) → Task 1-2;§15② 最小 Demo → Task 3-6(链路半程:渲染/编辑/历史,金额刷新与标黄显式推迟 M1/M2 并在 M0 明确不做一节声明);§13 M0 = schema+view+section/para/table 基础+history → 全覆盖;§七 meta.source 分层 → Task 4;§十二 往返/装饰剥离口径 → roundtrip 测试。
2. **Placeholder 扫描**:demo.ts Step 3 有一处显式标注的笔误占位(col_role),执行时改为 "unit";其余步骤代码完整。
3. **类型一致性**:`AstJsonNode` 在 doc/state/demo/组件间一致;handle 方法名 undo/redo/serializeNow 在 Task 5 定义与 Task 6 调用一致;flags {canUndo, canRedo} 一致。

## NEXT(后续批,不在本计划)

- **批廿七(建议)= M1 约束**:lockedPara filterTransaction 禁改 / amount+qty·unit 列只读 / enumCell 下拉禁自由输入 / todoBlock 不可编辑 + 尝试编辑 toast;含方案 §15②「改单价→金额只读刷新」前半链路。
- **批廿八(建议)= M2 联动**:provenanceDecor/statusDecor/liveAssert + 增量校验接线(受影响 node_id 子树 serialize→执行器→assertion_states→纯 decoration 回写)+ 后端文档 AST 存储与 GET/PUT。
- M3:diffSuggest/prosemirror-tables/编辑锁 TTL;M4:往返样例库扩面/e2e/可访问性。
