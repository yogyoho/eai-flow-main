// EAI-CUSTOM 批廿七 M1——节点级编辑约束(方案 §5.2/5.3/5.4/5.6):
// locked_paragraph 禁改 / amount_cell 只读 / table_cell qty·unit 来源列只读 /
// enum_cell 禁自由输入(文本必须恒等于 current attr,下拉经 setEnumValue 走合法通道;
// 不变式校验天然放行 undo,不靠 meta 白名单) / todo_block 禁删。
// 系统事务(meta.source=system)放行——审批替换/缺件补录的唯一通道。
import { type Node as PMNode } from "prosemirror-model";
import { type EditorState, Plugin, type Transaction } from "prosemirror-state";
import { createElement } from "react";
import { createRoot, type Root } from "react-dom/client";

import { EnumCellSelect } from "@/extensions/bid-write/editor/EnumCellSelect";

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

/** 占位符点击信息(待填对话框数据源;填值走 fillPlaceholder system 事务)。 */
export interface PlaceholderSelectInfo {
  slotId: string;
  label: string;
  value: string;
  placeholderType: string;
}

export interface PlaceholderViewHandlers {
  onPlaceholderSelect?: (info: PlaceholderSelectInfo) => void;
}

/** attrs 值安全字符串化(unknown 直 String() 会被 no-base-to-string 拦)。 */
function attrStr(value: unknown): string {
  return typeof value === "string" ? value : "";
}

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
        found = {
          code: "enum_cell",
          message: VIOLATIONS.enum_cell,
          pos,
          end: pos + node.nodeSize,
        };
        return false;
      }
    }
    return true;
  });
  return found;
}

interface ConstraintOptions {
  onViolation?: OnViolation;
  onPlaceholderSelect?: (info: PlaceholderSelectInfo) => void;
}

/** enum_cell 内容区内的改动:内容替换/光标插入先放行,由终态一致性校验把关 */
function insideEnumContent(
  step: { from: number; to: number },
  hit: ConstraintViolation,
): boolean {
  if (step.from === step.to)
    return step.from >= hit.pos + 1 && step.from <= hit.end - 1;
  return step.from >= hit.pos + 1 && step.to <= hit.end - 1;
}

/** attr 步(空区间恰在节点边界)是 setNodeMarkup 的形状,放行交给一致性校验 */
function isBoundaryAttrStep(
  step: { from: number; to: number },
  hit: ConstraintViolation,
): boolean {
  return (
    step.from === step.to && (step.from === hit.pos || step.from === hit.end)
  );
}

