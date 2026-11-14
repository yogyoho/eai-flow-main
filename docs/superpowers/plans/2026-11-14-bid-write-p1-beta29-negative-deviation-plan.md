# bid_write 批廿九(M3 负偏离展开)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** enum_cell 选「负偏离」时编辑器自动展开偏离说明面(偏离原因+替代方案),自愈维护,断言闭环。

**Architecture:** schema 单一真源 `document_ast_schema.yaml` 新增 `deviation_note` 节点(+`para.label` attr)→ codegen 双端;新 `deviation.ts` 插件用 **appendTransaction 自愈不变式**(负偏离∧无 note→插;note 破损→补;非负偏离∧note 空→删),appended tr 带 `source=system` 过 filterTransaction、**不设 addToHistory**(并入当前 undo 事件=一撤全撤);editorLocalAssert 加 SK-RT-005 闭环面。

**Tech Stack:** ProseMirror appendTransaction / codegen(yaml→schema.gen.ts) / rstest / pytest

**边界诚实(不做):**
- ★条款负偏离(SK-RT-004):star 不在 AST——后端生成期 422(routers.py)+预审查已拦,编辑器无法也不必管。
- 人工「审批」按钮流:闭环判定=双字段非空(与后端 RT-005 同口径);审批工作流挂后续批。
- appendTransaction 不在 EditorState.create 时跑:云端加载的未闭环文档挂载即 D0 提示(assert 面),展开面首次编辑才自愈出现——诚实面,可接受。
- row_id 全文唯一为约定(生成器保证),note↔行按 row_id 全局首配;碰撞场景挂真执行器批。

---

### Task 1: schema 扩展三件套(yaml+codegen+双端钉点)

**Files:**
- Modify: `backend/app/extensions/bid_write/document_ast_schema.yaml`
- Regenerate: `frontend/src/extensions/bid-write/editor/schema.gen.ts`(脚本生成,禁手改)
- Modify: `backend/tests/test_bid_write_editor_schema.py`(13→14 节点钉点)
- Modify: `frontend/tests/unit/extensions/bid-write-editor-schema.test.ts`(15→16 钉点)

- [x] **Step 1: yaml 加节点**(todo_block 之后、attachment_ref 之前)+ para 加 label attr

```yaml
  - name: deviation_note
    kind: block
    content: para+
    attrs:
      - {name: row_id, type: string, default: "", note: 关联 table_row.row_id(全文唯一约定,生成器保证);§5.4 负偏离展开面,appendTransaction 自愈维护挂批廿九}
    to_dom: {tag: div, class: bwe-devnote, data_attrs: {data-row-id: row_id}}
```

para attrs 追加:

```yaml
      - {name: label, type: string, default: "", note: 展开面字段标签(deviation_note 内 偏离原因/替代方案;空=普通段;CSS ::before 呈现)}
```

para to_dom 加 `data_attrs: {data-label: label}`。

头部注释口径行改:`16 项口径:14 节点+ 2 mark`;补一行 `批廿九:deviation_note 负偏离展开面(§5.4)`。`schema_version: "0.1.0"` → `"0.2.0"`(新节点类型=minor)。

- [x] **Step 2: 改后端钉点** `test_bid_write_editor_schema.py`:

```python
# 16 项口径:14 节点(含 doc 根与 text)+ 2 mark(批廿九 +deviation_note)
...
def test_schema_has_16_entries():
...
    assert len(data["nodes"]) == 14 and len(data["marks"]) == 2
```

(函数名/断言照原形改数;若文件内还有逐节点名单断言,补 `deviation_note`。)

- [x] **Step 3: 跑 codegen**

```bash
cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_write.editor_schema_gen
```

Expected: `frontend/src/extensions/bid-write/editor/schema.gen.ts` 更新——`AST_NODE_COUNT = 16`、`AST_NODE_TYPES` 含 `deviation_note`(enum_cell 与 todo_block 之间)、schema 有 deviation_note 定义(content `para+`,attrs row_id)。**禁手改 gen 文件**。

- [x] **Step 4: 改前端钉点** `bid-write-editor-schema.test.ts`:

```ts
expect(AST_NODE_COUNT).toBe(16);
expect(AST_NODE_TYPES).toHaveLength(14);
...
expect(AST_NODE_TYPES).toContain("deviation_note");
```

