# bid_write 批廿七：M1 编辑约束（filterTransaction 三硬约束 + enumCell 下拉）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 编辑器节点级拦截非法编辑：locked_paragraph 禁改、amount_cell 只读、table_cell qty/unit 来源列只读、enum_cell 禁自由输入（下拉合法通道）、todo_block 禁删；系统事务放行；违规即时提示。

**Architecture:** 单个 constraints Plugin（一次 filterTransaction 遍历 + handleTextInput 前置拦截），protected 判定按节点类型/attrs；enum_cell 走 NodeView `<select>`（原生控件）+ `setEnumValue` 命令（meta `bidWrite.enumCell:set` 放行通道，user 源可撤销）。无 yaml/schema 改动（M0 attrs 已含 readonly/col_role/enum_values）。

**Tech Stack:** prosemirror-state/model（已装）、React 19、rstest（node env，EditorState 无 DOM 可测）。

**明确不做（M1 诚实面）：**
- 负偏离展开必填子节点（需 schema 扩展，M2）；computed_expr 重算内核（后端/生成配置页联动，后续批）
- transformPasted 粘贴剥离（paste=ReplaceStep 已被 filter 拦截并提示，剥离是优化非门禁）
- handleKeyDown 删除键拦截（filter 已拦 resulting tr）；改写申请审批流（后端，M2+）
- NodeView 只做 enum_cell 一个；amount/locked 视觉沿用 M0 CSS

---

### Task 1: constraints.ts 核心过滤 + 单测

**Files:**
- Create: `frontend/src/extensions/bid-write/editor/constraints.ts`
- Test: `frontend/tests/unit/extensions/bid-write-editor-constraints.test.ts`

- [x] **Step 1: 写失败测试（10 例）**

```ts
import { describe, expect, it } from "@rstest/core";
import { EditorState, TextSelection, type Transaction } from "prosemirror-state";

import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { createBidWriteEditorState, systemTr } from "@/extensions/bid-write/editor/state";
import {
  ENUM_SET_META,
  findProtected,
  setEnumValue,
} from "@/extensions/bid-write/editor/constraints";

/** 定位演示文档中某文本首次出现所在的 (pos, node 类型) */
function locate(state: EditorState, needle: string): { pos: number; parent: string } {
  let hit = { pos: -1, parent: "" };
  state.doc.descendants((node, pos) => {
    if (hit.pos >= 0) return false;
    if (node.isText && (node.text ?? "").includes(needle)) {
      const $p = state.doc.resolve(pos);
      hit = { pos: pos, parent: $p.node($p.depth).type.name };
    }
    return true;
  });
  if (hit.pos < 0) throw new Error(`not found: ${needle}`);
  return hit;
}

/** 在包含 needle 的文本节点内插入 text（默认 user 源） */
function insertAt(state: EditorState, needle: string, text: string): Transaction {
  const { pos } = locate(state, needle);
  const tr = state.tr;
  tr.setSelection(TextSelection.create(tr.doc, pos));
  tr.insertText(text);
  return tr;
}

describe("M1 约束过滤(方案 §5.2/5.3/5.4/5.6)", () => {
  it("普通 para 编辑放行", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(insertAt(s0, "根据贵方招标文件", "X"));
    expect(s1).not.toBe(s0);
  });

  it("locked_paragraph 禁改(§5.2)", () => {
    const violations: string[] = [];
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {
      onViolation: (m) => violations.push(m),
    });
    const s1 = s0.apply(insertAt(s0, "本投标函自开标之日起", "X"));
    expect(s1).toBe(s0);
    expect(violations[0]).toContain("SK-BL-007");
  });

  it("amount_cell 只读(§5.3)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(insertAt(s0, "800,000.00", "X"));
    expect(s1).toBe(s0);
  });

  it("table_cell qty/unit 来源列只读(§5.6 SK-PS-002)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    expect(s0.apply(insertAt(s0, "200,000.00", "X"))).toBe(s0); // unit
    expect(s0.apply(insertAt(s0, "安装调试", "X"))).toBe(s0); // qty=1 行 name? 注意:"安装调试"是 name 列
  });

  it("table_cell name 列可编辑(对照)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(insertAt(s0, "设备 A", "改"));
    expect(s1).not.toBe(s0);
  });

  it("enum_cell 禁自由输入(§5.4)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(insertAt(s0, "完全响应", "X"));
    expect(s1).toBe(s0);
  });

  it("setEnumValue 合法通道:attr+文本同改,可撤销(§5.4)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const { pos } = locate(s0, "完全响应");
    const tr = setEnumValue(s0, pos - 1, "正偏离"); // nodeAt 需父坐标
    expect(tr).not.toBeNull();
    const s1 = s0.apply(tr as Transaction);
    expect(s1).not.toBe(s0);
    const text = s1.doc.textBetween(0, s1.doc.content.size, "\n", "");
    expect(text).toContain("正偏离");
    expect(text).not.toContain("完全响应");
    expect((tr as Transaction).getMeta(ENUM_SET_META)).toBeTruthy();
  });

  it("todo_block 禁删", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    let todoPos = -1;
    s0.doc.descendants((node, pos) => {
      if (node.type.name === "todo_block") todoPos = pos;
      return true;
    });
    const tr = s0.tr;
    tr.delete(todoPos - 1, todoPos + s0.doc.nodeAt(todoPos - 1)!.nodeSize + 1);
    expect(s0.apply(tr)).toBe(s0);
  });

  it("selection-only 事务放行(docChanged=false)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const tr = s0.tr;
    tr.setSelection(TextSelection.create(s0.doc, 1));
    expect(s0.apply(tr)).not.toBe(s0);
  });

  it("system 事务放行(§5.2 审批替换通道)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(systemTr(insertAt(s0, "本投标函自开标之日起", "X")));
    expect(s1).not.toBe(s0);
  });

  it("findProtected 返回违规码", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const { pos } = locate(s0, "800,000.00");
    expect(findProtected(s0.doc, pos, pos)?.code).toBe("amount_cell");
    expect(findProtected(s0.doc, 1, 1)).toBeNull();
  });
});
```

