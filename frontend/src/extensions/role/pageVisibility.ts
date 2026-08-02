import type { RegistryModule } from "@/extensions/types";

/** 收集所有 registry module 的页面 id。 */
export function allPageIds(modules: RegistryModule[]): string[] {
  return (modules || []).flatMap((m) => (m.pages || []).map((p) => p.id));
}

/** 将角色的 pages 解析为可见页面 id 集合（"*" 或缺失 → 全部可见）。 */
export function resolveVisiblePages(
  modules: RegistryModule[],
  rolePages?: string[],
): Set<string> {
  const ids = allPageIds(modules);
  if (!rolePages || rolePages.length === 0 || rolePages.includes("*")) {
    return new Set(ids);
  }
  return new Set(rolePages.filter((id) => ids.includes(id)));
}

/** 将可见页面集合序列化回 role.pages 的 wire 格式（全选时用 "*"）。 */
export function serializePages(visible: Set<string>, modules: RegistryModule[]): string[] {
  const ids = allPageIds(modules);
  if (ids.length > 0 && ids.every((id) => visible.has(id))) {
    return ["*"];
  }
  return [...visible];
}