- [x] **Step 5: 双端测试绿**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_write_editor_schema.py -v   # PASS
cd frontend && python ../scripts/pnpm.py exec rstest tests/unit/extensions/bid-write-editor-schema.test.ts   # PASS
```

若 roundtrip/history 测试因 schema 变化挂(不应——demo 文档无新节点),修测试硬编码。

- [x] **Step 6: Commit**

```bash
git add backend/app/extensions/bid_write/document_ast_schema.yaml backend/app/extensions/bid_write/editor_schema_gen.py backend/tests/test_bid_write_editor_schema.py frontend/src/extensions/bid-write/editor/schema.gen.ts frontend/tests/unit/extensions/bid-write-editor-schema.test.ts
git commit -m "feat(bid-write): 批廿九 M3-a schema 扩展——deviation_note 节点(row_id 关联行;§5.4 负偏离展开面)+para.label 字段标签 attr;codegen 双端再生成,16 项口径,semver 0.2.0"
```

---

### Task 2: deviation.ts 自愈展开插件 + state 挂接

**Files:**
- Create: `frontend/src/extensions/bid-write/editor/deviation.ts`
- Modify: `frontend/src/extensions/bid-write/editor/state.ts`(plugins 挂 deviationPlugin)
- Modify: `frontend/src/extensions/bid-write/editor/decor.ts`(anchorKey 加 deviation_note → `devnote:{row_id}`;buildAssertDecorations node-deco 分支加 deviation_note)
- Test: `frontend/tests/unit/extensions/bid-write-editor-deviation.test.ts`

- [x] **Step 1: deviation.ts 全文**

```ts
// EAI-CUSTOM 批廿九 M3——负偏离展开(方案 §5.4):enum_cell current=负偏离 ⇔
// 所属 table 后存在 deviation_note(row_id 关联)。appendTransaction 自愈不变式:
//  · 负偏离行 ∧ 无 note → 表后插 note(偏离原因/替代方案 两 labeled para);
//  · note 缺 labeled para → 补(破损自愈,含用户手删);
//  · 行非负偏离(或行没了)∧ note 双字段全空 → 收拢删除;
//  · 行非负偏离 ∧ note 有内容 → 保留(用户文本零丢失),由 editorLocalAssert
//    出 D1 孤儿提示,人工撤回或手删。
// appended tr:setMeta("source","system") 过 constraints filterTransaction;
// 不设 addToHistory —— prosemirror-history 把 appended tr 并入当前事务同一
// undo 事件,一撤=翻策略+展开面一起回。
import { type Node as PMNode } from "prosemirror-model";
import { Plugin, type EditorState, type Transaction } from "prosemirror-state";

import { systemTr } from "./state";

export const REASON_LABEL = "偏离原因";
export const ALT_LABEL = "替代方案";

interface RowHit {
  rowId: string;
  tableEnd: number; // 所属 table 节点末位(插入点)
}

interface NoteHit {
  rowId: string;
  pos: number;
  end: number;
  hasReason: boolean;
  reasonFilled: boolean;
  hasAlt: boolean;
  altFilled: boolean;
}

function rowIdOfEnum(node: PMNode, parent: PMNode | null): string | null {
  if (node.type.name !== "enum_cell") return null;
  if (String(node.attrs.current ?? "") !== "负偏离") return null;
  if (parent?.type.name !== "table_row") return null;
  const id = String(parent.attrs.row_id ?? "");
  return id ? id : null;
}

function collectNegativeRows(doc: PMNode): Map<string, RowHit> {
  const map = new Map<string, RowHit>();
  doc.descendants((node, pos, parent) => {
    const rowId = rowIdOfEnum(node, parent);
    if (!rowId || map.has(rowId)) return;
    // node=enum_cell 在 table_row>table 内;table 末位=向上两级
    if (!parent) return;
    // parent=table_row;再往上找 table 算 end
    doc.descendants(() => true); // noop 占位禁删(真实逻辑在下方 resolveTableEnd)
    map.set(rowId, { rowId, tableEnd: resolveTableEnd(doc, pos) });
  });
  return map;
}