注意两处测试锚点按实际 demo 结构校准（qty 行 name 判定：R-2 的 name 是「安装调试」，qty 是「1」——`insertAt(s0, "安装调试")` 命中 name 列，应放行；qty「1」文本太短易误命中，改用定位 col_role 断言）。若定位歧义，改写 helper 按 col_role 找 cell 再取其内部 pos。

- [x] **Step 2: 实现 constraints.ts**

```ts
// EAI-CUSTOM 批廿七 M1——节点级编辑约束(方案 §5.2/5.3/5.4/5.6):
// locked_paragraph 禁改 / amount_cell 只读 / table_cell qty·unit 来源列只读 /
// enum_cell 禁自由输入(下拉经 meta 放行) / todo_block 禁删。
// 系统事务(meta.source=system)放行——审批替换/缺件补录的唯一通道。
import { type Node as PMNode } from "prosemirror-model";
import { type EditorState, type Transaction } from "prosemirror-state";

export const ENUM_SET_META = "bidWrite.enumCell:set";

export interface ConstraintViolation {
  code:
    | "locked_paragraph"
    | "amount_cell"
    | "readonly_source_cell"
    | "enum_cell"
    | "todo_block";
  message: string;
  pos: number;
}

export type OnViolation = (violation: ConstraintViolation) => void;

const VIOLATIONS: Record<ConstraintViolation["code"], string> = {
  locked_paragraph: "固定法律条款不可改写（关联 SK-BL-007）",
  amount_cell: "金额由计算内核生成，请在「报价输入」中修改单价",
  readonly_source_cell: "来源列只读（SK-PS-002）：数量/单价请在解析确认侧维护",
  enum_cell: "响应策略请用下拉选择",
  todo_block: "缺件占位不可删除，请走补录流程",
};

/** 只读来源列角色(§5.6:清单来源列不允许在结果侧改) */
const READONLY_CELL_ROLES = new Set(["qty", "unit"]);

function guardCode(node: PMNode): ConstraintViolation["code"] | null {
  switch (node.type.name) {
    case "locked_paragraph":
      return "locked_paragraph";
    case "amount_cell":
      return "amount_cell";
    case "enum_cell":
      return "enum_cell";
    case "todo_block":
      return "todo_block";
    case "table_cell":
      return READONLY_CELL_ROLES.has(node.attrs.col_role)
        ? "readonly_source_cell"
        : null;
    default:
      return null;
  }
}

/** [from,to) 与受保护节点 [pos,pos+nodeSize) 相交(排除边界空插入) */
function overlaps(
  from: number,
  to: number,
  pos: number,
  end: number,
): boolean {
  if (from >= to && from !== to) return false;
  const empty = from === to;
  if (empty) return from > pos && from < end;
  return from < end && to > pos;
}

/** 在 doc 中找覆盖 [from,to) 的受保护节点;空区间按插入点判定 */
export function findProtected(
  doc: PMNode,
  from: number,
  to: number,
): ConstraintViolation | null {
  let found: ConstraintViolation | null = null;
  doc.descendants((node, pos) => {
    if (found) return false;
    const code = guardCode(node);
    if (!code) return true;
    const end = pos + node.nodeSize;
    if (overlaps(from, to, pos, end)) {
      found = { code, message: VIOLATIONS[code], pos };
      return false;
    }
    return true;
  });
  return found;
}

interface ConstraintOptions {
  onViolation?: OnViolation;
}

export function constraintsPlugin(options: ConstraintOptions = {}) {
  return {
    props: {
      handleTextInput(view, from, to) {
        const hit = findProtected(view.state.doc, from, to);
        if (hit) {
          options.onViolation?.(hit);
          return true;
        }
        return false;
      },
    },
    filterTransaction(tr, state) {
      if (!tr.docChanged) return true;
      if (tr.getMeta("source") === "system") return true;
      let doc = state.doc;
      for (const step of tr.steps) {
        if (tr.getMeta(ENUM_SET_META)) {
          // 枚举合法通道:仅豁免 enum_cell 守卫,其余守卫照常
          const hit = findProtectedExcept(doc, step.from, step.to, "enum_cell");
          if (hit) {
            options.onViolation?.(hit);
            return false;
          }
        } else {
          const hit = findProtected(doc, step.from, step.to);
          if (hit) {
            options.onViolation?.(hit);
            return false;
          }
        }
        doc = step.apply(doc);
      }
      return true;
    },
  };
}

function findProtectedExcept(
  doc: PMNode,
  from: number,
  to: number,
  except: ConstraintViolation["code"],
): ConstraintViolation | null {
  const hit = findProtected(doc, from, to);
  return hit && hit.code !== except ? hit : null;
}

/** §5.4 合法通道:current attr + 文本内容同改,一事务,user 源可撤销 */
export function setEnumValue(
  state: EditorState,
  pos: number,
  value: string,
): Transaction | null {
  const node = state.doc.nodeAt(pos);
  if (!node || node.type.name !== "enum_cell") return null;
  const values: string[] = node.attrs.enum_values ?? [];
  if (!values.includes(value)) return null;
  const tr = state.tr;
  tr.setNodeMarkup(pos, undefined, { ...node.attrs, current: value });
  const innerFrom = pos + 1;
  const innerTo = pos + 1 + node.content.size;
  tr.replaceWith(innerFrom, innerTo, state.schema.text(value));
  tr.setMeta(ENUM_SET_META, { pos, value });
  return tr;
}
```

