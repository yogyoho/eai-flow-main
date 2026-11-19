# 批卅三(工作台可操作性+可发现性)Implementation Plan

> **For agentic workers:** superpowers:executing-plans,逐任务勾 `- [ ]`。

**Goal:** 用户逐项测试反馈五痛点(无引导/只能写文字/表格不能加行/插槽不可编辑不知在哪填)——按序修复:表格行操作 → 锁定段点选指引 → 首次引导条。

**Architecture:** 新 `tableOps.ts`(非价格表加行/删行事务;价格表行结构属报价面,拒绝+提示);BidWriteEditor 工具条加「加行/删行」按钮(选中在表内时生效);点锁定段经 decor meta 出指引通知(插槽值来源=③生成配置+重新生成);WorkbenchView 首次进入引导条(localStorage 记忆已读)。

**Tech Stack:** ProseMirror Transaction / rstest / Playwright

---

### T1 表格行操作(tableOps.ts + 工具条)

**Files:** Create `frontend/src/extensions/bid-write/editor/tableOps.ts`;Modify `components/BidWriteEditor.tsx`(工具条两按钮);Test `frontend/tests/unit/extensions/bid-write-editor-tableops.test.ts`

- [ ] Step 1: tableOps.ts 全文:

```ts
// EAI-CUSTOM 批卅三 T1——表格行操作:加行/删行(用户痛点:表格不能加行)。
// 价格表(table_type=price)拒绝:行结构(金额/合计/加总链)属报价面,由③配置
// 与素材证据驱动,手加行会破坏 SK-PS-003/007/008 断言面。响应表/清单表全支持。
// 新行克隆末行单元格类型与 attrs,content 全空(enum_cell current="" 与空内容
// 满足 M1 不变式 textContent≡current;amount_cell 空内容由用户触发重算/断言提示)。
import { type Transaction } from "prosemirror-state";

export function addRowInSelection(state: {
  selection: { $from: { depth: number; before(d: number): number; after(d: number): number; node(d: number): { type: { name: string }; attrs: Record<string, unknown>; childCount: number; child(i: number): CellLike } } };
  tr: import("prosemirror-state").Transaction;
  schema: { nodes: Record<string, { create(attrs?: Record<string, unknown>, content?: unknown[]): unknown }> };
}): Transaction | null {
  const $from = state.selection.$from;
  for (let d = $from.depth; d > 0; d--) {
    const node = $from.node(d);
    if (node.type.name !== "table") continue;
    if (String(node.attrs.table_type) === "price") return null;
    const lastRow = node.child(node.childCount - 1);
    const cells: unknown[] = [];
    for (let i = 0; i < lastRow.childCount; i++) {
      const cell = lastRow.child(i);
      cells.push(cell.type.create({ ...cell.attrs }, []));
    }
    const row = state.schema.nodes.table_row.create({ row_id: "" }, cells);
    return state.tr.insert($from.after(d), row);
  }
  return null;
}

export function deleteRowInSelection(state: SameShapeAsAbove): Transaction | null {
  const $from = state.selection.$from;
  for (let d = $from.depth; d > 0; d--) {
    const node = $from.node(d);
    if (node.type.name !== "table") continue;
    if (String(node.attrs.table_type) === "price") return null;
    if (node.childCount <= 1) return null; // 保底:不留空表
    const rowPos = $from.before(d + 1);
    const rowSize = $from.node(d + 1).nodeSize;
    return state.tr.delete(rowPos, rowPos + rowSize);
  }
  return null;
}
```

(类型形态执行时对齐 PM 真实类型,用 structural typing;enum_cell create 后 content=[] 与 current="" 满足不变式。)

- [ ] Step 2: BidWriteEditor 工具条(撤销/重做旁)加两按钮:

```tsx
<button type="button" className="tb" title="表格加行(光标在响应表/清单表内;价格表不支持)" onClick={() => dispatchOp(addRowInSelection)}>＋行</button>
<button type="button" className="tb" title="表格删行(光标所在行)" onClick={() => dispatchOp(deleteRowInSelection)}>－行</button>
```

dispatchOp: `const tr = op(view.state); if (tr) view.dispatch(tr);`(内部 try/catch,失败静默;约束 filterTransaction 兜底)。

- [ ] Step 3: golden(表格结构手搭:非价格表加行→行数+1 且新行全空;选中在价格表→null;表外→null;删行→行数-1;单行表删→null):
- [ ] Step 4: rstest 绿 → Commit `feat(bid-write): 批卅三 T1 表格行操作——tableOps 加/删行(价格表拒绝保护报价面)+工具条按钮+golden`

### T2 锁定段点选指引

**Files:** Modify `editor/decor.ts`(provenancePlugin handleClick 内:命中 locked_paragraph → dispatch 既有 decor 通道)、`components/WorkbenchView.tsx`(notice 文案带③跳转)

- [ ] Step 1: handleClick 里:$pos 深度链含 locked_paragraph(且非 provenance 命中)→ dispatch decor 事件带 {guide: "locked"};WorkbenchView 收到后 ed-notice 显示:「锁定模板不可改写;插槽值(采购编号/报价/金额大写)来自招标上下文与报价表——去③生成配置补齐后重新执行生成」+ 跳转链接(writeTaskHref("generate", taskId))。
- [ ] Step 2: Playwright 或 dom 测试:点锁定段 → notice 文案出现且含「③生成配置」。
- [ ] Step 3: Commit `feat(bid-write): 批卅三 T2 锁定段点选指引——插槽值来源可视化+③跳转`

### T3 首次引导条

**Files:** Modify `components/WorkbenchView.tsx`(banner 区顶部)

- [ ] Step 1: 引导条(banner info,localStorage `bw_workbench_guide_read` 未读时显示,关闭按钮写入):

```tsx
{guideShown ? null : (
  <div className="banner info">
    <Info size={15} aria-hidden="true" />
    <span>
      可编辑区域:各节正文文字(点选后直接输入);响应表/清单表光标入表后用工具条「＋行/－行」;
      锁定模板(蓝框)不可改写,插槽值在③生成配置补齐后重新生成;黄色下划线=断言提示,点「查看 AI 建议」看明细。
    </span>
    <button type="button" className="btn btn-sm" onClick={() => { localStorage.setItem("bw_workbench_guide_read", "1"); setGuideShown(true); }}>知道了</button>
  </div>
)}
```

guideShown 初始= `!localStorage.getItem(...)`(useState 惰性初始化,SSR 安全:mount 后再读)。
- [ ] Step 2: dom 测试(首次渲染显示引导条、点「知道了」消失);Commit `feat(bid-write): 批卅三 T3 工作台首次引导条(可编辑区/表格操作/插槽来源三句话)`

### T4 验证收口

- [ ] 全量:typecheck+eslint+bid-write rstest+实机(表格加行真操作+点锁定段指引+引导条);全量 rstest 兜底;plan 全勾+wolf+memory+docs commit。**不推,等「push」。**

## Self-Review
覆盖五痛点:③表格加行(T1)/④⑤插槽来源(T2 指引+重新生成闭环)/①引导(T3)/②格式化工具**明确不做**(正文纯文本是断言面设计,格式噪声会破坏导出投影——诚实边界)。类型:tableOps 事务签名一致。