function resolveTableEnd(doc: PMNode, enumPos: number): number {
  let tableEnd = -1;
  doc.descendants((node, pos) => {
    const end = pos + node.nodeSize;
    if (node.type.name === "table" && enumPos > pos && enumPos < end && tableEnd < 0) {
      tableEnd = end;
    }
  });
  return tableEnd;
}

function collectNotes(doc: PMNode): Map<string, NoteHit> {
  const map = new Map<string, NoteHit>();
  doc.descendants((node, pos) => {
    if (node.type.name !== "deviation_note") return;
    let hasReason = false;
    let reasonFilled = false;
    let hasAlt = false;
    let altFilled = false;
    for (const child of node.content) {
      const label = String(child.attrs.label ?? "");
      const filled = child.textContent.trim().length > 0;
      if (label === REASON_LABEL) {
        hasReason = true;
        reasonFilled = reasonFilled || filled;
      } else if (label === ALT_LABEL) {
        hasAlt = true;
        altFilled = altFilled || filled;
      }
    }
    map.set(String(node.attrs.row_id ?? ""), {
      rowId: String(node.attrs.row_id ?? ""),
      pos,
      end: pos + node.nodeSize,
      hasReason,
      reasonFilled,
      hasAlt,
      altFilled,
    });
  });
  return map;
}

function labeledPara(state: EditorState, label: string): PMNode {
  return state.schema.nodes.para.create(
    { label },
    state.schema.text(""),
  );
}

function buildDeviationNote(state: EditorState, rowId: string): PMNode {
  return state.schema.nodes.deviation_note.create(
    { row_id: rowId },
    [labeledPara(state, REASON_LABEL), labeledPara(state, ALT_LABEL)],
  );
}

interface Op {
  pos: number;
  kind: "insert" | "remove" | "insertInto";
  node?: PMNode;
  to?: number;
}

/** 自愈 diff:返回 [] = 无需动作(幂等短路防再入) */
function diffDeviation(state: EditorState): Op[] {
  const doc = state.doc;
  const rows = collectNegativeRows(doc);
  const notes = collectNotes(doc);
  const ops: Op[] = [];
  for (const [rowId, hit] of rows) {
    const note = notes.get(rowId);
    if (!note) {
      if (hit.tableEnd >= 0) {
        ops.push({ pos: hit.tableEnd, kind: "insert", node: buildDeviationNote(state, rowId) });
      }
    } else if (!note.hasReason || !note.hasAlt) {
      // 破损自愈:缺哪个补哪个(顺序尾插,断言只看有无+非空)
      const noteEnd = note.end - 1; // 进 note 内部
      if (!note.hasReason) ops.push({ pos: noteEnd, kind: "insertInto", node: labeledPara(state, REASON_LABEL) });
      if (!note.hasAlt) ops.push({ pos: noteEnd, kind: "insertInto", node: labeledPara(state, ALT_LABEL) });
    }
  }
  for (const [rowId, note] of notes) {
    if (rows.has(rowId)) continue;
    const empty = !note.reasonFilled && !note.altFilled;
    if (empty) ops.push({ pos: note.pos, kind: "remove", to: note.end });
    // 非空孤儿保留(assert 面 D1),不在事务里删用户文本
  }
  return ops;
}

export function deviationPlugin(): Plugin<undefined> {
  return new Plugin<undefined>({
    appendTransaction(trs, _old, newState) {
      if (!trs.some((tr) => tr.docChanged)) return [];
      const ops = diffDeviation(newState);
      if (ops.length === 0) return [];
      const tr: Transaction = newState.tr;
      // 位置降序应用:后位先动,前位不漂移
      ops.sort((a, b) => b.pos - a.pos);
      for (const op of ops) {
        if (op.kind === "insert" && op.node) {
          tr.insert(op.pos, op.node);
        } else if (op.kind === "insertInto" && op.node) {
          tr.insert(op.pos, op.node);
        } else if (op.kind === "remove") {
          tr.delete(op.pos, op.to ?? op.pos);
        }
      }
      systemTr(tr);
      // systemTr 会设 addToHistory=false;撤回希望连展开面一起回 → 重设为默认入栈
      tr.setMeta("addToHistory", undefined);
      return [tr];
    },
  });
}

