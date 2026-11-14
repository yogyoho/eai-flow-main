// EAI-CUSTOM 批廿八 M2——装饰联动层(方案 §5.1/§六):
//  · provenancePlugin:provenance mark → widget 角标 [B-014][M-88];entity_id 空=
//    未登记 broken 红 ⚠(登记实体反查挂后续批);点击标记文本 dispatch meta
//    「provenance:jump」(decor 事务,不进撤销栈)。
//  · liveAssertPlugin:assertion_states 侧信道(meta「assert:apply」)→ D0 红/D1 黄
//    inline/node decoration;绝不写回节点文本;D2/SKIPPED 不渲染(SKIPPED 只进
//    状态栏,不得当作通过——§六降级面)。
//  · editorLocalAssert:本地确定性演示执行器(纯 AST JSON):行 qty×unit=amount
//    (SK-PS-008)/金额格非法(SK-PS-007)/加总=合计(SK-PS-003 D0)/表外金额形文本
//    ≠合计(SK-PS-003 D1,投标函金额只读引用口径)/缺件占位/status_mark 反射/
//    负偏离闭环 SK-RT-005(未闭环 D0@devnote:{row_id};孤儿展开面 D1)。
//    批三十起云端文档由 WorkbenchView 注入后端真执行器(assertRunner 同形),
//    本函数仅服务演示文档/离线演示面,不冒充后端校验通过;全量重建 O(n),依赖图
//    增量留后续性能批;0.005 浮点阈=演示面(内核口径 Decimal 4 位落表 2 位)。
import type { Node as PMNode } from "prosemirror-model";
import { Plugin, PluginKey, type EditorState, type Transaction } from "prosemirror-state";
import { Decoration, DecorationSet, type EditorView } from "prosemirror-view";

import { ALT_LABEL, REASON_LABEL } from "./deviation";
import { type AstJsonNode } from "./schema.gen";
import { decorTr } from "./state";

export interface AssertState {
  state: "D0" | "D1" | "D2";
  err_code?: string;
  message?: string;
}

export interface AssertSkipped {
  code: string;
  count: number;
  reason?: string;
}

export interface AssertPayload {
  states: Record<string, AssertState>;
  skipped: AssertSkipped[];
  run_at: string;
}

export interface AssertSummary {
  d0: number;
  d1: number;
  d2: number;
  skipped: AssertSkipped[];
}

export interface ProvenanceHit {
  clause_id: string;
  entity_id: string;
  anchor: string;
}

export const ASSERT_APPLY_META = "assert:apply";
export const PROVENANCE_JUMP_META = "provenance:jump";

/** 测试面:Decoration.find() 条目的窄化形态(node env 无 DOM,只看 from/to/class) */
export interface DecorationLike {
  from: number;
  to: number;
  type: { attrs?: Record<string, unknown> };
}

const SEVERITY: Record<AssertState["state"], number> = { D0: 3, D1: 2, D2: 1 };

function mergeState(map: Record<string, AssertState>, key: string, next: AssertState): void {
  const cur = map[key];
  if (!cur || SEVERITY[next.state] > SEVERITY[cur.state]) map[key] = next;
}

function anchorKey(node: PMNode, parent: PMNode | null): string | null {
  if (node.type.name === "para") {
    const slot = String(node.attrs.slot_id ?? "");
    return slot ? slot : null;
  }
  if (node.type.name === "locked_paragraph") {
    const tpl = String(node.attrs.template_id ?? "");
    return tpl ? tpl : null;
  }
  if (
    node.type.name === "table_row" &&
    parent?.type.name === "table" &&
    String(parent.attrs.table_type ?? "") === "price"
  ) {
    return `price:${String(node.attrs.row_id ?? "")}`;
  }
  if (
    node.type.name === "table_row" &&
    parent?.type.name === "table" &&
    String(parent.attrs.table_type ?? "") === "response"
  ) {
    return `rt:${String(node.attrs.row_id ?? "")}`;
  }
  if (node.type.name === "todo_block") {
    return `todo:${String(node.attrs.pending_item_id ?? "")}`;
  }
  if (node.type.name === "deviation_note") {
    const rid = String(node.attrs.row_id ?? "");
    return rid ? `devnote:${rid}` : null;
  }
  return null;
}

