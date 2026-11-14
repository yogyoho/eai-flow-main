// EAI-CUSTOM 批廿七 M1——节点级编辑约束(方案 §5.2/5.3/5.4/5.6):
// locked_paragraph 禁改 / amount_cell 只读 / table_cell qty·unit 来源列只读 /
// enum_cell 禁自由输入(文本必须恒等于 current attr,下拉经 setEnumValue 走合法通道;
// 不变式校验天然放行 undo,不靠 meta 白名单) / todo_block 禁删。
// 系统事务(meta.source=system)放行——审批替换/缺件补录的唯一通道。
import { type Node as PMNode } from "prosemirror-model";
import { type EditorState, Plugin, type Transaction } from "prosemirror-state";

export interface ConstraintViolation {
  code:
    | "locked_paragraph"
    | "amount_cell"
    | "readonly_source_cell"
    | "enum_cell"
    | "todo_block";
  message: string;
  pos: number;
  /** nodeEnd=pos+nodeSize;内部用于 enum 内容区判定 */
  end: number;
}

export type OnViolation = (violation: ConstraintViolation) => void;

const VIOLATIONS: Record<ConstraintViolation["code"], string> = {
  locked_paragraph: "固定法律条款不可改写（关联 SK-BL-007）",
  amount_cell: "金额由计算内核生成，请在「报价输入」中修改单价",
  readonly_source_cell: "来源列只读（SK-PS-002）：数量/单价请在解析确认侧维护",
  enum_cell: "响应策略请用下拉选择",
  todo_block: "缺件占位不可删除，请走补录流程",
};

/** §5.6 只读来源列(清单数量/单价不允许在结果侧改,SK-PS-002) */
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
      return READONLY_CELL_ROLES.has(String(node.attrs.col_role))
        ? "readonly_source_cell"
        : null;
    default:
      return null;
  }
}

/** [from,to) 与 [pos,end) 相交;空区间(光标)仅严格落在内部才算命中 */
function overlaps(from: number, to: number, pos: number, end: number): boolean {
  if (from === to) return from > pos && from < end;
  return from < end && to > pos;
}

/** 找覆盖 [from,to) 的受保护节点;未命中返回 null */
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
      found = { code, message: VIOLATIONS[code], pos, end };
      return false;
    }
    return true;
  });
  return found;
}

function findEnumMismatch(doc: PMNode): ConstraintViolation | null {
  let found: ConstraintViolation | null = null;
  doc.descendants((node, pos) => {
    if (found) return false;
    if (node.type.name === "enum_cell") {
      const current = String(node.attrs.current ?? "");
      if (node.textContent !== current) {
        found = { code: "enum_cell", message: VIOLATIONS.enum_cell, pos, end: pos + node.nodeSize };
        return false;
      }
    }
    return true;
  });
  return found;
}

interface ConstraintOptions {
  onViolation?: OnViolation;
}

/** enum_cell 内容区内的改动:内容替换/光标插入先放行,由终态一致性校验把关 */
function insideEnumContent(step: { from: number; to: number }, hit: ConstraintViolation): boolean {
  if (step.from === step.to) return step.from >= hit.pos + 1 && step.from <= hit.end - 1;
  return step.from >= hit.pos + 1 && step.to <= hit.end - 1;
}

/** attr 步(空区间恰在节点边界)是 setNodeMarkup 的形状,放行交给一致性校验 */
function isBoundaryAttrStep(step: { from: number; to: number }, hit: ConstraintViolation): boolean {
  return step.from === step.to && (step.from === hit.pos || step.from === hit.end);
}

export function constraintsPlugin(options: ConstraintOptions = {}): Plugin {
  return new Plugin({
    props: {
      // 输入前置拦截:即时反馈,不产生被拒事务
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
      // 事务分层约定见 state.ts(meta.source=system 才放行;decor 无 docChanged 自然通过)
      if (tr.getMeta("source") === "system") return true;
      let doc = state.doc;
      for (const step of tr.steps) {
        const hit = findProtected(doc, step.from, step.to);
        if (hit) {
          const exempt =
            hit.code === "enum_cell" &&
            (insideEnumContent(step, hit) || isBoundaryAttrStep(step, hit));
          if (!exempt) {
            options.onViolation?.(hit);
            return false;
          }
        }
        // PM 新版 Step.apply 返回 StepResult 包装(doc/failed),非裸 Node
        const result = step.apply(doc);
        if (result.failed) return false;
        doc = result.doc;
      }
      // §5.4 不变式:enum_cell 文本必须等于 current attr(setEnumValue/undo 自洽通过)
      const enumHit = findEnumMismatch(doc);
      if (enumHit) {
        options.onViolation?.(enumHit);
        return false;
      }
      return true;
    },
  });
}

/** §5.4 合法通道:current attr + 文本内容同改,一事务,user 源可撤销。
    注意用 setNodeAttribute(AttrStep,零区间)而非 setNodeMarkup——后者产生
    ReplaceAroundStep 全节点跨度,会被自家守卫拒绝。 */
export function setEnumValue(
  state: EditorState,
  pos: number,
  value: string,
): Transaction | null {
  const node = state.doc.nodeAt(pos);
  if (!node || node.type.name !== "enum_cell") return null;
  const values = (node.attrs.enum_values ?? []) as string[];
  if (!values.includes(value)) return null;
  const tr = state.tr;
  tr.setNodeAttribute(pos, "current", value);
  const innerFrom = pos + 1;
  const innerTo = pos + 1 + node.content.size;
  tr.replaceWith(innerFrom, innerTo, state.schema.text(value));
  return tr;
}

export type EnumViewHost = {
  state: EditorState;
  dispatch: (tr: Transaction) => void;
};

/** 批廿七 M1-b——enum_cell NodeView:原生 <select>,无 contentDOM(内容不可打字) */
export class EnumCellView {
  dom: HTMLSelectElement;

  constructor(node: PMNode, view: EnumViewHost, getPos: () => number | undefined) {
    this.dom = document.createElement("select");
    this.dom.className = "bwe-enum-select";
    this.dom.setAttribute("aria-label", "响应策略");
    for (const v of (node.attrs.enum_values ?? []) as string[]) {
      this.dom.append(new Option(v, v));
    }
    this.dom.value = String(node.attrs.current ?? "");
    this.dom.onchange = () => {
      const pos = getPos();
      if (pos == null) return;
      const tr = setEnumValue(view.state, pos, this.dom.value);
      if (tr) view.dispatch(tr);
    };
  }

  update(node: PMNode): boolean {
    if (node.type.name !== "enum_cell") return false;
    this.dom.value = String(node.attrs.current ?? "");
    return true;
  }

  ignoreMutation(): boolean {
    return true;
  }

  stopEvent(): boolean {
    return true;
  }
}

export function bidWriteNodeViews() {
  return {
    enum_cell: (node: PMNode, view: EnumViewHost, getPos: () => number | undefined) =>
      new EnumCellView(node, view, getPos),
  };
}

// ponytail: 全 doc 扫描每个守卫命中一次——演示文档规模 <100 节点,够用;索引化等真实文档出现再加
