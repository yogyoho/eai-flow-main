"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Search, Plus, Shield, Lock, Pencil, Trash2, Users, X,
  ChevronDown, Brain, Database, Puzzle, Wrench,
  Settings, Key, Loader2, FolderKanban, ClipboardCheck, FileText, Workflow,
  LayoutGrid, List, KeyRound, Filter, Eye, EyeOff, GripVertical,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Input } from "@/components/ui/input";
import { PageLoadingOverlay } from "@/components/ui/page-loading-overlay";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { permissionsApi, roleApi, userApi } from "@/extensions/api";
import type {
  Role, CreateRoleRequest, UpdateRoleRequest, User,
  RegistryModule, PermissionItem, DataScopeItem,
  PolicyItem, PolicyCondition, PolicyGrant,
} from "@/extensions/types";
import { cn } from "@/lib/utils";

/* ── Fallback permission categories (used when registry not loaded) ── */
const PERMISSION_CATEGORIES = [
  {
    name: "模型访问控制", icon: Brain,
    permissions: [
      { key: "model:read", label: "查看模型" },
      { key: "model:create", label: "创建模型配置" },
      { key: "model:update", label: "更新模型配置" },
      { key: "model:delete", label: "删除模型配置" },
    ],
  },
  {
    name: "知识库与数据", icon: Database,
    permissions: [
      { key: "kb:read", label: "查看知识库" },
      { key: "kb:create", label: "创建知识库" },
      { key: "kb:update", label: "更新知识库" },
      { key: "kb:delete", label: "删除知识库" },
      { key: "doc:read", label: "查看文档" },
      { key: "doc:upload", label: "上传文档" },
      { key: "doc:delete", label: "删除文档" },
    ],
  },
  {
    name: "插件与工具", icon: Puzzle,
    permissions: [
      { key: "skill:read", label: "查看技能" },
      { key: "skill:install", label: "安装技能" },
      { key: "skill:uninstall", label: "卸载技能" },
    ],
  },
  {
    name: "系统与管理", icon: Wrench,
    permissions: [
      { key: "user:read", label: "查看用户" },
      { key: "user:create", label: "创建用户" },
      { key: "user:update", label: "更新用户" },
      { key: "user:delete", label: "删除用户" },
      { key: "role:read", label: "查看角色" },
      { key: "role:create", label: "创建角色" },
      { key: "role:update", label: "更新角色" },
      { key: "role:delete", label: "删除角色" },
      { key: "dept:read", label: "查看部门" },
      { key: "dept:create", label: "创建部门" },
      { key: "dept:update", label: "更新部门" },
      { key: "dept:delete", label: "删除部门" },
      { key: "system:*", label: "所有系统权限" },
    ],
  },
  {
    name: "项目管理", icon: FolderKanban,
    permissions: [
      { key: "project:create", label: "创建项目" },
      { key: "project:edit", label: "编辑项目" },
      { key: "project:delete", label: "删除项目" },
      { key: "member:add", label: "添加成员" },
      { key: "member:remove", label: "移除成员" },
      { key: "settings:edit", label: "编辑项目设置" },
    ],
  },
  {
    name: "审批与审核", icon: ClipboardCheck,
    permissions: [
      { key: "approval:submit", label: "提交审批" },
      { key: "approval:review", label: "审核内容" },
      { key: "approval:approve", label: "批准/驳回" },
      { key: "approval:view", label: "查看审批" },
    ],
  },
  {
    name: "文档与协作", icon: FileText,
    permissions: [
      { key: "outline:edit", label: "编辑大纲" },
      { key: "chapter:write_any", label: "编写任意章节" },
      { key: "chapter:write_own", label: "编写自己章节" },
      { key: "chapter:review", label: "审阅章节" },
      { key: "ai:start_writing", label: "AI辅助写作" },
      { key: "source:view", label: "查看来源" },
      { key: "version:rollback", label: "版本回滚" },
      { key: "export:generate", label: "导出文档" },
    ],
  },
  {
    name: "工作流与模板", icon: Workflow,
    permissions: [
      { key: "workflow:start", label: "启动工作流" },
      { key: "workflow:cancel", label: "取消工作流" },
      { key: "workflow:edit", label: "编辑工作流" },
      { key: "template:manage", label: "管理模板" },
      { key: "template:publish", label: "发布模板" },
    ],
  },
];

/* ── Helpers ─────────────────────────────────────────── */
function getModuleIcon(key: string) {
  const map: Record<string, React.ComponentType<{ className?: string }>> = {
    knowledge: Database, model: Brain, plugin: Puzzle,
    system: Wrench, project: FolderKanban, approval: ClipboardCheck,
    document: FileText, workflow: Workflow,
  };
  return map[key] || Shield;
}

function modulesToCategories(modules: RegistryModule[]) {
  return modules.map((m) => ({
    name: m.display_name,
    icon: getModuleIcon(m.key),
    permissions: m.permissions.map((p) => ({ key: p.id, label: p.display_name })),
  }));
}

function getAllPermKeys(modules: RegistryModule[]): string[] {
  return modules.flatMap((m) => m.permissions.map((p) => p.id));
}

/** Check whether any module in the registry has the pages array (v3 tree format). */
function hasPageTree(modules: RegistryModule[] | null | undefined): boolean {
  return !!(modules && modules.length > 0 && modules.some((m) => m.pages && m.pages.length > 0));
}

/** Collect all operation IDs across modules with page tree, for "全选". */
function getAllTreePermKeys(modules: RegistryModule[]): string[] {
  const ids: string[] = [];
  for (const m of modules) {
    if (m.pages) {
      for (const page of m.pages) {
        for (const op of page.operations) {
          ids.push(op.id);
        }
      }
    }
    // Also include any module-level permissions without pages (backward compat)
    for (const p of m.permissions) {
      ids.push(p.id);
    }
  }
  return Array.from(new Set(ids));
}

/** Flat list of all permission keys from PERMISSION_CATEGORIES fallback. */
function getAllFallbackPermKeys(): string[] {
  return PERMISSION_CATEGORIES.flatMap((c) => c.permissions.map((p) => p.key));
}