export function buildAssertDecorations(doc: PMNode, states: Record<string, AssertState>): DecorationSet {
  const decos: Decoration[] = [];
  doc.descendants((node, pos, parent) => {
    if (node.type.name === "text") return;
    const key = anchorKey(node, parent);
    const st = key ? states[key] : undefined;
    if (!st || st.state === "D2") return;
    const cls = st.state === "D0" ? "bwx-assert-d0" : "bwx-assert-d1";
    const title = [st.err_code, st.message].filter(Boolean).join(" · ");
    const spec = { class: cls, "data-err": st.err_code ?? "", title };
    if (node.isLeaf || node.type.name === "table_row" || node.type.name === "deviation_note") {
      decos.push(Decoration.node(pos, pos + node.nodeSize, spec));
    } else if (node.content.size > 0) {
      decos.push(Decoration.inline(pos + 1, pos + 1 + node.content.size, spec));
    } else {
      decos.push(Decoration.node(pos, pos + node.nodeSize, spec));
    }
  });
  return DecorationSet.create(doc, decos);
}

export const liveAssertKey = new PluginKey<DecorationSet>("liveAssert");

export function liveAssertPlugin(): Plugin<DecorationSet> {
  return new Plugin<DecorationSet>({
    key: liveAssertKey,
    state: {
      init: (_config, state) => buildAssertDecorations(state.doc, {}),
      apply(tr, old) {
        const payload = tr.getMeta(ASSERT_APPLY_META) as AssertPayload | undefined;
        if (payload) return buildAssertDecorations(tr.doc, payload.states);
        if (!tr.docChanged) return old;
        return old.map(tr.mapping, tr.doc);
      },
    },
    props: {
      decorations(state: EditorState) {
        return liveAssertKey.getState(state) ?? DecorationSet.empty;
      },
    },
  });
}

/** 纯构造侧信道事务(node 环境可测);applyAssertionStates=构造+dispatch */
export function assertionTr(state: EditorState, payload: AssertPayload): Transaction {
  const tr = decorTr(state.tr);
  tr.setMeta(ASSERT_APPLY_META, payload);
  return tr;
}

export function applyAssertionStates(view: EditorView, payload: AssertPayload): void {
  view.dispatch(assertionTr(view.state, payload));
}

export function summarize(payload: AssertPayload | null): AssertSummary {
  if (!payload) return { d0: 0, d1: 0, d2: 0, skipped: [] };
  let d0 = 0;
  let d1 = 0;
  let d2 = 0;
  for (const st of Object.values(payload.states)) {
    if (st.state === "D0") d0 += 1;
    else if (st.state === "D1") d1 += 1;
    else d2 += 1;
  }
  return { d0, d1, d2, skipped: payload.skipped };
}

// ── provenance(方案 §5.1)─────────────────────────────────────────────────

export function buildProvenanceDecorations(doc: PMNode): DecorationSet {
  const decos: Decoration[] = [];
  doc.descendants((node, pos) => {
    if (node.type.name !== "text" || !node.marks.length) return;
    const mark = node.marks.find((m) => m.type.name === "provenance");
    if (!mark) return;
    const entityId = String(mark.attrs.entity_id ?? "");
    const clauseId = String(mark.attrs.clause_id ?? "");
    const broken = !entityId;
    decos.push(
      Decoration.widget(
        pos + node.nodeSize,
        () => {
          const sup = document.createElement("sup");
          sup.className = broken ? "bwe-prov-badge broken" : "bwe-prov-badge";
          sup.textContent = broken ? `⚠ [${clauseId}]` : `[${clauseId}][${entityId}]`;
          sup.contentEditable = "false";
          return sup;
        },
        { side: 1, marks: [] },
      ),
    );
  });
  return DecorationSet.create(doc, decos);
}

export function provenanceAt(state: EditorState, pos: number): ProvenanceHit | null {
  for (const p of [pos, pos - 1]) {
    const node = state.doc.nodeAt(p);
    const mark = node?.marks.find((m) => m.type.name === "provenance");
    if (mark) {
      return {
        clause_id: String(mark.attrs.clause_id ?? ""),
        entity_id: String(mark.attrs.entity_id ?? ""),
        anchor: String(mark.attrs.anchor ?? ""),
      };
    }
  }
  return null;
}

