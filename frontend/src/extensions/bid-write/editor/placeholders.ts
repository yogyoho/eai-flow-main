// EAI-CUSTOM——正文占位符清单(待填面板数据源):从 AST 提取 placeholder 原子
// 与所在章节,纯函数可 golden。value 非空=已填(演示文档的演示值也算已填,
// 不替用户判断演示值真伪——诚实面与编辑器一致)。
import { normalizeVarLabel } from "./placeholderOps";
import { type AstJsonNode } from "./schema.gen";

export interface AstPlaceholderInfo {
  slotId: string;
  label: string;
  placeholderType: string;
  value: string;
  required: boolean;
  source: string;
  /** 所在章节标题(顶层 section 才记;与左栏目录同源)。 */
  section: string;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function astPlaceholders(
  ast: AstJsonNode | null | undefined,
): AstPlaceholderInfo[] {
  const out: AstPlaceholderInfo[] = [];
  let section = "";
  const walk = (node: AstJsonNode | undefined) => {
    if (!node || typeof node !== "object") return;
    if (node.type === "section") {
      const prev = section;
      section = asString(node.attrs?.title) || section;
      for (const child of node.content ?? []) walk(child);
      section = prev;
      return;
    }
    if (node.type === "placeholder") {
      out.push({
        slotId: asString(node.attrs?.slot_id),
        label: asString(node.attrs?.label),
        placeholderType: asString(node.attrs?.placeholder_type),
        value: asString(node.attrs?.value),
        required: node.attrs?.required !== false,
        source: asString(node.attrs?.source),
        section,
      });
      return;
    }
    for (const child of node.content ?? []) walk(child);
  };
  walk(ast ?? undefined);
  return out;
}

/** 待填=value 空白;required 优先排序,label 次之(面板稳定序)。 */
export function pendingPlaceholders(
  ast: AstJsonNode | null | undefined,
): AstPlaceholderInfo[] {
  return astPlaceholders(ast)
    .filter((item) => item.value.trim() === "")
    .sort((a, b) => {
      if (a.required !== b.required) return a.required ? -1 : 1;
      return a.label.localeCompare(b.label, "zh-Hans-CN");
    });
}

/**
 * 同变量统计(填写对话框「全局替换」勾选面):与目标 slot 同归一化标签
 * 且(同值或未填)的原子总数(含目标自身)。判定规则与 placeholderOps.
 * findVariableHits 严格一致——编辑缓冲与 AST 清单两处口径必须同源。
 */
export function sameVariableInfo(
  ast: AstJsonNode | null | undefined,
  slotId: string,
): { label: string; total: number } {
  const all = astPlaceholders(ast);
  const ref = all.find((item) => item.slotId === slotId);
  if (!ref) return { label: "", total: 0 };
  const refLabel = normalizeVarLabel(ref.label);
  const total = all.filter(
    (item) =>
      normalizeVarLabel(item.label) === refLabel &&
      (item.value === ref.value || item.value === ""),
  ).length;
  return { label: ref.label, total };
}