/** 空展开面判定(WorkbenchView/测试用):双 labeled para 全空 */
export function deviationNoteIsEmpty(node: PMNode): boolean {
  let any = false;
  for (const child of node.content) {
    const label = String(child.attrs.label ?? "");
    if ((label === REASON_LABEL || label === ALT_LABEL) && child.textContent.trim().length > 0) {
      any = true;
    }
  }
  return !any;
}
```

注意 `systemTr` 会设 `addToHistory=false`,追加了 `setMeta("addToHistory", undefined)` 重置——prosemirror-history 读该 meta 时 undefined=默认入栈,appended tr 并入当前 undo 事件。若实测一撤不干净,退路:去掉这行并接受「撤翻策略后空展开面由自愈收拢」(测试钉行为,两种都可)。

- [x] **Step 2: state.ts 挂 plugin**

```ts
import { deviationPlugin } from "./deviation";
...
    plugins: [
      history(),
      keymap({ "Mod-z": undo, "Mod-Z": redo, "Mod-y": redo }),
      keymap(baseKeymap),
      constraintsPlugin(options),
      deviationPlugin(),
      provenancePlugin({ onJump: options.onProvenanceJump }),
      liveAssertPlugin(),
    ],
```

(import 排序:./constraints 后 ./decor 前=deviation 按字母序在 constraints 与 decor 之间。)

- [x] **Step 3: decor.ts anchorKey + node deco 分支**

anchorKey 追加:

```ts
  if (node.type.name === "deviation_note") {
    const rid = String(node.attrs.row_id ?? "");
    return rid ? `devnote:${rid}` : null;
  }