- [x] **Step 3: 跑测试绿**

Run: `cd frontend && python ../scripts/pnpm.py exec rstest tests/unit/extensions/bid-write-editor-constraints.test.ts`
Expected: 全绿（守卫命中即返回旧 state；注意 `s1).toBe(s0)` 断言依赖 PM filterTransaction 拒绝时返回原 state）。

- [x] **Step 4: 提交**

```bash
git add frontend/src/extensions/bid-write/editor/constraints.ts frontend/tests/unit/extensions/bid-write-editor-constraints.test.ts
git commit -m "feat(bid-write): 批廿七 M1-a——constraints.ts 节点级编辑约束(filterTransaction:lockedPara 禁改/amount 只读/qty·unit 来源列只读 SK-PS-002/enum 禁自由输入/todo 禁删;system 事务放行;setEnumValue 合法通道 user 源可撤销)+11 例单测"
```

---

### Task 2: enum_cell 下拉 NodeView + 编辑器接线

**Files:**
- Modify: `frontend/src/extensions/bid-write/editor/constraints.ts`（追加 EnumCellView + nodeViews 导出）
- Modify: `frontend/src/extensions/bid-write/editor/state.ts`（createBidWriteEditorState 接 options、挂 constraints+nodeViews）
- Modify: `frontend/src/extensions/bid-write/editor/BidWriteEditor.tsx`（透传 onViolation）
- Test: 追加到 `frontend/tests/unit/extensions/bid-write-editor-constraints.test.ts`

- [x] **Step 1: 追加失败测试（enum 命令可撤销 + 守卫联动）**

