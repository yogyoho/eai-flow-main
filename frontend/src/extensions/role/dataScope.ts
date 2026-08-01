import type { RegistryModule } from "@/extensions/types";

/**
 * 将角色的 data_scopes 解析为按 module 划分的选择（deny-by-default：无条目 = 未选择）。
 *
 * 后端为 deny-by-default：角色的 data_scopes 中若缺少某 module 的 scope id，则对该 module 不授予任何数据权限。
 * 因此这里绝不用「首个 scope」兜底——只有角色 data_scopes 里真实匹配到某 module 的 scope 时，才生成该 module 的条目。
 */
export function resolveDataScopeSelections(
  modules: RegistryModule[],
  roleDataScopes?: string[],
): Record<string, string> {
  return Object.fromEntries(
    (modules || [])
      .filter((m) => m.data_scopes?.length)
      .flatMap((m) => {
        const matched = (roleDataScopes ?? []).find((d) => m.data_scopes.some((s) => s.id === d));
        return matched ? ([[m.key, matched] as [string, string]]) : [];
      }),
  );
}