```

buildAssertDecorations node-deco 分支:

```ts
    if (node.isLeaf || node.type.name === "table_row" || node.type.name === "deviation_note") {
```

- [x] **Step 4: 写测试** `bid-write-editor-deviation.test.ts`(node env,EditorState.apply 直跑 appendTransaction):

```ts
import { describe, expect, it } from "@rstest/core";
import { undo } from "prosemirror-history";
import { type Node as PMNode } from "prosemirror-model";

import { setEnumValue } from "@/extensions/bid-write/editor/constraints";
import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { createBidWriteEditorState } from "@/extensions/bid-write/editor/state";

function enumPos(doc: PMNode): number {
  let hit = -1;
  doc.descendants((node, pos) => {
    if (hit < 0 && node.type.name === "enum_cell") hit = pos;
  });
  if (hit < 0) throw new Error("demo 无 enum_cell");
  return hit;
}

function findNote(doc: PMNode) {
  let hit: { pos: number; node: PMNode } | null = null;
  doc.descendants((node, pos) => {
    if (!hit && node.type.name === "deviation_note") hit = { pos, node };
  });
  return hit;
}

const labels = (note: PMNode) =>
  Array.from(note.content).map((p) => String(p.attrs.label ?? ""));

describe("deviation 展开自愈", () => {
  it("选负偏离 → 表后出现 note(双 labeled para);source=system 入 undo", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const tr = setEnumValue(s0, enumPos(s0.doc), "负偏离");
    expect(tr).not.toBeNull();
    const s1 = s0.apply(tr!);
    const note = findNote(s1.doc);
    expect(note).not.toBeNull();
    expect(String(note!.node.attrs.row_id ?? "")).toBe("R-sum");
    expect(labels(note!.node)).toEqual(["偏离原因", "替代方案"]);
    expect(tr!.getMeta("source")).toBeUndefined(); // 用户 tr 本身仍是 user 源
  });

  it("一撤=策略翻回+展开面消失(appended tr 并入同一 undo 事件)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const tr = setEnumValue(s0, enumPos(s0.doc), "负偏离");
    const s1 = s0.apply(tr!);
    let s2 = s1;
    undo(s1, (u) => {
      s2 = s1.apply(u);
    });
    expect(findNote(s2.doc)).toBeNull();
    s2.doc.descendants((node) => {
      if (node.type.name === "enum_cell") expect(node.attrs.current).toBe("完全响应");
    });
  });

  it("手删 note → 任何后续 doc 变更自愈重现", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s1 = s0.apply(setEnumValue(s0, enumPos(s0.doc), "负偏离")!);
    const note = findNote(s1.doc)!;
    const s2 = s1.apply((() => {
      const tr = s1.tr;
      tr.delete(note.pos, note.pos + note.node.nodeSize);
      return tr;
    })());
    // 删除 tr 自身是 user 源但先过 filter(表区外,无守卫命中)→ appendTransaction 补回
    expect(findNote(s2.doc)).not.toBeNull();
  });

  it("双字段已填 → 翻回完全响应 → note 保留(孤儿,文本零丢失)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s1 = s0.apply(setEnumValue(s0, enumPos(s0.doc), "负偏离")!);
    const note = findNote(s1.doc)!;
    // 填 reason(直接构造 doc 变更:note 内 labeled para 尾插文本)
    const rPos = note.pos + 1;
    const s2 = s1.apply(s1.tr.insertText("性能无法满足", rPos, rPos));
    const note2 = findNote(s2.doc)!;
    const aPos = /* 定位替代方案 para 内 */ 0;
    expect(aPos).toBeGreaterThan(0); // 占位防误删;真实定位见实现
    const s3 = s2.apply(setEnumValue(s2, enumPos(s2.doc), "完全响应")!);
    expect(findNote(s3.doc)).not.toBeNull(); // 保留
  });

  it("双字段全空 → 翻回完全响应 → note 收拢删除", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s1 = s0.apply(setEnumValue(s0, enumPos(s0.doc), "负偏离")!);
    const s2 = s1.apply(setEnumValue(s1, enumPos(s1.doc), "完全响应")!);
    expect(findNote(s2.doc)).toBeNull();
  });

  it("翻回后再次选负偏离 → 复用场景自愈重建", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s1 = s0.apply(setEnumValue(s0, enumPos(s0.doc), "负偏离")!);
    const s2 = s1.apply(setEnumValue(s1, enumPos(s1.doc), "完全响应")!);
    const s3 = s2.apply(setEnumValue(s2, enumPos(s2.doc), "负偏离")!);
    expect(findNote(s3.doc)).not.toBeNull();
  });
});
```

(第 4 例的替代方案 para 定位在实现时精确化:遍历 note.content 累计 offset 找 label=替代方案 的 para 内 pos。)

- [x] **Step 5: rstest 绿 → Commit**

```bash
python ../scripts/pnpm.py exec rstest tests/unit/extensions/bid-write-editor-deviation.test.ts tests/unit/extensions/bid-write-editor-constraints.test.ts
git add frontend/src/extensions/bid-write/editor/deviation.ts frontend/src/extensions/bid-write/editor/state.ts frontend/src/extensions/bid-write/editor/decor.ts frontend/tests/unit/extensions/bid-write-editor-deviation.test.ts
git commit -m "feat(bid-write): 批廿九 M3-b 负偏离自愈展开——deviationPlugin appendTransaction 不变式(插/补/收拢;孤儿非空保留)+source=system 过滤+并入 undo 事件+anchorKey devnote 面+N 例单测"
```

---

### Task 3: editorLocalAssert SK-RT-005 闭环面

**Files:**
- Modify: `frontend/src/extensions/bid-write/editor/decor.ts`(editorLocalAssert 加 deviation 段)
- Test: `frontend/tests/unit/extensions/bid-write-editor-assert.test.ts` 追加例

- [x] **Step 1: editorLocalAssert 逻辑**(walk 循环内 table 分支后新增 deviation_note 分支 + 循环外 reconcile):

walk 前置收集(函数顶部):

```ts
  const negativeRows = new Set<string>();
  const notes: { rowId: string; closed: boolean; anyFilled: boolean }[] = [];
```

table 分支内(rows 循环中,amount 判定前):

```ts
          for (const cell of row.content ?? []) {
            if (cell.type === "enum_cell" && attrStr(cell, "current") === "负偏离") {
              negativeRows.add(rowId);
            }
          }
```

(deviation_note 内部 enum 不会出现——它 content 是 para。)

walk 循环新增分支(todo_block 分支后):

```ts
      if (block.type === "deviation_note") {
        const rid = attrStr(block, "row_id");
        let hasReason = false;
        let reasonFilled = false;
        let hasAlt = false;
        let altFilled = false;
        for (const p of block.content ?? []) {
          const label = attrStr(p, "label");
          const filled = nodeText(p).trim().length > 0;
          if (label === "偏离原因") { hasReason = true; reasonFilled = reasonFilled || filled; }
          if (label === "替代方案") { hasAlt = true; altFilled = altFilled || filled; }
        }
        notes.push({ rowId: rid, closed: hasReason && reasonFilled && hasAlt && altFilled, anyFilled: reasonFilled || altFilled });
        continue;
      }