export function constraintsPlugin(options: ConstraintOptions = {}): Plugin {
  return new Plugin({
    props: {
      // enum_cell 走原生下拉 NodeView(§5.4:禁自由文本)
      nodeViews: bidWriteNodeViews({
        onPlaceholderSelect: options.onPlaceholderSelect,
      }),
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
        // Step 类型未声明 from/to(运行时必有),守卫按区间判定
        const { from, to } = step as unknown as { from: number; to: number };
        const hit = findProtected(doc, from, to);
        if (hit) {
          const exempt =
            hit.code === "enum_cell" &&
            (insideEnumContent({ from, to }, hit) ||
              isBoundaryAttrStep({ from, to }, hit));
          if (!exempt) {
            options.onViolation?.(hit);
            return false;
          }
        }
        // PM 新版 Step.apply 返回 StepResult 包装(doc/failed),非裸 Node
        const result = step.apply(doc);
        if (result.failed || !result.doc) return false;
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
  if (node?.type.name !== "enum_cell") return null;
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

/** 批廿七 M1-b——enum_cell NodeView:td 外壳 + shadcn Select,无 contentDOM(内容不可打字)。
 *  td 外壳保留招标表格的 colspan/rowspan,避免下拉直接挂在 tr 下破坏表格结构。 */
export class EnumCellView {
  dom: HTMLTableCellElement;
  private host: HTMLDivElement;
  private root: Root;
  private view: EnumViewHost;
  private getPos: () => number | undefined;

  constructor(
    node: PMNode,
    view: EnumViewHost,
    getPos: () => number | undefined,
  ) {
    this.dom = document.createElement("td");
    this.dom.className = "bwe-enum";
    this.host = document.createElement("div");
    this.host.className = "bwe-enum-host";
    this.dom.append(this.host);
    this.view = view;
    this.getPos = getPos;
    this.root = createRoot(this.host);
    this.render(node);
    this.applyAttrs(node);
  }

  update(node: PMNode): boolean {
    if (node.type.name !== "enum_cell") return false;
    this.applyAttrs(node);
    this.render(node);
    return true;
  }

  private render(node: PMNode): void {
    this.root.render(
      createElement(EnumCellSelect, {
        values: (node.attrs.enum_values ?? []) as string[],
        value: String(node.attrs.current ?? ""),
        onChange: (next: string) => {
          const pos = this.getPos();
          if (pos == null) return;
          const tr = setEnumValue(this.view.state, pos, next);
          if (tr) this.view.dispatch(tr);
        },
      }),
    );
  }

  private applyAttrs(node: PMNode): void {
    this.dom.setAttribute("colspan", String(node.attrs.col_span ?? 1));
    this.dom.setAttribute("rowspan", String(node.attrs.row_span ?? 1));
  }

  ignoreMutation(): boolean {
    return true;
  }

  stopEvent(): boolean {
    return true;
  }

  destroy(): void {
    // React 18 渲染期同步 unmount 另一 root 会抛 "Attempted to synchronously
    // unmount a root while React was already rendering"(BidWriteEditor 重建视图
    // 时 PM 在 effect cleanup 同步 destroy → root.unmount 撞上当前 commit)。
    // defer 到宏任务:届时宿主 td 已被 PM 摘除,异步卸载 detached root 无副作用。
    setTimeout(() => this.root.unmount());
  }
}

function placeholderText(node: PMNode): string {
  const value = String(node.attrs.value ?? "").trim();
  if (value) return value;
  const label = String(node.attrs.label ?? "").trim();
  if (label) return `（待填：${label}）`;
  const raw = String(node.attrs.raw ?? "").trim();
  return raw || "________";
}

/** 招标格式占位符:行内原子,只读展示;填值走 attrs.value(system 事务)。 */
export class PlaceholderView {
  dom: HTMLSpanElement;

  constructor(node: PMNode, handlers?: PlaceholderViewHandlers) {
    this.dom = document.createElement("span");
    this.dom.className = "bwe-placeholder";
    // 只读原子的用户入口:点击弹出填写面(stopEvent 阻 PM,DOM 监听不受影响)
    this.dom.addEventListener("click", () => {
      const attrs = node.attrs as Record<string, unknown>;
      handlers?.onPlaceholderSelect?.({
        slotId: attrStr(attrs.slot_id),
        label: attrStr(attrs.label),
        value: attrStr(attrs.value),
        placeholderType: attrStr(attrs.placeholder_type),
      });
    });
    this.update(node);
  }

  update(node: PMNode): boolean {
    if (node.type.name !== "placeholder") return false;
    const slot = String(node.attrs.slot_id ?? "");
    const type = String(node.attrs.placeholder_type ?? "");
    const label = String(node.attrs.label ?? "");
    const value = String(node.attrs.value ?? "");
    const source = String(node.attrs.source ?? "");
    this.dom.textContent = placeholderText(node);
    this.dom.dataset.slot = slot;
    this.dom.dataset.type = type;
    this.dom.dataset.label = label;
    this.dom.dataset.value = value;
    this.dom.dataset.source = source;
    this.dom.title = source
      ? `来源：${source}${value ? "" : "（未填）"}`
      : label || type || "招标格式占位符";
    this.dom.setAttribute("aria-label", `占位符：${label || type || slot}`);
    return true;
  }

  ignoreMutation(): boolean {
    return true;
  }

  stopEvent(): boolean {
    return true;
  }
}

export function bidWriteNodeViews(handlers: PlaceholderViewHandlers = {}) {
  return {
    enum_cell: (
      node: PMNode,
      view: EnumViewHost,
      getPos: () => number | undefined,
    ) => new EnumCellView(node, view, getPos),
    placeholder: (node: PMNode) => new PlaceholderView(node, handlers),
  };
}

// ponytail: 全 doc 扫描每个守卫命中一次——演示文档规模 <100 节点,够用;索引化等真实文档出现再加