```ts
// 追加 describe:
describe("enum 下拉通道接线(§5.4)", () => {
  it("undo 可撤销枚举切换且守卫不拦 undo", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const { pos } = locate(s0, "完全响应");
    const tr = setEnumValue(s0, pos - 1, "负偏离");
    const s1 = s0.apply(tr as Transaction);
    expect(undo(s1, undefined)).toBe(true);
    let captured: Transaction | null = null;
    const s2 = s1.apply(
      (() => {
        let c: Transaction | null = null;
        undo(s1, (t) => { c = t; });
        return c as unknown as Transaction;
      })(),
    );
    expect(s2.doc.textBetween(0, s2.doc.content.size, "\n", "")).toContain("完全响应");
  });
});
```

- [x] **Step 2: 实现 EnumCellView（NodeView，原生 select）**

constraints.ts 追加：

```ts
/** §5.4 NodeView:原生 <select>(禁自由文本);内容不进 DOM(模型仍在,序列化不损) */
export class EnumCellView {
  dom: HTMLSelectElement;

  constructor(
    node: PMNode,
    view: { state: EditorState; dispatch: (tr: Transaction) => void },
    getPos: () => number | undefined,
  ) {
    this.dom = document.createElement("select");
    this.dom.className = "bwe-enum-select";
    this.dom.setAttribute("aria-label", "响应策略");
    for (const v of (node.attrs.enum_values ?? []) as string[]) {
      this.dom.append(new Option(v, v));
    }
    this.dom.value = (node.attrs.current as string) ?? "";
    this.dom.onchange = () => {
      const pos = getPos();
      if (pos == null) return;
      const tr = setEnumValue(view.state, pos, this.dom.value);
      if (tr) view.dispatch(tr);
    };
  }

  update(node: PMNode): boolean {
    if (node.type.name !== "enum_cell") return false;
    this.dom.value = (node.attrs.current as string) ?? "";
    return true;
  }

  ignoreMutation(): boolean {
    return true;
  }

  stopEvent(): boolean {
    return true; // select 交互不进 PM 事务流
  }
}

export function bidWriteNodeViews() {
  return {
    enum_cell: (
      node: PMNode,
      view: Parameters<ConstructorParameters<typeof EnumCellView>[1]>[0],
      getPos: ConstructorParameters<typeof EnumCellView>[2],
    ) => new EnumCellView(node, view, getPos),
  };
}
```

- [x] **Step 3: state.ts 接线**

```ts
// createBidWriteEditorState 签名改为:
export function createBidWriteEditorState(
  ast: AstJsonNode,
  options: { onViolation?: OnViolation } = {},
): EditorState {
  return EditorState.create({
    doc: hydrateAst(ast),
    plugins: [
      history(),
      keymap({ "Mod-z": undo, "Mod-Z": redo, "Mod-y": redo }),
      keymap(baseKeymap),
      new Plugin({
        props: { nodeViews: bidWriteNodeViews() },
        ...constraintsPlugin(options),
      }),
    ],
  });
}
```

（constraintsPlugin 返回 props/filterTransaction 平铺进同一 Plugin；import { Plugin } from "prosemirror-state"。）

- [x] **Step 4: BidWriteEditor 透传 onViolation**

props 加 `onViolation?: (message: string) => void;`，useEffect 内
`createBidWriteEditorState(initialAst, { onViolation })`，依赖数组加 `onViolation`（父级 useCallback 稳定）。

- [x] **Step 5: 跑全部编辑器测试绿**

Run: `python ../scripts/pnpm.py exec rstest tests/unit/extensions/bid-write-editor-constraints.test.ts tests/unit/extensions/bid-write-editor-history.test.ts tests/unit/extensions/bid-write-editor-roundtrip.test.ts tests/unit/extensions/bid-write-editor-schema.test.ts`
Expected: 全绿（history 测试的系统/装饰事务不受新守卫影响：system 放行；decor tr 无 docChanged 放行）。

- [x] **Step 6: 提交**

```bash
git add frontend/src/extensions/bid-write/editor/constraints.ts frontend/src/extensions/bid-write/editor/state.ts frontend/src/extensions/bid-write/editor/BidWriteEditor.tsx frontend/tests/unit/extensions/bid-write-editor-constraints.test.ts
git commit -m "feat(bid-write): 批廿七 M1-b——enum_cell 原生 select NodeView(禁自由文本;setEnumValue 通道 dispatch;stopEvent/ignoreMutation)+state.ts 挂 constraints plugin+BidWriteEditor 透传 onViolation"
```

---

### Task 3: WorkbenchView 违规提示 + CSS