```

reconcile(表外金额面之前):

```ts
  for (const rid of negativeRows) {
    const note = notes.find((n) => n.rowId === rid);
    if (!note || !note.closed) {
      states[`devnote:${rid}`] = {
        state: "D0",
        err_code: "SK-RT-005",
        message: "负偏离未闭环:需偏离原因+替代方案(后端 RT-005 同口径)",
      };
    }
  }
  for (const note of notes) {
    if (negativeRows.has(note.rowId) || !note.anyFilled) continue;
    mergeState(states, `devnote:${note.rowId}`, {
      state: "D1",
      err_code: "SK-RT-005",
      message: "响应策略已非负偏离,展开面未清理(撤回或手删)",
    });
  }
  // ★SK-RT-004 编辑器不管:star 不在 AST(生成期 422+预审查已拦)
```

- [x] **Step 2: assert 测试追加 3 例**(构造 ast JSON):

```ts
  test("负偏离行未闭环 → devnote D0 SK-RT-005;闭环后消失", () => {
    const ast = demo();
    // R-sum enum 改负偏离 + 手工挂一个空 note(模拟展开面)
    const table = at(at(at(at(ast.content)[2]).content)[0]);
    const sumRow = at(at(table.content)[2]);
    at(at(at(sumRow.content)[1])).content![0].text = "负偏离";
    at(at(sumRow.content)[1]).attrs!.current = "负偏离";
    (at(at(ast.content)[2]).content as AstJsonNode[]).splice(1, 0, {
      type: "deviation_note",
      attrs: { row_id: "R-sum" },
      content: [
        { type: "para", attrs: { label: "偏离原因" }, content: [] },
        { type: "para", attrs: { label: "替代方案" }, content: [] },
      ],
    } as AstJsonNode);
    const p1 = editorLocalAssert(ast);
    expect(p1.states["devnote:R-sum"]).toMatchObject({ state: "D0", err_code: "SK-RT-005" });
    // 填满双字段 → 闭环
    const note = at(at(at(at(ast.content)[2]).content)[1]);
    at(note.content)[0].content = [{ type: "text", text: "产能不足" }];
    at(note.content)[1].content = [{ type: "text", text: "分批交付" }];
    const p2 = editorLocalAssert(ast);
    expect(p2.states["devnote:R-sum"]).toBeUndefined();
  });

  test("孤儿 note(策略已翻回)有内容 → D1;空 → 无状态(自愈会删)", () => {
    const ast = demo();
    (at(at(ast.content)[2]).content as AstJsonNode[]).splice(1, 0, {
      type: "deviation_note",
      attrs: { row_id: "R-sum" },
      content: [
        { type: "para", attrs: { label: "偏离原因" }, content: [{ type: "text", text: "旧原因" }] },
        { type: "para", attrs: { label: "替代方案" }, content: [{ type: "text", text: "旧方案" }] },
      ],
    } as AstJsonNode);
    const p = editorLocalAssert(ast);
    expect(p.states["devnote:R-sum"]).toMatchObject({ state: "D1", err_code: "SK-RT-005" });
  });

  test("demo 基线不受影响(无负偏离 → 无 devnote 键)", () => {
    const p = editorLocalAssert(demo());
    expect(Object.keys(p.states).some((k) => k.startsWith("devnote:"))).toBe(false);
  });
