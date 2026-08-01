// EAI-CUSTOM: 策略条件/授权 shape 双向转换 —— UI 数组 ⇄ 引擎 dict
// 引擎 (_evaluate_conditions) 存储/评估 conditions={and:[{attr,op,value}]}（op ∈ eq/neq/gt/gte/lt/lte/contains/not_contains/in/not_in），
// grants={permissions:[...]}；UI 编辑用 conditions=[{attribute,operator,value}]、grants=[{permission}]。
// 保存时转引擎 dict，加载时转回 UI 数组 —— 保证 SAVED shape 与引擎一致且编辑器可用。
import type { PolicyCondition, PolicyGrant } from "@/extensions/types";

const UI_TO_ENGINE_OP: Record<string, string> = {
  "=": "eq", "!=": "neq", ">": "gt", "<": "lt", ">=": "gte", "<=": "lte",
  "contains": "contains", "not_contains": "not_contains", "in": "in", "not_in": "not_in",
};
const ENGINE_TO_UI_OP: Record<string, string> = {
  eq: "=", neq: "!=", gt: ">", lt: "<", gte: ">=", lte: "<=",
  contains: "contains", not_contains: "not_contains", in: "in", not_in: "not_in",
};

/** UI 条件数组 → 引擎 dict（空数组 → 空 dict，引擎视为无条件=全量；in/not_in 值按逗号拆成列表） */
export function toEngineConditions(conds: PolicyCondition[]): Record<string, unknown> {
  if (!conds.length) return {};
  return {
    and: conds.map((c) => {
      const op = UI_TO_ENGINE_OP[c.operator] ?? c.operator;
      return {
        attr: c.attribute,
        op,
        value:
          op === "in" || op === "not_in"
            ? String(c.value).split(",").map((s) => s.trim()).filter(Boolean)
            : c.value,
      };
    }),
  };
}

/** 引擎条件 dict → UI 条件数组（兼容旧数据已是数组；or 树 UI 编辑器不支持 → [] + warn，避免静默 allow-all） */
export function toUIConditions(conds: unknown): PolicyCondition[] {
  if (Array.isArray(conds)) return conds as PolicyCondition[];
  if (!conds || typeof conds !== "object") return [];
  const obj = conds as Record<string, unknown>;
  if (!Array.isArray(obj.and)) {
    if (Array.isArray(obj.or)) {
      // EAI-CUSTOM: or 树无法在 UI 行编辑器表达，退回空条件（空=全量）。显式警告，别静默丢条件。
      console.warn("策略条件包含 'or' 树，UI 编辑器不支持，已按空条件处理");
    }
    return [];
  }
  return (obj.and as Array<Record<string, unknown>>).map((c) => ({
    attribute: (c.attr as string) ?? "",
    operator: (ENGINE_TO_UI_OP[c.op as string] ?? (c.op as string)) ?? "=",
    value: Array.isArray(c.value) ? c.value.join(", ") : ((c.value as string) ?? ""),
  }));
}

/** 引擎授权 dict → UI 授权数组（dict={permissions:[...]} 或已是数组都接受；其余 → []） */
export function toGrantArray(g: unknown): PolicyGrant[] {
  if (Array.isArray(g)) return g as PolicyGrant[];
  if (g && typeof g === "object") {
    const perms = (g as { permissions?: unknown }).permissions;
    if (Array.isArray(perms)) {
      return perms.map((p) => ({ permission: String(p) }));
    }
  }
  return [];
}