**Files:**
- Modify: `frontend/src/extensions/bid-write/components/WorkbenchView.tsx`
- Modify: `frontend/src/app/bid-write/bid-write.css`（追加 .ed-notice / .bwe-enum-select）

- [x] **Step 1: WorkbenchView 挂 onViolation → 3s 自动消退提示**

```tsx
const [violation, setViolation] = useState<string | null>(null);
const violationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
const handleViolation = useCallback((v: { message: string }) => {
  setViolation(v.message);
  if (violationTimer.current) clearTimeout(violationTimer.current);
  violationTimer.current = setTimeout(() => setViolation(null), 3000);
}, []);
useEffect(() => () => {
  if (violationTimer.current) clearTimeout(violationTimer.current);
}, []);

// handleDocChange 旁:
const editorOnViolation = handleViolation;

// BidWriteEditor JSX 加:
onViolation={editorOnViolation}

// ed-toolbar 后、doc-body 内加:
{violation ? (
  <div className="ed-notice" role="status">
    {violation}
  </div>
) : null}
```

- [x] **Step 2: CSS（token 化，追加到 bwe 区块尾）**

```css
.bwx .ed-notice {
  margin-top: 8px;
  border: 1px solid var(--warn-700);
  border-radius: 6px;
  background: var(--warn-50);
  padding: 6px 12px;
  font-size: 13px;
  color: var(--warn-700);
}
.bwx .bwe-enum-select {
  border: 1px solid var(--hairline);
  border-radius: 4px;
  background: transparent;
  color: var(--main-600);
  font-size: 13px;
  padding: 2px 6px;
}
```

- [x] **Step 3: lint + tsc + 全量编辑器测试**

Run: `python ../scripts/pnpm.py exec eslint src/extensions/bid-write --fix && python ../scripts/pnpm.py exec tsc --noEmit`（仅允许 pre-existing password-forms 3 错）+ rstest 四件套。
Expected: 全绿。

- [x] **Step 4: 提交**

```bash
git add frontend/src/extensions/bid-write/components/WorkbenchView.tsx frontend/src/app/bid-write/bid-write.css
git commit -m "feat(bid-write): 批廿七 M1-c——WorkbenchView 违规提示(3s 自动消退 role=status)+ed-notice/bwe-enum-select token 化样式"
```

---

### Task 4: 容器重启 + 浏览器实机验证

**Files:** 无代码改动（验证脚本在 job tmp）

- [ ] **Step 1: 重启前端容器**（无依赖变更，restart 即可，勿重建镜像）

```bash
docker compose -p eai-docker restart frontend
```

- [ ] **Step 2: 浏览器验证（扩展 qa-bidwrite-editor.mjs）**

断言清单：
1. 点进 amount_cell (800,000.00) 打字 → 无变化 + ed-notice「金额由计算内核生成…」出现
2. 点进 locked 段打字 → notice「SK-BL-007」
3. 点 qty cell「4」打字 → notice「SK-PS-002」
4. name cell「设备 A」打字 → 正常进入（无 notice）
5. enum 下拉选「正偏离」→ 单元格文本变「正偏离」，Ctrl+Z 撤回「完全响应」
6. 保存 → statusbar 保存时间刷新
（登录流程沿用已验证路径：/login networkidle+15s+真实键入；localhost 经 127.0.0.1 访问）

- [ ] **Step 3: 全量前端 rstest 回归**

Run: `python ../scripts/pnpm.py exec rstest`
Expected: 仅 pre-existing task-form-dialog 2 例隔离性 flake（单跑绿）。

---

### Task 5: wolf/记忆收口

- [ ] **Step 1: .wolf 记账**（memory/anatomy/cerebrum/buglog 如有）
- [ ] **Step 2: plan 全勾 + 提交**（`git add -f` plan；.wolf 四件）

```bash
git add -f docs/superpowers/plans/2026-11-14-bid-write-p1-beta27-editor-m1-constraints-plan.md
git add .wolf/memory.md .wolf/anatomy.md .wolf/cerebrum.md .wolf/buglog.json
git commit -m "docs(bid-write): 批廿七收口——M1 约束落地全勾+wolf 三件套"
```

- [ ] **Step 3: auto-memory 批廿七条目 + MEMORY.md 索引**（不推，等「push」）

**NEXT:** 批廿八 = M2 联动（provenanceDecor/statusDecor/liveAssert 侧信道 + 后端 AST 存储 GET/PUT + 负偏离展开 schema 扩展）。