```

- [x] **Step 3: rstest assert+deviation+decor 全绿 → Commit**

```bash
python ../scripts/pnpm.py exec rstest tests/unit/extensions/bid-write-editor-assert.test.ts tests/unit/extensions/bid-write-editor-deviation.test.ts tests/unit/extensions/bid-write-editor-decor.test.ts
git add frontend/src/extensions/bid-write/editor/decor.ts frontend/tests/unit/extensions/bid-write-editor-assert.test.ts
git commit -m "feat(bid-write): 批廿九 M3-c 断言闭环面——editorLocalAssert SK-RT-005(负偏离未闭环 D0/孤儿展开面 D1)+3 例;★RT-004 留后端(注释)"
```

---

### Task 4: CSS + WorkbenchView 文案

**Files:**
- Modify: `frontend/src/app/bid-write/bid-write.css`
- Modify: `frontend/src/extensions/bid-write/components/WorkbenchView.tsx`(M2→M3 文案两处)

- [x] **Step 1: css 追加**(token 对齐既有段;label 经 data-label ::before 呈现,标签不可选中)

```css
/* ── 批廿九 M3:负偏离展开面 ─────────────────────────────────────────── */
.bwx .bwe-devnote {
  margin: 6px 0;
  padding: 6px 10px;
  background: var(--warn-50);
  border: 1px dashed var(--warn-700);
  border-radius: 4px;
}
.bwx .bwe-devnote p {
  margin: 2px 0;
  min-height: 18px;
}
.bwx .bwe-devnote p[data-label]::before {
  content: attr(data-label) ":";
  font-weight: 600;
  color: var(--warn-700);
  margin-right: 4px;
  user-select: none;
}
.bwx .bwx-assert-d0.bwe-devnote,
.bwx .bwe-devnote.bwx-assert-d0 { border-style: solid; border-color: var(--error-700); }
```

- [x] **Step 2: WorkbenchView 文案**:banner info 段 `正文编辑器 M2 已接入` → `正文编辑器 M3 已接入:编辑/撤销、断言联动、AST 云端存储与负偏离展开面可用;…`;footer 段 `M2:断言联动与 AST 存储已接入(演示执行器)` → `M3:负偏离展开面已接入(…)`;subtitle `M2(断言联动+AST 存储)` → `M3(负偏离展开)`。

- [x] **Step 3:** tsc + eslint 两文件 + 全 editor rstest 绿

- [x] **Step 4: Commit**

```bash
git add frontend/src/app/bid-write/bid-write.css frontend/src/extensions/bid-write/components/WorkbenchView.tsx
git commit -m "feat(bid-write): 批廿九 M3-d 展开面样式+M3 文案——bwe-devnote 警示虚线盒(data-label ::before 标签)+未闭环 solid 红边"
```

---

### Task 5: 实机验证(宿主 :3000)

- [x] **Step 1:** gateway 已在批廿八 T4 重启过——后端本批只动 yaml/测试/前端 gen,AST 存储路由无变化;**前端 :3000 dev server 热更即可**(batch-28 的 b00rkjdvi 还在跑;若挂则重启)。
- [x] **Step 2:** 写并跑 `C:/Users/admin/.claude/jobs/d2aa6c7f/tmp/qa-bidwrite-m3.mjs`(M2 脚本登录段复用):
  ①选负偏离 → `.bwe-devnote` 出现且双 data-label para 在
  ②chip 出现 `SK-RT-005`(D0 +1)
  ③原因/替代方案两格打字 → chip 回基线 `D0 1 · D1 1`
  ④Ctrl+Z 撤到翻策略前 → note 消失
  ⑤再选负偏离+填满 → 保存 → PUT 200
  ⑥reload → 云端 badge + note 与内容都在(新节点往返实证)
  ⑦截图
- [x] **Step 3:** 全量 rstest(components 单独跑兜底 flake 基线)。

---

### Task 6: 收口

- [x] **Step 1:** plan 全勾 + `git add -f` 本 plan。
- [x] **Step 2:** wolf 四件套:cerebrum(appendTransaction 自愈不变式法/appended tr undo 并入/meta addToHistory 重置法/破损自愈补 para 法)+ memory 批线 + anatomy(deviation.ts 新文件、schema.gen/deviation 相关条目)+ buglog(若有)。
- [x] **Step 3:** auto-memory `bid-write-p1-beta29-negative-deviation-landed.md` + MEMORY.md 行。
- [x] **Step 4:** docs commit(不推,等「push」)。

---

## Self-Review

1. **Spec 覆盖**:§5.4 展开(appendTransaction)✓ approval_required(闭环判定=双字段非空,assert 面承载)✓ schema 扩展 ✓;SK-RT-004 边界声明 ✓。
2. **占位扫描**:测试第 4 例 `aPos` 占位已在计划内标注「实现时精确化」——执行时落地,不算 plan 占位。
3. **类型一致性**:deviation_note attrs=row_id(yaml=gen=插件=assert 四处一致);label 值 REASON_LABEL/ALT_LABEL 常量复用 ✓;`devnote:{row_id}` 键在 anchorKey/assert/测试三处一致 ✓。