/* ── Animated Permission Checkbox ─────────────────────────── */
function PermCheckbox({ checked, disabled }: { checked: boolean; disabled?: boolean }) {
  return (
    <span
      className={cn(
        "relative inline-flex items-center justify-center w-[18px] h-[18px] shrink-0 rounded-[5px] border-[1.5px] transition-all duration-200 ease-out select-none",
        checked
          ? "bg-primary border-primary shadow-[0_1px_4px_rgba(var(--color-primary),0.3)]"
          : "bg-transparent border-muted-foreground/30",
        disabled && "opacity-40 pointer-events-none",
      )}
    >
      <svg viewBox="0 0 14 14" fill="none" className="w-[11px] h-[11px]" aria-hidden="true">
        <motion.path
          d="M3 7.5L5.8 10.2L11 4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={cn(checked ? "text-primary-foreground" : "text-transparent")}
          initial={false}
          animate={checked ? { pathLength: 1, opacity: 1 } : { pathLength: 0, opacity: 0 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
        />
      </svg>
      <AnimatePresence>
        {checked && (
          <motion.span
            className="absolute inset-0 rounded-[5px] bg-primary/30"
            initial={{ scale: 1, opacity: 0.6 }}
            animate={{ scale: 1.6, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
          />
        )}
      </AnimatePresence>
    </span>
  );
}

/* ── Permission Panel with 3-level tree (Module → Page → Operation) ── */
function PermissionPanel({
  selected, onChange, readonly = false, compact = false,
  modules,
}: {
  selected: string[];
  onChange: (perms: string[]) => void;
  readonly?: boolean;
  compact?: boolean;
  modules?: RegistryModule[] | null;
}) {
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const isTree = hasPageTree(modules);
  const treeModules: RegistryModule[] = isTree ? modules! : [];
  const categories = !isTree && modules && modules.length > 0 ? modulesToCategories(modules) : (!isTree ? PERMISSION_CATEGORIES : []);
  const allPerms = isTree ? getAllTreePermKeys(treeModules) : (modules && modules.length > 0 ? getAllPermKeys(modules) : getAllFallbackPermKeys());

  // Initialise expanded state
  useEffect(() => {
    if (isTree && treeModules.length > 0) {
      setExpandedCats(new Set(treeModules.map((m) => m.key)));
    } else {
      setExpandedCats(new Set(categories.map((c) => c.name)));
    }
  }, [modules]);

  const toggleCat = (name: string) =>
    setExpandedCats((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });

  const togglePerm = (key: string) => {
    if (readonly) return;
    onChange(selected.includes(key) ? selected.filter((p) => p !== key) : [...selected, key]);
  };

  const toggleCategory = (keys: string[]) => {
    if (readonly) return;
    const allSelected = keys.every((k) => selected.includes(k));
    if (allSelected) onChange(selected.filter((p) => !keys.includes(p)));
    else onChange([...new Set([...selected, ...keys])]);
  };

  const gridStyle = compact
    ? { gridTemplateColumns: "repeat(auto-fill, minmax(145px, 1fr))" }
    : { gridTemplateColumns: "repeat(auto-fill, minmax(185px, 1fr))" };

  return (
    <div className="space-y-3">
      {!readonly && (
        <div className="flex gap-2">
          <button type="button" onClick={() => onChange(allPerms)}
            className="group flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-foreground/80 bg-background border border-border rounded-lg hover:border-primary/40 hover:text-primary hover:bg-primary/[0.04] transition-all duration-200">
            <PermCheckbox checked={false} />
            全选
          </button>
          <button type="button" onClick={() => onChange([])}
            className="px-3.5 py-1.5 text-xs font-medium text-muted-foreground bg-background border border-border rounded-lg hover:border-destructive/30 hover:text-destructive/80 hover:bg-destructive/[0.03] transition-all duration-200">
            清空
          </button>
        </div>
      )}

      {isTree && treeModules.length > 0 ? (
        /* ── 3-level tree rendering (v3 modules with pages) ── */
        treeModules.map((mod) => {
          const isExpanded = expandedCats.has(mod.key);

          // Collect all operation IDs under this module (across all pages + direct)
          const hasPages = !!(mod.pages && mod.pages.length > 0);
          const pageOpIds: string[] = mod.pages ? mod.pages.flatMap((pg) => pg.operations.map((op) => op.id)) : [];
          const directOpIds: string[] = mod.permissions.map((p) => p.id);
          const allOpIds = Array.from(new Set([...pageOpIds, ...directOpIds]));
          const totalOps = allOpIds.length;
          const selectedCount = selected.filter((k) => allOpIds.includes(k)).length;
          const allCatSelected = totalOps > 0 && allOpIds.every((k) => selected.includes(k));
          const ratio = totalOps > 0 ? selectedCount / totalOps : 0;
          const Icon = getModuleIcon(mod.key);

          return (
            <div key={mod.key} className="bg-card rounded-xl border border-border overflow-hidden">
              {/* Module header */}
              <div className="flex items-center w-full">
                <button type="button" onClick={() => toggleCat(mod.key)}
                  className="flex-1 flex items-center gap-3 p-4 hover:bg-accent/60 transition-colors text-left">
                  <div className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors duration-200",
                    selectedCount > 0
                      ? "bg-primary/10 border border-primary/20"
                      : "bg-muted border border-border",
                  )}>
                    <Icon className={cn("w-4 h-4 transition-colors duration-200", selectedCount > 0 ? "text-primary" : "text-muted-foreground")} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-foreground text-sm">{mod.display_name}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-muted-foreground tabular-nums">{selectedCount}/{totalOps}</span>
                      <span className="relative h-1 flex-1 max-w-[80px] bg-muted rounded-full overflow-hidden">
                        <motion.span
                          className="absolute inset-y-0 left-0 bg-primary rounded-full"
                          initial={false}
                          animate={{ width: `${ratio * 100}%` }}
                          transition={{ duration: 0.3, ease: "easeOut" }}
                        />
                      </span>
                    </div>
                  </div>
                  <div className="ml-auto mr-2">
                    <motion.div animate={{ rotate: isExpanded ? 0 : -90 }} transition={{ duration: 0.2 }}>
                      <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    </motion.div>
                  </div>
                </button>
                {!readonly && totalOps > 0 && (
                  <button type="button" onClick={() => toggleCategory(allOpIds)}
                    className={cn(
                      "px-3 py-1.5 mr-3 text-xs font-semibold rounded-lg transition-all duration-200 shrink-0",
                      allCatSelected
                        ? "bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20"
                        : "bg-secondary/60 text-muted-foreground border border-transparent hover:bg-accent hover:text-foreground hover:border-border",
                    )}>
                    {allCatSelected ? "取消全选" : "全选本组"}
                  </button>
                )}
              </div>

              {/* Expanded content: pages with their operations */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
                    <div className="px-3 pb-3 pt-1">
                      {hasPages ? (
                        mod.pages!.map((page) => {
                          const pageHasOps = page.operations.length > 0;
                          return (
                            <div key={page.id} className="mb-2 last:mb-0">
                              {/* Page header */}
                              <div className="flex items-center gap-2 py-2 px-1 text-sm font-semibold text-muted-foreground">
                                <FileText className="w-3.5 h-3.5 shrink-0 opacity-60" />
                                <span className="truncate">{page.display_name}</span>
                              </div>
                              {/* Operations grid */}
                              {pageHasOps ? (
                                <div className="grid gap-1.5" style={gridStyle}>
                                  {page.operations.map((op) => {
                                    const isChecked = selected.includes(op.id);
                                    return (
                                      <label key={op.id}
                                        className={cn(
                                          "group/perm flex items-center gap-2.5 text-sm p-2 rounded-lg transition-all duration-200 min-w-0 select-none",
                                          readonly ? "cursor-default" : "cursor-pointer",
                                          isChecked
                                            ? "bg-primary/[0.04] border border-primary/10"
                                            : "border border-transparent hover:bg-accent/50 hover:border-border",
                                        )}>
                                        <input type="checkbox" checked={isChecked}
                                          onChange={() => togglePerm(op.id)} disabled={readonly}
                                          className="sr-only peer" />
                                        <PermCheckbox checked={isChecked} disabled={readonly} />
                                        <span className={cn(
                                          "truncate transition-colors duration-200 leading-tight",
                                          readonly ? "text-muted-foreground" : isChecked ? "text-foreground font-medium" : "text-foreground/70 group-hover/perm:text-foreground",
                                        )}>
                                          {op.display_name}
                                        </span>
                                      </label>
                                    );
                                  })}
                                </div>
                              ) : (
                                <div className="text-xs text-muted-foreground/50 px-1 pb-2">暂无操作项</div>
                              )}
                            </div>
                          );
                        })
                      ) : (
                        /* Backward compat: module with no pages, show permissions directly */
                        totalOps > 0 ? (
                          <div className="grid gap-1.5" style={gridStyle}>
                            {mod.permissions.map((perm) => {
                              const isChecked = selected.includes(perm.id);
                              return (
                                <label key={perm.id}
                                  className={cn(
                                    "group/perm flex items-center gap-2.5 text-sm p-2 rounded-lg transition-all duration-200 min-w-0 select-none",
                                    readonly ? "cursor-default" : "cursor-pointer",
                                    isChecked
                                      ? "bg-primary/[0.04] border border-primary/10"
                                      : "border border-transparent hover:bg-accent/50 hover:border-border",
                                  )}>
                                  <input type="checkbox" checked={isChecked}
                                    onChange={() => togglePerm(perm.id)} disabled={readonly}
                                    className="sr-only peer" />
                                  <PermCheckbox checked={isChecked} disabled={readonly} />
                                  <span className={cn(
                                    "truncate transition-colors duration-200 leading-tight",
                                    readonly ? "text-muted-foreground" : isChecked ? "text-foreground font-medium" : "text-foreground/70 group-hover/perm:text-foreground",
                                  )}>
                                    {perm.display_name}
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="text-xs text-muted-foreground/50 px-1 py-2">暂无权限点</div>
                        )
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })
      ) : (
        /* ── Flat rendering (fallback / no pages) ── */
        categories.map((category) => {
          const Icon = category.icon;
          const isExpanded = expandedCats.has(category.name);
          const catKeys = category.permissions.map((p) => p.key);
          const selectedCount = selected.filter((p) => catKeys.includes(p)).length;
          const allCatSelected = catKeys.every((k) => selected.includes(k));
          const ratio = selectedCount / category.permissions.length;

          return (
            <div key={category.name} className="bg-card rounded-xl border border-border overflow-hidden">
              <div className="flex items-center w-full">
                <button type="button" onClick={() => toggleCat(category.name)}
                  className="flex-1 flex items-center gap-3 p-4 hover:bg-accent/60 transition-colors text-left">
                  <div className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors duration-200",
                    selectedCount > 0
                      ? "bg-primary/10 border border-primary/20"
                      : "bg-muted border border-border",
                  )}>
                    <Icon className={cn("w-4 h-4 transition-colors duration-200", selectedCount > 0 ? "text-primary" : "text-muted-foreground")} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-foreground text-sm">{category.name}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-muted-foreground tabular-nums">{selectedCount}/{category.permissions.length}</span>
                      <span className="relative h-1 flex-1 max-w-[80px] bg-muted rounded-full overflow-hidden">
                        <motion.span
                          className="absolute inset-y-0 left-0 bg-primary rounded-full"
                          initial={false}
                          animate={{ width: `${ratio * 100}%` }}
                          transition={{ duration: 0.3, ease: "easeOut" }}
                        />
                      </span>
                    </div>
                  </div>
                  <div className="ml-auto mr-2">
                    <motion.div animate={{ rotate: isExpanded ? 0 : -90 }} transition={{ duration: 0.2 }}>
                      <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    </motion.div>
                  </div>
                </button>
                {!readonly && (
                  <button type="button" onClick={() => toggleCategory(catKeys)}
                    className={cn(
                      "px-3 py-1.5 mr-3 text-xs font-semibold rounded-lg transition-all duration-200 shrink-0",
                      allCatSelected
                        ? "bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20"
                        : "bg-secondary/60 text-muted-foreground border border-transparent hover:bg-accent hover:text-foreground hover:border-border",
                    )}>
                    {allCatSelected ? "取消全选" : "全选本组"}
                  </button>
                )}
              </div>

              <AnimatePresence>
                {isExpanded && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
                    <div className="px-3 pb-3 pt-1 grid gap-1.5"
                      style={{ gridTemplateColumns: compact ? "repeat(auto-fill, minmax(145px, 1fr))" : "repeat(auto-fill, minmax(185px, 1fr))" }}>
                      {category.permissions.map((perm) => {
                        const isChecked = selected.includes(perm.key);
                        return (
                          <label key={perm.key}
                            className={cn(
                              "group/perm flex items-center gap-2.5 text-sm p-2 rounded-lg transition-all duration-200 min-w-0 select-none",
                              readonly ? "cursor-default" : "cursor-pointer",
                              isChecked
                                ? "bg-primary/[0.04] border border-primary/10"
                                : "border border-transparent hover:bg-accent/50 hover:border-border",
                            )}>
                            <input type="checkbox" checked={isChecked}
                              onChange={() => togglePerm(perm.key)} disabled={readonly}
                              className="sr-only peer" />
                            <PermCheckbox checked={isChecked} disabled={readonly} />
                            <span className={cn(
                              "truncate transition-colors duration-200 leading-tight",
                              readonly ? "text-muted-foreground" : isChecked ? "text-foreground font-medium" : "text-foreground/70 group-hover/perm:text-foreground",
                            )}>
                              {perm.label}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })
      )}
    </div>
  );
}

/* ── Matrix Overview: roles x permission categories ─────────── */
function RoleMatrixOverview({ roles, modules }: { roles: Role[]; modules?: RegistryModule[] | null }) {
  const categories = modules && modules.length > 0 ? modulesToCategories(modules) : PERMISSION_CATEGORIES;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr>
            <th className="sticky left-0 bg-muted/60 px-3 py-2 text-left font-semibold text-foreground border-b border-r">
              角色
            </th>
            {categories.map((cat) => (
              <th key={cat.name} className="px-3 py-2 text-center font-medium text-muted-foreground border-b whitespace-nowrap">
                {cat.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {roles.map((role) => (
            <tr key={role.id} className="hover:bg-accent/40 transition-colors">
              <td className="sticky left-0 bg-card px-3 py-2.5 font-medium text-foreground border-b border-r whitespace-nowrap">
                <div className="flex items-center gap-1.5">
                  <Shield className={cn("w-3.5 h-3.5", role.is_system ? "text-amber-500" : "text-muted-foreground")} />
                  <span>{role.name}</span>
                </div>
              </td>
              {categories.map((cat) => {
                const catKeys = cat.permissions.map((p) => p.key);
                const count = catKeys.filter((k) => (role.permissions || []).includes(k)).length;
                const total = catKeys.length;
                const ratio = total > 0 ? count / total : 0;
                return (
                  <td key={cat.name} className="px-3 py-2.5 text-center border-b">
                    <div className="flex flex-col items-center gap-1">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center text-[10px] font-bold"
                        style={{
                          backgroundColor: ratio === 0 ? "var(--muted)" : ratio >= 1 ? "rgba(34,197,94,0.15)" : "rgba(59,130,246,0.15)",
                          color: ratio === 0 ? "var(--muted-foreground)" : ratio >= 1 ? "rgb(22,163,74)" : "rgb(37,99,235)",
                        }}>
                        {count}/{total}
                      </div>
                      {total > 0 && (
                        <div className="w-10 h-1 rounded-full bg-muted overflow-hidden">
                          <div
                            className={cn("h-full rounded-full", ratio >= 1 ? "bg-green-500" : ratio > 0 ? "bg-blue-500" : "bg-transparent")}
                            style={{ width: `${ratio * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Data Scope Panel ──────────────────────────────────────── */
function DataScopePanel({
  modules, selections, onChange, readonly,
}: {
  modules: RegistryModule[];
  selections: Record<string, string>;
  onChange: (selections: Record<string, string>) => void;
  readonly?: boolean;
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">为各资源类型设置数据访问范围</p>
      {modules
        .filter((m) => m.data_scopes && m.data_scopes.length > 0)
        .map((module) => {
          const currentVal = selections[module.key] || module.data_scopes[0]?.id || "";
          return (
            <div key={module.key} className="bg-card rounded-xl border border-border p-4">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                  {(() => { const Icon = getModuleIcon(module.key); return <Icon className="w-4 h-4 text-primary" />; })()}
                </div>
                <span className="font-medium text-foreground text-sm">{module.display_name}</span>
              </div>
              <div className="flex flex-wrap gap-3 pl-11">
                {module.data_scopes.map((scope) => {
                  const isSelected = currentVal === scope.id;
                  return (
                    <label
                      key={scope.id}
                      className={cn(
                        "flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-all duration-200",
                        readonly ? "cursor-default" : "cursor-pointer",
                        isSelected
                          ? "bg-primary/[0.06] border-primary/30 text-primary font-medium"
                          : "border-border text-muted-foreground hover:border-primary/20 hover:text-foreground",
                      )}
                    >
                      <input
                        type="radio"
                        name={`scope-${module.key}`}
                        value={scope.id}
                        checked={isSelected}
                        onChange={() => { if (!readonly) onChange({ ...selections, [module.key]: scope.id }); }}
                        disabled={readonly}
                        className="sr-only"
                      />
                      <span className={cn(
                        "w-3.5 h-3.5 rounded-full border-[1.5px] flex items-center justify-center shrink-0",
                        isSelected ? "border-primary" : "border-muted-foreground/40",
                      )}>
                        {isSelected && <span className="w-2 h-2 rounded-full bg-primary" />}
                      </span>
                      <span>{scope.display_name}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          );
        })}
      {modules.filter((m) => m.data_scopes && m.data_scopes.length > 0).length === 0 && (
        <div className="text-center py-8 text-muted-foreground text-sm">
          <Filter className="w-8 h-8 mx-auto mb-2 opacity-30" />
          暂无数据权限配置项
        </div>
      )}
    </div>
  );
}

/* ── Policies Panel ────────────────────────────────────────── */
function PoliciesPanel({
  policies, policiesLoading, onToggle, onDelete, onAdd, onSave, modules,
}: {
  policies: PolicyItem[];
  policiesLoading: boolean;
  onToggle: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
  onAdd: () => void;
  onSave: (policy: PolicyItem) => void;
  modules: RegistryModule[];
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<{ name: string; conditions: PolicyCondition[]; grants: PolicyGrant[] }>({
    name: "", conditions: [], grants: [],
  });

  const startEdit = useCallback((policy?: PolicyItem) => {
    if (policy) {
      setEditingId(policy.id);
      setEditForm({ name: policy.name, conditions: [...policy.conditions], grants: [...policy.grants] });
    } else {
      setEditingId("__new__");
      setEditForm({ name: "", conditions: [{ attribute: "", operator: "=", value: "" }], grants: [{ permission: "", data_scope: "" }] });
    }
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setEditForm({ name: "", conditions: [], grants: [] });
  }, []);

  const handleSave = useCallback(() => {
    onSave({
      id: editingId === "__new__" ? "" : (editingId || ""),
      name: editForm.name,
      enabled: true,
      conditions: editForm.conditions,
      grants: editForm.grants,
    });
    cancelEdit();
  }, [editingId, editForm, onSave, cancelEdit]);

  const allPermissions = modules.flatMap((m) => m.permissions);
  const allDataScopes = modules.flatMap((m) => m.data_scopes);

  if (policiesLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
        <Loader2 className="w-4 h-4 animate-spin mr-2" />加载中...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">管理自定义访问策略（属性条件 + 权限授予）</p>
        <button
          type="button"
          onClick={() => startEdit()}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-primary bg-primary/10 border border-primary/20 rounded-lg hover:bg-primary/20 transition-all"
        >
          <Plus className="w-3.5 h-3.5" /> 添加策略
        </button>
      </div>

      {/* Policy list */}
      {policies.length === 0 && editingId !== "__new__" && (
        <div className="text-center py-12 text-muted-foreground text-sm bg-card rounded-xl border border-border">
          <GripVertical className="w-8 h-8 mx-auto mb-2 opacity-30" />
          暂无自定义策略，点击"添加策略"创建
        </div>
      )}

      {policies.map((policy) => (
        <div key={policy.id} className={cn(
          "bg-card rounded-xl border p-4 transition-all",
          policy.enabled ? "border-border" : "border-border/50 opacity-60",
        )}>
          {editingId === policy.id ? (
            <PolicyEditForm
              form={editForm}
              onChange={setEditForm}
              onSave={handleSave}
              onCancel={cancelEdit}
              allPermissions={allPermissions}
              allDataScopes={allDataScopes}
            />
          ) : (
            <PolicyRow
              policy={policy}
              onToggle={onToggle}
              onDelete={onDelete}
              onEdit={() => startEdit(policy)}
              allPermissions={allPermissions}
            />
          )}
        </div>
      ))}

      {/* New policy form */}
      {editingId === "__new__" && (
        <div className="bg-card rounded-xl border border-primary/30 p-4 ring-1 ring-primary/10">
          <PolicyEditForm
            form={editForm}
            onChange={setEditForm}
            onSave={handleSave}
            onCancel={cancelEdit}
            allPermissions={allPermissions}
            allDataScopes={allDataScopes}
          />
        </div>
      )}
    </div>
  );
}

/* ── Policy Row (read-only) ────────────────────────────────── */
function PolicyRow({
  policy, onToggle, onDelete, onEdit, allPermissions,
}: {
  policy: PolicyItem;
  onToggle: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
  onEdit: () => void;
  allPermissions: PermissionItem[];
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-medium text-foreground text-sm">{policy.name}</span>
          <button
            type="button"
            onClick={() => onToggle(policy.id, !policy.enabled)}
            className={cn(
              "flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border transition-colors",
              policy.enabled
                ? "bg-success/10 text-success border-success/30"
                : "bg-muted text-muted-foreground border-border",
            )}
          >
            {policy.enabled ? <><Eye className="w-3 h-3" /> 已启用</> : <><EyeOff className="w-3 h-3" /> 已禁用</>}
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onEdit} className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent rounded transition-colors">
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => onDelete(policy.id)} className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      {/* Conditions summary */}
      {policy.conditions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {policy.conditions.map((c, i) => (
            <span key={i} className="text-[11px] px-2 py-0.5 rounded bg-muted text-muted-foreground font-mono">
              {c.attribute || "?"} {c.operator} {c.value || "?"}
            </span>
          ))}
        </div>
      )}
      {/* Grants summary */}
      {policy.grants.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {policy.grants.map((g, i) => {
            const permLabel = allPermissions.find((p) => p.id === g.permission)?.display_name || g.permission;
            return (
              <span key={i} className="text-[11px] px-2 py-0.5 rounded bg-primary/[0.06] text-primary border border-primary/10 font-medium">
                {permLabel}{g.data_scope ? ` (${g.data_scope})` : ""}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── Policy Edit Form ──────────────────────────────────────── */
function PolicyEditForm({
  form, onChange, onSave, onCancel, allPermissions, allDataScopes,
}: {
  form: { name: string; conditions: PolicyCondition[]; grants: PolicyGrant[] };
  onChange: (f: { name: string; conditions: PolicyCondition[]; grants: PolicyGrant[] }) => void;
  onSave: () => void;
  onCancel: () => void;
  allPermissions: PermissionItem[];
  allDataScopes: DataScopeItem[];
}) {
  const addCondition = () => onChange({ ...form, conditions: [...form.conditions, { attribute: "", operator: "=", value: "" }] });
  const removeCondition = (i: number) => onChange({ ...form, conditions: form.conditions.filter((_, idx) => idx !== i) });
  const updateCondition = (i: number, f: Partial<PolicyCondition>) => {
    const conds = [...form.conditions];
    conds[i] = { ...conds[i], ...f };
    onChange({ ...form, conditions: conds });
  };

  const addGrant = () => onChange({ ...form, grants: [...form.grants, { permission: "", data_scope: "" }] });
  const removeGrant = (i: number) => onChange({ ...form, grants: form.grants.filter((_, idx) => idx !== i) });
  const updateGrant = (i: number, f: Partial<PolicyGrant>) => {
    const grs = [...form.grants];
    grs[i] = { ...grs[i], ...f };
    onChange({ ...form, grants: grs });
  };

  const ATTR_OPTIONS = ["tags", "role_level", "dept_id", "user_id", "email_domain"];
  const OP_OPTIONS = ["=", "!=", "contains", ">=", "<=", "in", "not_in"];

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs font-medium text-foreground mb-1">策略名称</label>
        <input
          type="text"
          value={form.name}
          onChange={(e) => onChange({ ...form, name: e.target.value })}
          placeholder="例如：仅限高级用户访问"
          className="w-full px-3 py-2 bg-background border border-input rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
        />
      </div>

      {/* Conditions */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-medium text-foreground">条件 (Conditions)</label>
          <button type="button" onClick={addCondition} className="text-xs text-primary hover:text-primary/80 font-medium">
            + 添加条件
          </button>
        </div>
        <div className="space-y-2">
          {form.conditions.map((c, i) => (
            <div key={i} className="flex items-center gap-2">
              <Select value={c.attribute || "__none__"} onValueChange={(v) => updateCondition(i, { attribute: v === "__none__" ? "" : v })}>
                <SelectTrigger className="w-[130px] h-8 text-xs"><SelectValue placeholder="属性" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__"><span className="text-muted-foreground">选择属性</span></SelectItem>
                  {ATTR_OPTIONS.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={c.operator} onValueChange={(v) => updateCondition(i, { operator: v })}>
                <SelectTrigger className="w-[100px] h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {OP_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                </SelectContent>
              </Select>
              <input
                type="text"
                value={c.value}
                onChange={(e) => updateCondition(i, { value: e.target.value })}
                placeholder="值"
                className="flex-1 h-8 px-2 bg-background border border-input rounded text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
              <button onClick={() => removeCondition(i)} className="p-1 text-muted-foreground hover:text-destructive transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Grants */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-medium text-foreground">权限授予 (Grants)</label>
          <button type="button" onClick={addGrant} className="text-xs text-primary hover:text-primary/80 font-medium">
            + 添加授予
          </button>
        </div>
        <div className="space-y-2">
          {form.grants.map((g, i) => (
            <div key={i} className="flex items-center gap-2">
              <Select value={g.permission || "__none__"} onValueChange={(v) => updateGrant(i, { permission: v === "__none__" ? "" : v })}>
                <SelectTrigger className="w-[180px] h-8 text-xs"><SelectValue placeholder="选择权限" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__"><span className="text-muted-foreground">选择权限</span></SelectItem>
                  {allPermissions.map((p) => <SelectItem key={p.id} value={p.id}>{p.display_name}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={g.data_scope || "__none__"} onValueChange={(v) => updateGrant(i, { data_scope: v === "__none__" ? "" : v })}>
                <SelectTrigger className="w-[160px] h-8 text-xs"><SelectValue placeholder="数据范围" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__"><span className="text-muted-foreground">不限</span></SelectItem>
                  {allDataScopes.map((s) => <SelectItem key={s.id} value={s.id}>{s.display_name}</SelectItem>)}
                </SelectContent>
              </Select>
              <button onClick={() => removeGrant(i)} className="p-1 text-muted-foreground hover:text-destructive transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
        <button onClick={onCancel}
          className="px-3 py-1.5 text-xs font-medium text-foreground bg-background border border-input rounded-lg hover:bg-muted transition-colors">
          取消
        </button>
        <button onClick={onSave}
          className="px-3 py-1.5 text-xs font-medium text-white bg-primary rounded-lg hover:bg-primary/90 transition-colors shadow-sm">
          保存
        </button>
      </div>
    </div>
  );
}

/* ── Main Page Component ───────────────────────────────────── */
export default function AdminRolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"permissions" | "datascope" | "policies" | "users">("permissions");
  const [showMatrix, setShowMatrix] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [roleUsers, setRoleUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);

  // Registry & policies
  const [registryModules, setRegistryModules] = useState<RegistryModule[] | null>(null);
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [policiesLoading, setPoliciesLoading] = useState(false);
  const [dataScopeSelections, setDataScopeSelections] = useState<Record<string, string>>({});

  const [createForm, setCreateForm] = useState<CreateRoleRequest>({
    name: "", code: "", permissions: [], description: "", level: 10, parent_role_id: undefined,
  });
  const [editForm, setEditForm] = useState<{ name: string; description: string; permissions: string[]; level?: number; parent_role_id?: string }>({
    name: "", description: "", permissions: [],
  });

  /* ── Data loading ────────────────────────────────────────── */
  const loadData = async () => {
    setIsLoading(true);
    try {
      const res = await roleApi.list();
      setRoles(res.roles);
      setSelectedRole((prev) =>
        prev
          ? (res.roles.find((r) => r.id === prev.id) ?? prev)
          : (res.roles[0] ?? null)
      );
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  // Fetch permissions registry on mount
  useEffect(() => {
    permissionsApi.getRegistry()
      .then((res) => setRegistryModules(res.modules))
      .catch((err) => console.error("Failed to load permissions registry:", err));
  }, []);

  // Fetch policies when tab changes to policies
  const loadPolicies = useCallback(async () => {
    setPoliciesLoading(true);
    try {
      const res = await permissionsApi.listPolicies();
      setPolicies(res.policies || []);
    } catch (err) {
      console.error("Failed to load policies:", err);
      setPolicies([]);
    } finally {
      setPoliciesLoading(false);
    }
  }, []);

  /* ── Handlers ────────────────────────────────────────────── */
  const filteredRoles = searchQuery
    ? roles.filter((r) =>
        r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.code || "").toLowerCase().includes(searchQuery.toLowerCase())
      )
    : roles;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await roleApi.create(createForm);
      setIsCreateModalOpen(false);
      setCreateForm({ name: "", code: "", permissions: [], description: "" });
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "创建失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定要删除该角色吗？")) return;
    try {
      await roleApi.delete(id);
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "删除失败");
    }
  };

  const openEditModal = (role: Role) => {
    setEditForm({
      name: role.name,
      description: role.description || "",
      permissions: role.permissions ?? [],
      level: role.level,
      parent_role_id: role.parent_role_id,
    });
    setIsEditModalOpen(true);
  };

  const handleEdit = async () => {
    if (!selectedRole) return;
    try {
      await roleApi.update(selectedRole.id, editForm);
      setIsEditModalOpen(false);
      loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "更新失败");
    }
  };

  const loadRoleUsers = async (role: Role) => {
    setUsersLoading(true);
    try {
      const res = await userApi.list({ limit: 500, role_id: role.id });
      setRoleUsers(res.users);
    } catch {
      setRoleUsers([]);
    } finally {
      setUsersLoading(false);
    }
  };

  const handleSelectRole = (role: Role) => {
    setSelectedRole(role);
    setActiveTab("permissions");
    setRoleUsers([]);
  };

  const handleTabChange = (tab: "permissions" | "datascope" | "policies" | "users") => {
    setActiveTab(tab);
    if (tab === "users" && selectedRole && roleUsers.length === 0 && !usersLoading) {
      loadRoleUsers(selectedRole);
    }
    if (tab === "policies" && policies.length === 0 && !policiesLoading) {
      loadPolicies();
    }
  };

  // Policy CRUD handlers
  const handlePolicyToggle = async (id: string, enabled: boolean) => {
    try {
      await permissionsApi.updatePolicy(id, { enabled });
      setPolicies((prev) => prev.map((p) => p.id === id ? { ...p, enabled } : p));
    } catch (err) {
      console.error("Failed to toggle policy:", err);
    }
  };

  const handlePolicyDelete = async (id: string) => {
    if (!confirm("确定要删除该策略吗？")) return;
    try {
      await permissionsApi.deletePolicy(id);
      setPolicies((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      console.error("Failed to delete policy:", err);
    }
  };

  const handlePolicySave = async (policy: PolicyItem) => {
    try {
      if (policy.id) {
        await permissionsApi.updatePolicy(policy.id, { name: policy.name, conditions: policy.conditions, grants: policy.grants });
        setPolicies((prev) => prev.map((p) => p.id === policy.id ? { ...p, name: policy.name, conditions: policy.conditions, grants: policy.grants } : p));
      } else {
        const created = await permissionsApi.createPolicy({
          name: policy.name, conditions: policy.conditions, grants: policy.grants,
          role_id: selectedRole?.id, enabled: true,
        });
        setPolicies((prev) => [...prev, created]);
      }
    } catch (err) {
      console.error("Failed to save policy:", err);
      alert("保存策略失败");
    }
  };

  // Save data scope selections to role
  const handleDataScopeChange = async (selections: Record<string, string>) => {
    setDataScopeSelections(selections);
    if (selectedRole && !selectedRole.is_system) {
      try {
        // Append data_scopes to role update payload
        await roleApi.update(selectedRole.id, { permissions: selectedRole.permissions, data_scopes: selections } as unknown as UpdateRoleRequest);
      } catch (err) {
        console.error("Failed to save data scopes:", err);
      }
    }
  };

  const formatDate = (s: string) => {
    try {
      const d = new Date(s);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    } catch { return s; }
  };

  if (isLoading) {
    return <PageLoadingOverlay text="加载中" />;
  }

  const modules = registryModules || [];

  return (
    <main className="h-full flex overflow-hidden max-w-[1600px] w-full mx-auto bg-background">
      {/* Left Sidebar */}
      <div className="w-80 border-r border-border bg-muted/30 flex flex-col shrink-0">
        <div className="p-4 border-b border-border bg-card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-foreground">角色列表</h2>
            <button onClick={() => setIsCreateModalOpen(true)}
              className="p-1.5 bg-primary/10 text-primary rounded-md hover:bg-primary/20 transition-colors" title="新建角色">
              <Plus className="w-4 h-4" />
            </button>
          </div>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input type="text" placeholder="搜索角色..." value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-secondary border-transparent focus:bg-background focus:border-primary focus:ring-2 focus:ring-primary/20 rounded-lg text-sm transition-all outline-none" />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {filteredRoles.length === 0 ? (
            <div className="text-sm text-muted-foreground py-4 text-center">暂无角色</div>
          ) : (
            filteredRoles.map((role) => {
              const isSelected = selectedRole?.id === role.id;
              return (
                <button key={role.id} onClick={() => handleSelectRole(role)}
                  className={cn(
                    "w-full text-left p-3 rounded-xl transition-all duration-200 border",
                    isSelected
                      ? "bg-card border-primary/30 shadow-sm ring-1 ring-primary/10"
                      : "border-transparent hover:bg-accent"
                  )}>
                  <div className="flex items-center justify-between mb-1">
                    <span className={cn("font-medium text-sm truncate", isSelected ? "text-primary" : "text-foreground")}>
                      {role.name}
                    </span>
                    {role.is_system && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground font-medium shrink-0 ml-1">系统</span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground line-clamp-1 mb-2 min-h-[1rem]">
                    {role.description || <span className="opacity-40">暂无描述</span>}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Users className="w-3 h-3" /> —
                    </span>
                    <span className="flex items-center gap-1">
                      <Key className="w-3 h-3" /> {role.permissions?.length ?? 0} 权限
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Right Side */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedRole ? (
          <>
            {/* Header */}
            <div className="px-8 pt-6 shrink-0">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                    <Settings className="w-4 h-4" />
                    <span>角色详情</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <h1 className="text-2xl font-bold text-foreground tracking-tight">{selectedRole.name}</h1>
                    <span className="text-xs px-2 py-1 rounded-md bg-muted text-muted-foreground font-medium border border-border font-mono">
                      {selectedRole.code}
                    </span>
                    {selectedRole.is_system && (
                      <span className="flex items-center gap-1 text-xs font-medium text-warning bg-warning/10 px-2 py-1 rounded-full border border-warning/50">
                        <Lock className="w-3 h-3" /> 系统预设角色，不可修改
                      </span>
                    )}
                  </div>
                  {selectedRole.description && (
                    <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">{selectedRole.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {!selectedRole.is_system && (
                    <>
                      <button onClick={() => openEditModal(selectedRole)}
                        className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-foreground bg-background border border-input rounded-lg hover:bg-muted transition-colors shadow-sm">
                        <Pencil className="w-4 h-4" /> 编辑
                      </button>
                      <button onClick={() => handleDelete(selectedRole.id)}
                        className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-destructive bg-background border border-destructive/30 rounded-lg hover:bg-destructive/10 transition-colors shadow-sm">
                        <Trash2 className="w-4 h-4" /> 删除
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Tabs */}
              <div className="flex items-center gap-6 mt-4 border-b border-border px-8 -mx-8 overflow-x-auto">
                <button onClick={() => handleTabChange("permissions")}
                  className={cn("pb-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                    activeTab === "permissions" ? "text-primary" : "text-muted-foreground hover:text-foreground")}>
                  <KeyRound className="w-3.5 h-3.5 inline mr-1.5" />
                  操作权限
                  {activeTab === "permissions" && (
                    <motion.div layoutId="roleActiveTab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
                  )}
                </button>
                <button onClick={() => handleTabChange("datascope")}
                  className={cn("pb-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                    activeTab === "datascope" ? "text-primary" : "text-muted-foreground hover:text-foreground")}>
                  <Filter className="w-3.5 h-3.5 inline mr-1.5" />
                  数据权限
                  {activeTab === "datascope" && (
                    <motion.div layoutId="roleActiveTab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
                  )}
                </button>
                <button onClick={() => handleTabChange("policies")}
                  className={cn("pb-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                    activeTab === "policies" ? "text-primary" : "text-muted-foreground hover:text-foreground")}>
                  <GripVertical className="w-3.5 h-3.5 inline mr-1.5" />
                  自定义策略
                  {activeTab === "policies" && (
                    <motion.div layoutId="roleActiveTab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
                  )}
                </button>
                <button onClick={() => handleTabChange("users")}
                  className={cn("pb-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                    activeTab === "users" ? "text-primary" : "text-muted-foreground hover:text-foreground")}>
                  关联用户{activeTab === "users" ? ` (${usersLoading ? "…" : roleUsers.length})` : ""}
                  {activeTab === "users" && (
                    <motion.div layoutId="roleActiveTab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
                  )}
                </button>
                {/* Matrix view toggle — only for permissions tab */}
                {activeTab === "permissions" && (
                  <div className="ml-auto flex items-center gap-1 pb-3">
                    <button
                      type="button"
                      onClick={() => setShowMatrix(false)}
                      className={cn("p-1.5 rounded transition-colors", !showMatrix ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}
                      title="列表视图"
                    >
                      <List className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowMatrix(true)}
                      className={cn("p-1.5 rounded transition-colors", showMatrix ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}
                      title="矩阵概览"
                    >
                      <LayoutGrid className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-y-auto p-8 bg-muted/20">
              <AnimatePresence mode="wait">
                {activeTab === "permissions" ? (
                  <motion.div key="permissions" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} className="w-full">
                    {showMatrix ? (
                      <div>
                        <h3 className="text-sm font-semibold mb-3">角色权限矩阵</h3>
                        <div className="bg-card rounded-xl border border-border overflow-hidden">
                          <RoleMatrixOverview roles={roles} modules={registryModules} />
                        </div>
                      </div>
                    ) : (
                    <>
                    {selectedRole.is_system && (
                      <p className="text-xs text-muted-foreground mb-4">系统角色权限为只读</p>
                    )}
                    <PermissionPanel
                      selected={selectedRole.permissions ?? []}
                      readonly={selectedRole.is_system}
                      modules={registryModules}
                      onChange={async (perms) => {
                        try {
                          await roleApi.update(selectedRole.id, { permissions: perms });
                          loadData();
                        } catch (err: unknown) {
                          alert(err instanceof Error ? err.message : "更新权限失败");
                        }
                      }}
                    />
                    </>
                    )}
                  </motion.div>
                ) : activeTab === "datascope" ? (
                  <motion.div key="datascope" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
                    {selectedRole.is_system && (
                      <p className="text-xs text-muted-foreground mb-4">系统角色数据权限为只读</p>
                    )}
                    <DataScopePanel
                      modules={modules}
                      selections={dataScopeSelections}
                      onChange={handleDataScopeChange}
                      readonly={selectedRole.is_system}
                    />
                  </motion.div>
                ) : activeTab === "policies" ? (
                  <motion.div key="policies" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
                    <PoliciesPanel
                      policies={policies}
                      policiesLoading={policiesLoading}
                      onToggle={handlePolicyToggle}
                      onDelete={handlePolicyDelete}
                      onAdd={loadPolicies}
                      onSave={handlePolicySave}
                      modules={modules}
                    />
                  </motion.div>
                ) : (
                  <motion.div key="users" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
                    {usersLoading ? (
                      <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
                        <Loader2 className="w-4 h-4 animate-spin mr-2" />加载中...
                      </div>
                    ) : roleUsers.length === 0 ? (
                      <div className="bg-card rounded-2xl border border-border shadow-sm p-8 text-center max-w-lg mx-auto">
                        <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4 text-muted-foreground">
                          <Users className="w-8 h-8" />
                        </div>
                        <h3 className="text-base font-medium text-foreground mb-2">暂无关联用户</h3>
                        <p className="text-muted-foreground text-sm mb-6">当前没有用户被分配 "{selectedRole.name}" 角色，可前往用户管理页面进行分配。</p>
                        <a href="/admin/users"
                          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm shadow-sm">
                          前往用户管理
                        </a>
                      </div>
                    ) : (
                      <div className="max-w-3xl">
                        <div className="grid grid-cols-2 gap-3 mb-6">
                          {roleUsers.map((user) => (
                            <div key={user.id}
                              className="flex items-center gap-3 p-3 rounded-xl bg-card border border-border hover:shadow-sm transition-all">
                              <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm shrink-0">
                                {(user.full_name || user.username).charAt(0).toUpperCase()}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="font-medium text-foreground text-sm truncate">{user.full_name || user.username}</div>
                                <div className="text-xs text-muted-foreground truncate">{user.email}</div>
                              </div>
                              <span className={cn("text-xs px-1.5 py-0.5 rounded-full font-medium shrink-0",
                                user.status === "active" ? "bg-success/10 text-success" : "bg-secondary text-muted-foreground")}>
                                {user.status === "active" ? "正常" : "停用"}
                              </span>
                            </div>
                          ))}
                        </div>
                        <div className="text-center">
                          <a href="/admin/users"
                            className="text-sm text-primary hover:text-primary/80 font-medium transition-colors">
                            前往用户管理 →
                          </a>
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Shield className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">请选择一个角色查看详情</p>
            </div>
          </div>
        )}
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {isCreateModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsCreateModalOpen(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-background rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
              <div className="px-6 py-4 border-b border-border flex items-center justify-between shrink-0">
                <h3 className="text-lg font-semibold text-foreground">新建角色</h3>
                <button onClick={() => setIsCreateModalOpen(false)}
                  className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <form onSubmit={handleCreate} className="p-6 space-y-5 overflow-y-auto flex-1">
                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      角色名称 <span className="text-destructive">*</span>
                    </label>
                    <Input placeholder="例如：管理员" value={createForm.name}
                      onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })} required />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      角色代码 <span className="text-destructive">*</span>
                    </label>
                    <Input placeholder="例如：admin" value={createForm.code}
                      onChange={(e) => setCreateForm({ ...createForm, code: e.target.value })} required />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">描述</label>
                  <textarea rows={2} placeholder="角色描述（选填）"
                    value={createForm.description || ""}
                    onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                    className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary text-sm resize-none" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">权限配置</label>
                  <PermissionPanel selected={createForm.permissions ?? []}
                    modules={registryModules}
                    compact
                    onChange={(perms) => setCreateForm({ ...createForm, permissions: perms })} />
                </div>
              </form>
              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-end gap-3 shrink-0">
                <button type="button" onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-foreground bg-background border border-input rounded-lg hover:bg-muted transition-colors">
                  取消
                </button>
                <button type="submit" onClick={handleCreate}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 transition-colors shadow-sm">
                  创建角色
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Edit Modal */}
      <AnimatePresence>
        {isEditModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsEditModalOpen(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative bg-background rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
              <div className="px-6 py-4 border-b border-border flex items-center justify-between shrink-0">
                <h3 className="text-lg font-semibold text-foreground">编辑角色 — {selectedRole?.name}</h3>
                <button onClick={() => setIsEditModalOpen(false)}
                  className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 space-y-5 overflow-y-auto flex-1">
                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">角色名称</label>
                    <Input value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">角色代码</label>
                    <Input value={selectedRole?.code || ""} disabled
                      className="bg-muted text-muted-foreground cursor-not-allowed" />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">描述</label>
                  <textarea rows={2} placeholder="角色描述（选填）"
                    value={editForm.description || ""}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                    className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary text-sm resize-none" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">层级</label>
                    <input
                      type="number"
                      value={editForm.level ?? 10}
                      onChange={(e) => setEditForm({ ...editForm, level: parseInt(e.target.value) || 10 })}
                      className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary text-sm"
                      min="1"
                      max="100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">继承角色</label>
                    <Select
                      value={editForm.parent_role_id || "__none__"}
                      onValueChange={(v) => setEditForm({ ...editForm, parent_role_id: v === "__none__" ? undefined : v })}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="无继承" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">
                          <span className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/30 shrink-0" />
                            <span className="text-muted-foreground">无继承</span>
                          </span>
                        </SelectItem>
                        {roles
                          .filter((r) => r.id !== selectedRole?.id)
                          .map((r) => (
                            <SelectItem key={r.id} value={r.id}>
                              <span className="flex items-center gap-2">
                                <span className={cn(
                                  "w-1.5 h-1.5 rounded-full shrink-0",
                                  r.is_system ? "bg-amber-400" : "bg-primary/60",
                                )} />
                                <span>{r.name}</span>
                                <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                                  Lv.{r.level}
                                </span>
                                {r.is_system && (
                                  <span className="text-[10px] text-amber-600 bg-amber-50 dark:bg-amber-950/30 px-1.5 py-0.5 rounded font-medium">
                                    系统
                                  </span>
                                )}
                              </span>
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">权限配置</label>
                  <PermissionPanel selected={editForm.permissions}
                    modules={registryModules}
                    compact
                    onChange={(perms) => setEditForm({ ...editForm, permissions: perms })} />
                </div>
              </div>
              <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-end gap-3 shrink-0">
                <button onClick={() => setIsEditModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-foreground bg-background border border-input rounded-lg hover:bg-accent transition-colors">
                  取消
                </button>
                <button onClick={handleEdit}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 transition-colors shadow-sm">
                  保存
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </main>
  );
}