export const provenanceKey = new PluginKey<DecorationSet>("provenance");

export function provenancePlugin(options: { onJump?: (hit: ProvenanceHit) => void } = {}): Plugin<DecorationSet> {
  return new Plugin<DecorationSet>({
    key: provenanceKey,
    state: {
      init: (_c, state) => buildProvenanceDecorations(state.doc),
      apply(tr, old) {
        if (tr.docChanged) return buildProvenanceDecorations(tr.doc);
        return old;
      },
    },
    props: {
      decorations(state: EditorState) {
        return provenanceKey.getState(state) ?? DecorationSet.empty;
      },
      handleClick(view, pos) {
        const hit = provenanceAt(view.state, pos);
        if (!hit) return false;
        const tr = decorTr(view.state.tr);
        tr.setMeta(PROVENANCE_JUMP_META, hit);
        view.dispatch(tr);
        options.onJump?.(hit);
        return true;
      },
    },
  });
}

// ── 本地确定性演示执行器(纯 AST JSON)────────────────────────────────────

type LooseNode = {
  type?: string;
  attrs?: Record<string, unknown>;
  content?: LooseNode[];
  text?: string;
  marks?: { type?: string; attrs?: Record<string, unknown> }[];
};

const AMOUNT_RE = /^\d{1,3}(?:,\d{3})*\.\d{2}$/;
const NUM_RE = /^\d+(?:\.\d+)?$/;

function parseAmount(text: string): number | null {
  const t = text.trim();
  return AMOUNT_RE.test(t) ? Number(t.replace(/,/g, "")) : null;
}

/** qty/unit 走宽松数字(整数不带千分位);amount 保持严格金额格式 */
function parseNumber(text: string): number | null {
  const t = text.trim().replace(/,/g, "");
  return NUM_RE.test(t) ? Number(t) : null;
}

function nodeText(node: LooseNode | null): string {
  if (!node) return "";
  if (typeof node.text === "string") return node.text;
  return (node.content ?? []).map(nodeText).join("");
}

function cellByRole(row: LooseNode, role: string): LooseNode | null {
  for (const cell of row.content ?? []) {
    const cellRole = attrStr(cell, "col_role") || attrStr(cell, "role");
    if (cellRole === role) return cell;
  }
  return null;
}

/** attrs 值安全取字符串(no-base-to-string:非字符串一律落 fallback) */
function attrStr(node: LooseNode, key: string, fallback = ""): string {
  const v = node.attrs?.[key];
  return typeof v === "string" ? v : fallback;
}

