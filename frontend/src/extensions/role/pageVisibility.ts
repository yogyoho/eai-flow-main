import type { RegistryModule } from "@/extensions/types";

/** 收集所有 registry module 的页面 id。 */
export function allPageIds(modules: RegistryModule[]): string[] {
  return (modules || []).flatMap((m) => (m.pages ?? []).map((p) => p.id));
}

/**
 * 将角色的 pages 解析为可见页面 id 集合。
 * - undefined / "*" → 全部可见（新角色默认）
 * - 显式列表 → 该集合（未知 id 剔除）
 * - []（显式空）→ 空集 = 全不可见（与运行时 canPage 一致）
 */
export function resolveVisiblePages(
  modules: RegistryModule[],
  rolePages?: string[],
): Set<string> {
  const ids = allPageIds(modules);
  if (!rolePages || rolePages.includes("*")) {
    return new Set(ids);
  }
  return new Set(rolePages.filter((id) => ids.includes(id)));
}

/** 将可见页面集合序列化回 role.pages 的 wire 格式（全选时用 "*"）。 */
export function serializePages(
  visible: Set<string>,
  modules: RegistryModule[],
): string[] {
  const ids = allPageIds(modules);
  if (ids.length > 0 && ids.every((id) => visible.has(id))) {
    return ["*"];
  }
  return [...visible];
}

/** 模块只有 1 个 page → 面板折叠为两级（跳过中间子页行）。 */
export function isSinglePageModule(mod: RegistryModule): boolean {
  return !!mod.pages && mod.pages.length === 1;
}

/** 模块无可配权限（无 pages 且无直接 permissions）→ 整卡隐藏。 */
export function shouldHideModule(mod: RegistryModule): boolean {
  return !mod.pages || mod.pages.length === 0;
}

/** 可见性纯模块：pages 非空且全部子页无操作 → 只控制子页可见性，无操作网格。 */
export function isVisibilityOnlyModule(mod: RegistryModule): boolean {
  return (
    !!mod.pages &&
    mod.pages.length > 0 &&
    mod.pages.every((p) => p.operations.length === 0)
  );
}