export function editorLocalAssert(ast: AstJsonNode): AssertPayload {
  const root = ast as unknown as LooseNode;
  const states: Record<string, AssertState> = {};
  let total: number | null = null;
  const outsideAmounts: { value: number; slot: string }[] = [];
  // 批廿九 SK-RT-005 闭环面:负偏离行集合 + 展开面快照(price 表范围,演示面同 M2)
  const negativeRows = new Set<string>();
  const devNotes: { rowId: string; closed: boolean; anyFilled: boolean }[] = [];

  // 段落文本金额(表外)+ status_mark 反射;表格与 todo 单独处理
  for (const section of root.content ?? []) {
    for (const block of section.content ?? []) {
      if (block.type === "table" && attrStr(block, "table_type") === "price") {
        const detailAmounts: number[] = [];
        for (const row of block.content ?? []) {
          const rowId = attrStr(row, "row_id");
          for (const cell of row.content ?? []) {
            if (cell.type === "enum_cell" && attrStr(cell, "current") === "负偏离") {
              negativeRows.add(rowId);
            }
          }
          const qty = parseNumber(nodeText(cellByRole(row, "qty")));
          const unit = parseNumber(nodeText(cellByRole(row, "unit")));
          const amountCell = cellByRole(row, "amount");
          const totalCell = cellByRole(row, "total_num");
          const amount = amountCell ? parseAmount(nodeText(amountCell)) : null;
          if (amountCell && amount === null && !totalCell) {
            states[`price:${rowId}`] = { state: "D0", err_code: "SK-PS-007", message: "金额格非法/空(不导出不补)" };
          } else if (qty !== null && unit !== null && amount !== null) {
            detailAmounts.push(amount);
            if (Math.abs(qty * unit - amount) > 0.005) {
              states[`price:${rowId}`] = {
                state: "D0",
                err_code: "SK-PS-008",
                message: `行金额失配:${qty}×${unit}≠${amount}`,
              };
            }
          }
          if (totalCell) {
            const t = parseAmount(nodeText(totalCell));
            if (t !== null) total = t;
            if (detailAmounts.length > 0 && t !== null) {
              const sum = detailAmounts.reduce((a, b) => a + b, 0);
              if (Math.abs(sum - t) > 0.005) {
                states[`price:${rowId}`] = {
                  state: "D0",
                  err_code: "SK-PS-003",
                  message: `加总失配:明细和 ${sum}≠合计 ${t}(明细表唯一事实源)`,
                };
              }
            }
          }
        }
        continue; // 表内文本不进表外金额面
      }
      if (block.type === "todo_block") {
        const key = `todo:${attrStr(block, "pending_item_id")}`;
        states[key] = {
          state: attrStr(block, "level", "D1") === "D0" ? "D0" : "D1",
          err_code: "",
          message: `缺件:${attrStr(block, "missing", "待补")}`,
        };
        continue;
      }
      if (block.type === "deviation_note") {
        const rid = attrStr(block, "row_id");
        let hasReason = false;
        let reasonFilled = false;
        let hasAlt = false;
        let altFilled = false;
        for (const p of block.content ?? []) {
          const label = attrStr(p, "label");
          const filled = nodeText(p).trim().length > 0;
          if (label === REASON_LABEL) {
            hasReason = true;
            reasonFilled = reasonFilled || filled;
          } else if (label === ALT_LABEL) {
            hasAlt = true;
            altFilled = altFilled || filled;
          }
        }
        devNotes.push({
          rowId: rid,
          closed: hasReason && reasonFilled && hasAlt && altFilled,
          anyFilled: reasonFilled || altFilled,
        });
        continue;
      }
      if (block.type !== "para" && block.type !== "locked_paragraph") continue;
      const slot = attrStr(block, "slot_id") || attrStr(block, "template_id");
      if (!slot) continue;
      for (const t of block.content ?? []) {
        const v = parseAmount(String(t.text ?? ""));
        if (v !== null) outsideAmounts.push({ value: v, slot });
        const mark = (t.marks ?? []).find((m) => m.type === "status_mark");
        if (!mark) continue;
        const st = attrStr({ attrs: mark.attrs }, "state", "D1");
        if (st === "D0" || st === "D1") {
          mergeState(states, slot, {
            state: st,
            err_code: attrStr({ attrs: mark.attrs }, "err_code"),
            message: "文中既存标记(生成器/执行器快照)",
          });
        }
      }
    }
  }

  // SK-RT-005 闭环面:负偏离行 ⇔ 展开面双字段非空(与后端 RT-005 同口径)
  for (const rid of negativeRows) {
    const note = devNotes.find((n) => n.rowId === rid);
    if (!note?.closed) {
      states[`devnote:${rid}`] = {
        state: "D0",
        err_code: "SK-RT-005",
        message: "负偏离未闭环:需偏离原因+替代方案",
      };
    }
  }
  for (const note of devNotes) {
    if (negativeRows.has(note.rowId) || !note.anyFilled) continue;
    mergeState(states, `devnote:${note.rowId}`, {
      state: "D1",
      err_code: "SK-RT-005",
      message: "响应策略已非负偏离,展开面未清理(撤回或手删)",
    });
  }
  // ★SK-RT-004 编辑器不管:star 不在 AST(后端生成期 422 + 预审查已拦)

  if (total !== null) {
    for (const { value, slot } of outsideAmounts) {
      if (Math.abs(value - total) > 0.005) {
        mergeState(states, slot, {
          state: "D1",
          err_code: "SK-PS-003",
          message: `金额 ${value} 与报价合计(${total})不一致——派生金额只读引用,请回报价侧修正`,
        });
      }
    }
  }

  return {
    states,
    skipped: [{ code: "SK-PS-006", count: 1, reason: "限价未确认(本地演示执行器不核限价)" }],
    run_at: new Date().toISOString(),
  };
}
