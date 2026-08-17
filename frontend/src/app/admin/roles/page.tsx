"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Plus,
  Shield,
  Lock,
  Pencil,
  Trash2,
  Users,
  X,
  ChevronDown,
  ChevronRight,
  Brain,
  Database,
  Puzzle,
  Wrench,
  Settings,
  Key,
  Loader2,
  FolderKanban,
  ClipboardCheck,
  FileText,
  Workflow,
  LayoutGrid,
  List,
  KeyRound,
  Filter,
  Eye,
  EyeOff,
  GripVertical,
  AlertTriangle,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { PageLoadingOverlay } from "@/components/ui/page-loading-overlay";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  deptApi,
  permissionsApi,
  projectApi,
  roleApi,
  userApi,
} from "@/extensions/api";
import { resolveDataScopeSelections } from "@/extensions/role/dataScope";
import {
  isSinglePageModule,
  isVisibilityOnlyModule,
  resolveVisiblePages,
  serializePages,
  shouldHideModule,
} from "@/extensions/role/pageVisibility";
import {
  toDenyInfo,
  toEngineConditions,
  toEngineGrants,
  toGrantArray,
  toUIConditions,
} from "@/extensions/role/policyConverters";
import type {
  Role,
  CreateRoleRequest,
  User,
  RegistryModule,
  PermissionItem,
  Department,
  OperationItem,
  PolicyItem,
  PolicyCondition,
  PolicyGrant,
} from "@/extensions/types";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 策略条件属性/操作符中文标签 —— key 保持引擎值，仅展示用中文（下拉 + PolicyRow 共用）
const ATTR_LABELS: Record<string, string> = {
  role_code: "角色代码",
  username: "用户名",
  tags: "标签",
  role_level: "角色级别",
  dept_id: "部门ID",
  dept_ids: "部门ID（多值）",
  member_projects: "参与项目",
  user_id: "用户ID",
};

// EAI-CUSTOM (标签池): 常用标签池 —— 派生 role:/dept: 标签 + 可编辑的业务标签（按需增删）
const COMMON_TAGS = ["vip", "外包", "试用"];
const OP_LABELS: Record<string, string> = {
  "=": "等于",
  "!=": "不等于",
  ">=": "大于等于",
  "<=": "小于等于",
  contains: "包含",
  in: "属于",
  not_in: "不属于",
};

/* ── Fallback permission categories (used when registry not loaded) ── */
const PERMISSION_CATEGORIES = [
  {
    name: "模型访问控制",
    icon: Brain,
    permissions: [
      { key: "model:read", label: "查看模型" },
      { key: "model:create", label: "创建模型配置" },
      { key: "model:update", label: "更新模型配置" },
      { key: "model:delete", label: "删除模型配置" },
    ],
  },
  {
    name: "知识库与数据",
    icon: Database,
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
    name: "插件与工具",
    icon: Puzzle,
    permissions: [
      { key: "skill:read", label: "查看技能" },
      { key: "skill:install", label: "安装技能" },
      { key: "skill:uninstall", label: "卸载技能" },
    ],
  },
  {
    name: "系统与管理",
    icon: Wrench,
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
    name: "项目管理",
    icon: FolderKanban,
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
    name: "审批与审核",
    icon: ClipboardCheck,
    permissions: [
      { key: "approval:submit", label: "提交审批" },
      { key: "approval:review", label: "审核内容" },
      { key: "approval:approve", label: "批准/驳回" },
      { key: "approval:view", label: "查看审批" },
    ],
  },
  {
    name: "文档与协作",
    icon: FileText,
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
    name: "工作流与模板",
    icon: Workflow,
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
    dashboard: LayoutGrid,
    knowledge: Database,
    model: Brain,
    plugin: Puzzle,
    system: Wrench,
    project: FolderKanban,
    approval: ClipboardCheck,
    document: FileText,
    workflow: Workflow,
    writing: FileText,
    docmgr: FileText,
    knowledge_factory: Brain,
    contract_price: FileText,
    output: FileText,
    workflow_admin: Workflow,
    admin: Shield,
    settings: Settings,
  };
  return map[key] ?? Shield;
}

function modulesToCategories(modules: RegistryModule[]) {
  return modules.map((m) => ({
    name: m.display_name,
    icon: getModuleIcon(m.key),
    permissions: m.permissions.map((p) => ({
      key: p.id,
      label: p.display_name,
    })),
  }));
}

function getAllPermKeys(modules: RegistryModule[]): string[] {
  return modules.flatMap((m) => m.permissions.map((p) => p.id));
}

/** Check whether any module in the registry has the pages array (v3 tree format). */
function hasPageTree(modules: RegistryModule[] | null | undefined): boolean {
  return !!(
    modules &&
    modules.length > 0 &&
    modules.some((m) => m.pages && m.pages.length > 0)
  );
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

/** 通配符展开：["*"] 表示全部权限，展开为所有操作 id（tree + direct + fallback）。 */
function expandWildcardPerms(
  perms: string[] | undefined,
  modules?: RegistryModule[] | null,
): string[] {
  if (!perms?.includes("*")) return perms ?? [];
  if (modules && modules.length > 0) {
    return hasPageTree(modules)
      ? getAllTreePermKeys(modules)
      : getAllPermKeys(modules);
  }
  return getAllFallbackPermKeys();
}

/* ── EAI-CUSTOM: Module key → nav_id mapping ─────────────── */
const MODULE_NAV_MAP: Record<string, string> = {
  dashboard: "nav:dashboard",
  writing: "nav:writing",
  projects: "nav:projects",
  docmgr: "nav:docmgr",
  knowledge: "nav:knowledge",
  knowledge_factory: "nav:knowledge-factory",
  contract_price: "nav:contract-price",
  output: "nav:output",
  workflow_admin: "nav:workflow-admin",
  admin: "nav:admin",
  settings: "nav:settings",
};

/** All known nav IDs from MODULE_NAV_MAP */
const ALL_NAV_IDS = Object.values(MODULE_NAV_MAP);

/** Derive nav_id from a module key, or null if not mapped */
function getNavIdForModule(key: string): string | null {
  return MODULE_NAV_MAP[key] ?? null;
}

/* ── Animated Permission Checkbox ─────────────────────────── */
function PermCheckbox({
  checked,
  disabled,
}: {
  checked: boolean;
  disabled?: boolean;
}) {
  return (
    <span
      className={cn(
        "relative inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] border-[1.5px] transition-all duration-200 ease-out select-none",
        checked
          ? "bg-primary border-primary shadow-[0_1px_4px_rgba(var(--color-primary),0.3)]"
          : "border-muted-foreground/30 bg-transparent",
        disabled && "pointer-events-none opacity-40",
      )}
    >
      <svg
        viewBox="0 0 14 14"
        fill="none"
        className="h-[11px] w-[11px]"
        aria-hidden="true"
      >
        <motion.path
          d="M3 7.5L5.8 10.2L11 4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={cn(
            checked ? "text-primary-foreground" : "text-transparent",
          )}
          initial={false}
          animate={
            checked
              ? { pathLength: 1, opacity: 1 }
              : { pathLength: 0, opacity: 0 }
          }
          transition={{ duration: 0.18, ease: "easeOut" }}
        />
      </svg>
      <AnimatePresence>
        {checked && (
          <motion.span
            className="bg-primary/30 absolute inset-0 rounded-[5px]"
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
  selected,
  onChange,
  readonly = false,
  compact = false,
  modules,
  enabledNavs,
  onNavToggle,
  enabledPages,
  onPageToggle,
}: {
  selected: string[];
  onChange: (perms: string[]) => void;
  readonly?: boolean;
  compact?: boolean;
  modules?: RegistryModule[] | null;
  /** EAI-CUSTOM: set of nav IDs (e.g. "nav:knowledge") that are visible */
  enabledNavs?: Set<string>;
  /** EAI-CUSTOM: called when a module nav toggle changes */
  onNavToggle?: (navId: string, enabled: boolean) => void;
  /** EAI-CUSTOM: set of visible page ids (sub-page visibility) */
  enabledPages?: Set<string>;
  /** EAI-CUSTOM: called when a sub-page visibility toggle changes */
  onPageToggle?: (pageId: string, enabled: boolean) => void;
}) {
  const defaultEnabledNavs = enabledNavs ?? new Set(ALL_NAV_IDS);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  // useMemo so the expanded-state effect below can depend on stable refs (recreated literals would loop the effect)
  const isTree = useMemo(() => hasPageTree(modules), [modules]);
  const treeModules: RegistryModule[] = useMemo(
    () => (isTree ? (modules ?? []) : []),
    [isTree, modules],
  );
  // EAI-CUSTOM: 隐藏无可配权限的模块（app_center pages=[] 始终可见无可配项 → 整卡隐藏）
  const visibleModules: RegistryModule[] = isTree
    ? treeModules.filter((m) => !shouldHideModule(m))
    : [];
  const categories = useMemo(
    () =>
      !isTree && modules && modules.length > 0
        ? modulesToCategories(modules)
        : !isTree
          ? PERMISSION_CATEGORIES
          : [],
    [isTree, modules],
  );
  const allPerms = isTree
    ? getAllTreePermKeys(treeModules)
    : modules && modules.length > 0
      ? getAllPermKeys(modules)
      : getAllFallbackPermKeys();
  // EAI-CUSTOM: 通配符展开 —— superadmin permissions=["*"] 表示全部权限，面板应全部勾选显示（resolveVisiblePages 对 pages 的 "*" 同理）
  const effectiveSelected = selected.includes("*") ? allPerms : selected;

  // Initialise expanded state
  useEffect(() => {
    if (isTree && treeModules.length > 0) {
      setExpandedCats(new Set(treeModules.map((m) => m.key)));
    } else {
      setExpandedCats(new Set(categories.map((c) => c.name)));
    }
  }, [isTree, treeModules, categories]);

  const toggleCat = (name: string) =>
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });

  const togglePerm = (key: string) => {
    if (readonly) return;
    onChange(
      effectiveSelected.includes(key)
        ? effectiveSelected.filter((p) => p !== key)
        : [...effectiveSelected, key],
    );
  };

  const toggleCategory = (keys: string[]) => {
    if (readonly) return;
    const allSelected = keys.every((k) => effectiveSelected.includes(k));
    if (allSelected)
      onChange(effectiveSelected.filter((p) => !keys.includes(p)));
    else onChange([...new Set([...effectiveSelected, ...keys])]);
  };

  // EAI-CUSTOM: 搜索 —— 匹配操作/模块名 → 自动展开命中模块 + 高亮
  const q = searchQuery.trim().toLowerCase();
  const highlight = (text: string): React.ReactNode => {
    if (!q) return text;
    const idx = text.toLowerCase().indexOf(q);
    if (idx < 0) return text;
    return (
      <>
        {text.slice(0, idx)}
        <mark className="bg-primary/20 text-primary rounded-sm px-0.5">
          {text.slice(idx, idx + q.length)}
        </mark>
        {text.slice(idx + q.length)}
      </>
    );
  };
  useEffect(() => {
    if (!q) return;
    if (isTree) {
      const hitModules = visibleModules.filter((mod) => {
        const pageOps = (mod.pages ?? []).flatMap((pg) =>
          pg.operations.map((op) => op.id),
        );
        const directOps = mod.permissions.map((p) => p.id);
        return [...pageOps, ...directOps].some(
          (id) =>
            id.toLowerCase().includes(q) ||
            (mod.display_name || "").toLowerCase().includes(q),
        );
      });
      if (hitModules.length > 0) {
        setExpandedCats(new Set(hitModules.map((m) => m.key)));
      }
    } else {
      const hitCats = categories.filter((c) =>
        c.permissions.some(
          (p) =>
            p.key.toLowerCase().includes(q) || c.name.toLowerCase().includes(q),
        ),
      );
      if (hitCats.length > 0) {
        setExpandedCats(new Set(hitCats.map((c) => c.name)));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const gridStyle = compact
    ? { gridTemplateColumns: "repeat(auto-fill, minmax(145px, 1fr))" }
    : { gridTemplateColumns: "repeat(auto-fill, minmax(185px, 1fr))" };

  return (
    <div className="space-y-3">
      {!readonly && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => onChange(allPerms)}
            className="group text-foreground/80 bg-background border-border hover:border-primary/40 hover:text-primary hover:bg-primary/[0.04] flex items-center gap-1.5 rounded-lg border px-3.5 py-1.5 text-xs font-semibold transition-all duration-200"
          >
            <PermCheckbox checked={false} />
            全选
          </button>
          <button
            type="button"
            onClick={() => onChange([])}
            className="text-muted-foreground bg-background border-border hover:border-destructive/30 hover:text-destructive/80 hover:bg-destructive/[0.03] rounded-lg border px-3.5 py-1.5 text-xs font-medium transition-all duration-200"
          >
            清空
          </button>
          <div className="relative ml-1 max-w-xs min-w-[160px] flex-1">
            <Search className="text-muted-foreground absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索操作..."
              className="h-8 pl-8 text-xs"
            />
          </div>
          <button
            type="button"
            onClick={() => {
              if (isTree)
                setExpandedCats(new Set(visibleModules.map((m) => m.key)));
              else setExpandedCats(new Set(categories.map((c) => c.name)));
            }}
            className="text-muted-foreground bg-background border-border hover:border-primary/40 hover:text-primary rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors"
          >
            全部展开
          </button>
          <button
            type="button"
            onClick={() => setExpandedCats(new Set())}
            className="text-muted-foreground bg-background border-border hover:border-primary/40 hover:text-primary rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors"
          >
            全部收起
          </button>
        </div>
      )}

      {isTree && visibleModules.length > 0
        ? /* ── 3-level tree rendering (v3 modules with pages) ── */
          visibleModules.map((mod) => {
            const isExpanded = expandedCats.has(mod.key);

            // Collect all operation IDs under this module (across all pages + direct)
            const hasPages = !!(mod.pages && mod.pages.length > 0);
            // EAI-CUSTOM: 单页模块折叠两级 —— 取唯一 page 供直接渲染
            const singlePage =
              isSinglePageModule(mod) && mod.pages ? mod.pages[0] : undefined;
            const pageOpIds: string[] = mod.pages
              ? mod.pages.flatMap((pg) => pg.operations.map((op) => op.id))
              : [];
            const directOpIds: string[] = mod.permissions.map((p) => p.id);
            const allOpIds = Array.from(
              new Set([...pageOpIds, ...directOpIds]),
            );
            const totalOps = allOpIds.length;
            const selectedCount = effectiveSelected.filter((k) =>
              allOpIds.includes(k),
            ).length;
            const allCatSelected =
              totalOps > 0 &&
              allOpIds.every((k) => effectiveSelected.includes(k));
            const ratio = totalOps > 0 ? selectedCount / totalOps : 0;
            const Icon = getModuleIcon(mod.key);
            const navId = getNavIdForModule(mod.key);
            const moduleVisible = navId ? defaultEnabledNavs.has(navId) : true;
            // EAI-CUSTOM: 可见性纯模块（所有子页无操作）→ 扁平子页网格，计数按可见子页数
            const visibilityOnly = isVisibilityOnlyModule(mod);
            const pageCount = mod.pages ? mod.pages.length : 0;
            const visiblePageCount = mod.pages
              ? mod.pages.filter((pg) =>
                  enabledPages ? enabledPages.has(pg.id) : true,
                ).length
              : 0;
            const pageRatio = pageCount > 0 ? visiblePageCount / pageCount : 0;

            return (
              <div
                key={mod.key}
                className="bg-card border-border overflow-hidden rounded-xl border"
              >
                {/* Module header */}
                <div className="flex w-full items-center">
                  <button
                    type="button"
                    onClick={() => toggleCat(mod.key)}
                    className="hover:bg-accent/60 flex flex-1 items-center gap-3 p-4 text-left transition-colors"
                  >
                    <div
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors duration-200",
                        (visibilityOnly
                          ? visiblePageCount > 0
                          : selectedCount > 0) && moduleVisible
                          ? "bg-primary/10 border-primary/20 border"
                          : "bg-muted border-border border",
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-4 w-4 transition-colors duration-200",
                          (visibilityOnly
                            ? visiblePageCount > 0
                            : selectedCount > 0) && moduleVisible
                            ? "text-primary"
                            : "text-muted-foreground",
                        )}
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-foreground text-sm font-medium">
                        {highlight(mod.display_name)}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2">
                        <span
                          className={cn(
                            "text-xs tabular-nums",
                            moduleVisible
                              ? "text-muted-foreground"
                              : "text-muted-foreground/50",
                          )}
                        >
                          {visibilityOnly
                            ? `可见 ${visiblePageCount}/${pageCount} 子页`
                            : `${selectedCount}/${totalOps}`}
                        </span>
                        <span className="bg-muted relative h-1 max-w-[80px] flex-1 overflow-hidden rounded-full">
                          <motion.span
                            className={cn(
                              "absolute inset-y-0 left-0 rounded-full",
                              moduleVisible
                                ? "bg-primary"
                                : "bg-muted-foreground/30",
                            )}
                            initial={false}
                            animate={{
                              width: `${(visibilityOnly ? pageRatio : ratio) * 100}%`,
                            }}
                            transition={{ duration: 0.3, ease: "easeOut" }}
                          />
                        </span>
                      </div>
                    </div>
                  </button>
                  {!readonly && totalOps > 0 && !visibilityOnly && (
                    <button
                      type="button"
                      onClick={() => {
                        if (moduleVisible) toggleCategory(allOpIds);
                      }}
                      disabled={!moduleVisible}
                      className={cn(
                        "mr-3 shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all duration-200",
                        !moduleVisible ? "cursor-not-allowed opacity-40" : "",
                        allCatSelected
                          ? "bg-primary/10 text-primary border-primary/20 hover:bg-primary/20 border"
                          : "bg-secondary/60 text-muted-foreground hover:bg-accent hover:text-foreground hover:border-border border border-transparent",
                      )}
                    >
                      {allCatSelected ? "取消全选" : "全选本组"}
                    </button>
                  )}
                  {/* EAI-CUSTOM: Module visibility toggle */}
                  {navId && onNavToggle && (
                    <div
                      className={cn(
                        "mr-3 flex shrink-0 items-center gap-1.5",
                        readonly ? "pointer-events-none opacity-50" : "",
                      )}
                    >
                      <span className="text-muted-foreground text-xs">
                        模块可见
                      </span>
                      <Switch
                        checked={moduleVisible}
                        onCheckedChange={(checked) =>
                          onNavToggle(navId, checked)
                        }
                        disabled={readonly}
                      />
                    </div>
                  )}
                  {/* EAI-CUSTOM: 展开/收起箭头置于卡片最右侧 */}
                  <button
                    type="button"
                    onClick={() => toggleCat(mod.key)}
                    className="text-muted-foreground hover:text-foreground hover:bg-accent/60 mr-1 flex h-full w-10 shrink-0 items-center justify-center rounded-lg transition-colors"
                    title={isExpanded ? "收起" : "展开"}
                  >
                    <motion.div
                      animate={{ rotate: isExpanded ? 0 : -90 }}
                      transition={{ duration: 0.2 }}
                    >
                      <ChevronDown className="h-4 w-4" />
                    </motion.div>
                  </button>
                </div>

                {/* Expanded content: pages with their operations */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      {/* EAI-CUSTOM: gray out + disable interaction when module not visible */}
                      <div
                        className={cn(
                          "px-3 pt-1 pb-3",
                          !moduleVisible && "pointer-events-none opacity-50",
                        )}
                      >
                        {visibilityOnly && onPageToggle ? (
                          /* 可见性纯模块：扁平子页卡片网格，每卡 = 名称 + 可见 Tag */
                          <div className="grid gap-1.5" style={gridStyle}>
                            {mod.pages!.map((page) => {
                              const pageVisible = enabledPages
                                ? enabledPages.has(page.id)
                                : true;
                              return (
                                <button
                                  key={page.id}
                                  type="button"
                                  onClick={() => {
                                    if (!readonly)
                                      onPageToggle(page.id, !pageVisible);
                                  }}
                                  disabled={readonly}
                                  className={cn(
                                    "flex min-w-0 items-center gap-2.5 rounded-lg p-2 text-sm transition-all duration-200 select-none",
                                    readonly
                                      ? "cursor-default"
                                      : "cursor-pointer",
                                    pageVisible
                                      ? "bg-primary/[0.04] border-primary/10 border"
                                      : "hover:bg-accent/50 hover:border-border border border-transparent",
                                  )}
                                >
                                  <span
                                    className={cn(
                                      "truncate leading-tight",
                                      readonly
                                        ? "text-muted-foreground"
                                        : pageVisible
                                          ? "text-foreground font-medium"
                                          : "text-foreground/70 group-hover/perm:text-foreground",
                                    )}
                                  >
                                    {highlight(page.display_name)}
                                  </span>
                                  <span
                                    className={cn(
                                      "ml-auto inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-xs font-medium",
                                      pageVisible
                                        ? "bg-primary/10 text-primary border-primary/20"
                                        : "bg-muted text-muted-foreground border-transparent",
                                    )}
                                  >
                                    <span
                                      className={cn(
                                        "h-1.5 w-1.5 rounded-full",
                                        pageVisible
                                          ? "bg-primary"
                                          : "bg-muted-foreground/50",
                                      )}
                                    />
                                    {pageVisible ? "可见" : "不可见"}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        ) : singlePage ? (
                          /* 单页模块：折叠两级，直接渲染该页操作网格（无子页行） */
                          <div className="grid gap-1.5" style={gridStyle}>
                            {singlePage.operations.length > 0 ? (
                              singlePage.operations.map((op) => {
                                const isChecked = effectiveSelected.includes(
                                  op.id,
                                );
                                return (
                                  <label
                                    key={op.id}
                                    className={cn(
                                      "group/perm flex min-w-0 items-center gap-2.5 rounded-lg p-2 text-sm transition-all duration-200 select-none",
                                      readonly
                                        ? "cursor-default"
                                        : "cursor-pointer",
                                      isChecked
                                        ? "bg-primary/[0.04] border-primary/10 border"
                                        : "hover:bg-accent/50 hover:border-border border border-transparent",
                                    )}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={isChecked}
                                      onChange={() => togglePerm(op.id)}
                                      disabled={readonly}
                                      className="peer sr-only"
                                    />
                                    <PermCheckbox
                                      checked={isChecked}
                                      disabled={readonly}
                                    />
                                    <span
                                      className={cn(
                                        "truncate leading-tight transition-colors duration-200",
                                        readonly
                                          ? "text-muted-foreground"
                                          : isChecked
                                            ? "text-foreground font-medium"
                                            : "text-foreground/70 group-hover/perm:text-foreground",
                                      )}
                                    >
                                      {highlight(op.display_name)}
                                    </span>
                                  </label>
                                );
                              })
                            ) : (
                              <div className="text-muted-foreground/50 px-1 py-2 text-xs">
                                暂无操作项
                              </div>
                            )}
                          </div>
                        ) : hasPages ? (
                          mod.pages!.map((page) => {
                            const pageHasOps = page.operations.length > 0;
                            const pageOpIds = page.operations.map(
                              (op) => op.id,
                            );
                            const pageSelected = effectiveSelected.filter((k) =>
                              pageOpIds.includes(k),
                            ).length;
                            const pageTotal = pageOpIds.length;
                            const pageVisible = enabledPages
                              ? enabledPages.has(page.id)
                              : true;
                            return (
                              <div key={page.id} className="mb-2 last:mb-0">
                                {/* Page header: icon + name + visible switch (right after text) + count */}
                                <div className="text-muted-foreground flex items-center gap-2 px-1 py-2 text-sm font-semibold">
                                  <FileText className="h-3.5 w-3.5 shrink-0 opacity-60" />
                                  <span className="truncate">
                                    {highlight(page.display_name)}
                                  </span>
                                  {onPageToggle && (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        if (!readonly)
                                          onPageToggle(page.id, !pageVisible);
                                      }}
                                      disabled={readonly}
                                      className={cn(
                                        "ml-1 inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-xs font-medium transition-colors",
                                        pageVisible
                                          ? "bg-primary/10 text-primary border-primary/20 hover:bg-primary/20"
                                          : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground border-transparent",
                                      )}
                                    >
                                      <span
                                        className={cn(
                                          "h-1.5 w-1.5 rounded-full",
                                          pageVisible
                                            ? "bg-primary"
                                            : "bg-muted-foreground/50",
                                        )}
                                      />
                                      {pageVisible ? "可见" : "不可见"}
                                    </button>
                                  )}
                                  {pageTotal > 0 && (
                                    <span className="text-muted-foreground/60 ml-1 text-xs tabular-nums">
                                      {pageSelected}/{pageTotal}
                                    </span>
                                  )}
                                </div>
                                {/* Operations grid — grayed + locked when page hidden */}
                                <div
                                  className={cn(
                                    pageVisible
                                      ? ""
                                      : "pointer-events-none opacity-40",
                                  )}
                                >
                                  {pageHasOps ? (
                                    <div
                                      className="grid gap-1.5"
                                      style={gridStyle}
                                    >
                                      {page.operations.map((op) => {
                                        const isChecked =
                                          effectiveSelected.includes(op.id);
                                        return (
                                          <label
                                            key={op.id}
                                            className={cn(
                                              "group/perm flex min-w-0 items-center gap-2.5 rounded-lg p-2 text-sm transition-all duration-200 select-none",
                                              readonly
                                                ? "cursor-default"
                                                : "cursor-pointer",
                                              isChecked
                                                ? "bg-primary/[0.04] border-primary/10 border"
                                                : "hover:bg-accent/50 hover:border-border border border-transparent",
                                            )}
                                          >
                                            <input
                                              type="checkbox"
                                              checked={isChecked}
                                              onChange={() => togglePerm(op.id)}
                                              disabled={readonly}
                                              className="peer sr-only"
                                            />
                                            <PermCheckbox
                                              checked={isChecked}
                                              disabled={readonly}
                                            />
                                            <span
                                              className={cn(
                                                "truncate leading-tight transition-colors duration-200",
                                                readonly
                                                  ? "text-muted-foreground"
                                                  : isChecked
                                                    ? "text-foreground font-medium"
                                                    : "text-foreground/70 group-hover/perm:text-foreground",
                                              )}
                                            >
                                              {op.display_name}
                                            </span>
                                          </label>
                                        );
                                      })}
                                    </div>
                                  ) : (
                                    <div className="text-muted-foreground/50 px-1 pb-2 text-xs">
                                      {pageVisible
                                        ? "暂无操作项"
                                        : "仅控制 tab 显隐"}
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          })
                        ) : /* Backward compat: module with no pages, show permissions directly */
                        totalOps > 0 ? (
                          <div className="grid gap-1.5" style={gridStyle}>
                            {mod.permissions.map((perm) => {
                              const isChecked = effectiveSelected.includes(
                                perm.id,
                              );
                              return (
                                <label
                                  key={perm.id}
                                  className={cn(
                                    "group/perm flex min-w-0 items-center gap-2.5 rounded-lg p-2 text-sm transition-all duration-200 select-none",
                                    readonly
                                      ? "cursor-default"
                                      : "cursor-pointer",
                                    isChecked
                                      ? "bg-primary/[0.04] border-primary/10 border"
                                      : "hover:bg-accent/50 hover:border-border border border-transparent",
                                  )}
                                >
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    onChange={() => togglePerm(perm.id)}
                                    disabled={readonly}
                                    className="peer sr-only"
                                  />
                                  <PermCheckbox
                                    checked={isChecked}
                                    disabled={readonly}
                                  />
                                  <span
                                    className={cn(
                                      "truncate leading-tight transition-colors duration-200",
                                      readonly
                                        ? "text-muted-foreground"
                                        : isChecked
                                          ? "text-foreground font-medium"
                                          : "text-foreground/70 group-hover/perm:text-foreground",
                                    )}
                                  >
                                    {highlight(perm.display_name)}
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="text-muted-foreground/50 px-1 py-2 text-xs">
                            暂无权限点
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })
        : /* ── Flat rendering (fallback / no pages) ── */
          categories.map((category) => {
            const Icon = category.icon;
            const isExpanded = expandedCats.has(category.name);
            const catKeys = category.permissions.map((p) => p.key);
            const selectedCount = effectiveSelected.filter((p) =>
              catKeys.includes(p),
            ).length;
            const allCatSelected = catKeys.every((k) =>
              effectiveSelected.includes(k),
            );
            const ratio = selectedCount / category.permissions.length;

            return (
              <div
                key={category.name}
                className="bg-card border-border overflow-hidden rounded-xl border"
              >
                <div className="flex w-full items-center">
                  <button
                    type="button"
                    onClick={() => toggleCat(category.name)}
                    className="hover:bg-accent/60 flex flex-1 items-center gap-3 p-4 text-left transition-colors"
                  >
                    <div
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors duration-200",
                        selectedCount > 0
                          ? "bg-primary/10 border-primary/20 border"
                          : "bg-muted border-border border",
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-4 w-4 transition-colors duration-200",
                          selectedCount > 0
                            ? "text-primary"
                            : "text-muted-foreground",
                        )}
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-foreground text-sm font-medium">
                        {category.name}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2">
                        <span className="text-muted-foreground text-xs tabular-nums">
                          {selectedCount}/{category.permissions.length}
                        </span>
                        <span className="bg-muted relative h-1 max-w-[80px] flex-1 overflow-hidden rounded-full">
                          <motion.span
                            className="bg-primary absolute inset-y-0 left-0 rounded-full"
                            initial={false}
                            animate={{ width: `${ratio * 100}%` }}
                            transition={{ duration: 0.3, ease: "easeOut" }}
                          />
                        </span>
                      </div>
                    </div>
                  </button>
                  {!readonly && (
                    <button
                      type="button"
                      onClick={() => toggleCategory(catKeys)}
                      className={cn(
                        "mr-3 shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all duration-200",
                        allCatSelected
                          ? "bg-primary/10 text-primary border-primary/20 hover:bg-primary/20 border"
                          : "bg-secondary/60 text-muted-foreground hover:bg-accent hover:text-foreground hover:border-border border border-transparent",
                      )}
                    >
                      {allCatSelected ? "取消全选" : "全选本组"}
                    </button>
                  )}
                  {/* EAI-CUSTOM: 展开/收起箭头置于卡片最右侧 */}
                  <button
                    type="button"
                    onClick={() => toggleCat(category.name)}
                    className="text-muted-foreground hover:text-foreground hover:bg-accent/60 mr-1 flex h-full w-10 shrink-0 items-center justify-center rounded-lg transition-colors"
                    title={isExpanded ? "收起" : "展开"}
                  >
                    <motion.div
                      animate={{ rotate: isExpanded ? 0 : -90 }}
                      transition={{ duration: 0.2 }}
                    >
                      <ChevronDown className="h-4 w-4" />
                    </motion.div>
                  </button>
                </div>

                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div
                        className="grid gap-1.5 px-3 pt-1 pb-3"
                        style={{
                          gridTemplateColumns: compact
                            ? "repeat(auto-fill, minmax(145px, 1fr))"
                            : "repeat(auto-fill, minmax(185px, 1fr))",
                        }}
                      >
                        {category.permissions.map((perm) => {
                          const isChecked = effectiveSelected.includes(
                            perm.key,
                          );
                          return (
                            <label
                              key={perm.key}
                              className={cn(
                                "group/perm flex min-w-0 items-center gap-2.5 rounded-lg p-2 text-sm transition-all duration-200 select-none",
                                readonly ? "cursor-default" : "cursor-pointer",
                                isChecked
                                  ? "bg-primary/[0.04] border-primary/10 border"
                                  : "hover:bg-accent/50 hover:border-border border border-transparent",
                              )}
                            >
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => togglePerm(perm.key)}
                                disabled={readonly}
                                className="peer sr-only"
                              />
                              <PermCheckbox
                                checked={isChecked}
                                disabled={readonly}
                              />
                              <span
                                className={cn(
                                  "truncate leading-tight transition-colors duration-200",
                                  readonly
                                    ? "text-muted-foreground"
                                    : isChecked
                                      ? "text-foreground font-medium"
                                      : "text-foreground/70 group-hover/perm:text-foreground",
                                )}
                              >
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
          })}
    </div>
  );
}

/* ── Matrix Overview: roles x permission categories ─────────── */
function RoleMatrixOverview({
  roles,
  modules,
}: {
  roles: Role[];
  modules?: RegistryModule[] | null;
}) {
  // EAI-CUSTOM: 矩阵同样隐藏无可配权限的模块（app_center）
  const matrixModules =
    modules && modules.length > 0
      ? modules.filter((m) => !shouldHideModule(m))
      : modules;
  const categories =
    matrixModules && matrixModules.length > 0
      ? modulesToCategories(matrixModules)
      : PERMISSION_CATEGORIES;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="bg-muted/60 text-foreground sticky left-0 border-r border-b px-3 py-2 text-left font-semibold">
              角色
            </th>
            {categories.map((cat) => (
              <th
                key={cat.name}
                className="text-muted-foreground border-b px-3 py-2 text-center font-medium whitespace-nowrap"
              >
                {cat.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {roles.map((role) => (
            <tr key={role.id} className="hover:bg-accent/40 transition-colors">
              <td className="bg-card text-foreground sticky left-0 border-r border-b px-3 py-2.5 font-medium whitespace-nowrap">
                <div className="flex items-center gap-1.5">
                  <Shield
                    className={cn(
                      "h-3.5 w-3.5",
                      role.is_system
                        ? "text-amber-500"
                        : "text-muted-foreground",
                    )}
                  />
                  <span>{role.name}</span>
                </div>
              </td>
              {categories.map((cat) => {
                const catKeys = cat.permissions.map((p) => p.key);
                // EAI-CUSTOM: 通配符展开 —— superadmin permissions=["*"] 视为全部权限
                const rolePerms = expandWildcardPerms(
                  role.permissions,
                  modules,
                );
                const count = catKeys.filter((k) =>
                  rolePerms.includes(k),
                ).length;
                const total = catKeys.length;
                const ratio = total > 0 ? count / total : 0;
                return (
                  <td
                    key={cat.name}
                    className="border-b px-3 py-2.5 text-center"
                  >
                    <div className="flex flex-col items-center gap-1">
                      <div
                        className="flex h-8 w-8 items-center justify-center rounded-lg text-[10px] font-bold"
                        style={{
                          backgroundColor:
                            ratio === 0
                              ? "var(--muted)"
                              : ratio >= 1
                                ? "rgba(34,197,94,0.15)"
                                : "rgba(59,130,246,0.15)",
                          color:
                            ratio === 0
                              ? "var(--muted-foreground)"
                              : ratio >= 1
                                ? "rgb(22,163,74)"
                                : "rgb(37,99,235)",
                        }}
                      >
                        {count}/{total}
                      </div>
                      {total > 0 && (
                        <div className="bg-muted h-1 w-10 overflow-hidden rounded-full">
                          <div
                            className={cn(
                              "h-full rounded-full",
                              ratio >= 1
                                ? "bg-green-500"
                                : ratio > 0
                                  ? "bg-blue-500"
                                  : "bg-transparent",
                            )}
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
  modules,
  selections,
  onChange,
  readonly,
}: {
  modules: RegistryModule[];
  selections: Record<string, string>;
  onChange: (selections: Record<string, string>) => void;
  readonly?: boolean;
}) {
  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">
        为各资源类型设置数据访问范围
      </p>
      {modules
        .filter((m) => m.data_scopes && m.data_scopes.length > 0)
        .map((module) => {
          const currentVal = selections[module.key] ?? "";
          return (
            <div
              key={module.key}
              className="bg-card border-border rounded-xl border p-4"
            >
              <div className="mb-3 flex items-center gap-3">
                <div className="bg-primary/10 border-primary/20 flex h-8 w-8 items-center justify-center rounded-lg border">
                  {(() => {
                    const Icon = getModuleIcon(module.key);
                    return <Icon className="text-primary h-4 w-4" />;
                  })()}
                </div>
                <span className="text-foreground text-sm font-medium">
                  {module.display_name}
                </span>
              </div>
              <div className="flex flex-wrap gap-3 pl-11">
                {/* EAI-CUSTOM: deny-by-default — 角色未配置该 module 的 scope 时无任何 radio 选中，明确提示未配置 */}
                {!currentVal && (
                  <span className="border-border text-muted-foreground/70 bg-muted/40 inline-flex items-center rounded-lg border border-dashed px-3 py-2 text-xs">
                    未配置（不授予该模块数据权限）
                  </span>
                )}
                {module.data_scopes.map((scope) => {
                  const isSelected = currentVal === scope.id;
                  return (
                    <label
                      key={scope.id}
                      className={cn(
                        "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-all duration-200",
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
                        onChange={() => {
                          if (!readonly)
                            onChange({ ...selections, [module.key]: scope.id });
                        }}
                        disabled={readonly}
                        className="sr-only"
                      />
                      <span
                        className={cn(
                          "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border-[1.5px]",
                          isSelected
                            ? "border-primary"
                            : "border-muted-foreground/40",
                        )}
                      >
                        {isSelected && (
                          <span className="bg-primary h-2 w-2 rounded-full" />
                        )}
                      </span>
                      <span>{scope.display_name}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          );
        })}
      {modules.filter((m) => m.data_scopes && m.data_scopes.length > 0)
        .length === 0 && (
        <div className="text-muted-foreground py-8 text-center text-sm">
          <Filter className="mx-auto mb-2 h-8 w-8 opacity-30" />
          暂无数据权限配置项
        </div>
      )}
    </div>
  );
}

/* ── Policies Panel ────────────────────────────────────────── */
// EAI-CUSTOM (T14): 策略编辑态 shape —— 在原 allow 字段外承载 deny 集合。
// deny 权限支持精确（kb:delete）与模块通配（kb:*）；deny 数据范围 id 必须在 registry 已声明。
type PolicyEditState = {
  name: string;
  conditions: PolicyCondition[];
  grants: PolicyGrant[];
  denyPermissions: string[];
  denyDataScopes: string[];
};

function PoliciesPanel({
  policies,
  policiesLoading,
  onToggle,
  onDelete,
  onSave,
  modules,
  roles,
}: {
  policies: PolicyItem[];
  policiesLoading: boolean;
  onToggle: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
  onAdd: () => void;
  onSave: (policy: PolicyItem) => void;
  modules: RegistryModule[];
  roles: Role[];
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<PolicyEditState>({
    name: "",
    conditions: [],
    grants: [],
    denyPermissions: [],
    denyDataScopes: [],
  });

  const startEdit = useCallback((policy?: PolicyItem) => {
    if (policy) {
      setEditingId(policy.id);
      // EAI-CUSTOM: 后端返回 conditions/grants 为引擎 dict，编辑前转回 UI 数组（toUIConditions/toGrantArray 对数组幂等）；
      // T14: deny 集合在 loadPolicies 已用 toDenyInfo 抽到 policy.denyPermissions/denyDataScopes，直接透传
      setEditForm({
        name: policy.name,
        conditions: toUIConditions(policy.conditions),
        grants: toGrantArray(policy.grants),
        denyPermissions: [...(policy.denyPermissions ?? [])],
        denyDataScopes: [...(policy.denyDataScopes ?? [])],
      });
    } else {
      setEditingId("__new__");
      setEditForm({
        name: "",
        conditions: [{ attribute: "", operator: "=", value: "" }],
        grants: [],
        denyPermissions: [],
        denyDataScopes: [],
      });
    }
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setEditForm({
      name: "",
      conditions: [],
      grants: [],
      denyPermissions: [],
      denyDataScopes: [],
    });
  }, []);

  const handleSave = useCallback(() => {
    onSave({
      id: editingId === "__new__" ? "" : (editingId ?? ""),
      name: editForm.name,
      enabled: true,
      conditions: editForm.conditions,
      grants: editForm.grants,
      denyPermissions: editForm.denyPermissions,
      denyDataScopes: editForm.denyDataScopes,
    });
    cancelEdit();
  }, [editingId, editForm, onSave, cancelEdit]);

  // Dedupe by id: the same permission point (e.g. export:generate) can be declared
  // under multiple modules; the dropdown keys SelectItems by p.id, so duplicates
  // would trigger React "two children with the same key".
  const allPermissions = modules
    .flatMap((m) => m.permissions)
    .filter((p, i, arr) => p && arr.findIndex((q) => q.id === p.id) === i);

  if (policiesLoading) {
    return (
      <div className="text-muted-foreground flex items-center justify-center py-12 text-sm">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        加载中...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-sm">
          管理全局访问策略（属性条件 + 权限授予），作用于所有角色
        </p>
        <button
          type="button"
          onClick={() => startEdit()}
          className="text-primary bg-primary/10 border-primary/20 hover:bg-primary/20 flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all"
        >
          <Plus className="h-3.5 w-3.5" /> 添加策略
        </button>
      </div>

      {/* Policy list */}
      {policies.length === 0 && editingId !== "__new__" && (
        <div className="text-muted-foreground bg-card border-border rounded-xl border py-12 text-center text-sm">
          <GripVertical className="mx-auto mb-2 h-8 w-8 opacity-30" />
          暂无自定义策略，点击&quot;添加策略&quot;创建
        </div>
      )}

      {policies.map((policy) => (
        <div
          key={policy.id}
          className={cn(
            "bg-card rounded-xl border p-4 transition-all",
            policy.enabled ? "border-border" : "border-border/50 opacity-60",
          )}
        >
          {editingId === policy.id ? (
            <PolicyEditForm
              form={editForm}
              onChange={setEditForm}
              onSave={handleSave}
              onCancel={cancelEdit}
              allPermissions={allPermissions}
              modules={modules}
              roles={roles}
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
        <div className="bg-card border-primary/30 ring-primary/10 rounded-xl border p-4 ring-1">
          <PolicyEditForm
            form={editForm}
            onChange={setEditForm}
            onSave={handleSave}
            onCancel={cancelEdit}
            allPermissions={allPermissions}
            modules={modules}
            roles={roles}
          />
        </div>
      )}
    </div>
  );
}

/* ── Policy Row (read-only) ────────────────────────────────── */
function PolicyRow({
  policy,
  onToggle,
  onDelete,
  onEdit,
  allPermissions,
}: {
  policy: PolicyItem;
  onToggle: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
  onEdit: () => void;
  allPermissions: PermissionItem[];
}) {
  // EAI-CUSTOM: 后端返回 grants 为引擎 dict {permissions:[...]}，渲染前统一转数组（兼容旧数据已是数组）
  const grantList = toGrantArray(policy.grants);
  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-foreground text-sm font-medium">
            {policy.name}
          </span>
          <button
            type="button"
            onClick={() => onToggle(policy.id, !policy.enabled)}
            className={cn(
              "flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors",
              policy.enabled
                ? "bg-success/10 text-success border-success/30"
                : "bg-muted text-muted-foreground border-border",
            )}
          >
            {policy.enabled ? (
              <>
                <Eye className="h-3 w-3" /> 已启用
              </>
            ) : (
              <>
                <EyeOff className="h-3 w-3" /> 已禁用
              </>
            )}
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onEdit}
            className="text-muted-foreground hover:text-foreground hover:bg-accent rounded p-1.5 transition-colors"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onDelete(policy.id)}
            className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded p-1.5 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      {/* Conditions summary */}
      {policy.conditions.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {policy.conditions.map((c, i) =>
            c.attribute === "__or__" ? (
              // EAI-CUSTOM (P0): or 树只读徽章 —— 不误显"全局"
              <span
                key={i}
                className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-600"
              >
                ⚠ 或(OR) 条件（只读）
              </span>
            ) : (
              <span
                key={i}
                className="bg-muted text-muted-foreground rounded px-2 py-0.5 font-mono text-[11px]"
              >
                {(ATTR_LABELS[c.attribute] ?? c.attribute) || "?"}{" "}
                {OP_LABELS[c.operator] ?? c.operator} {c.value || "?"}
              </span>
            ),
          )}
        </div>
      ) : (
        // EAI-CUSTOM (T14): 空条件 = 引擎无条件=作用于所有非超管用户，显式提示避免误读为"未配置"
        <div className="mt-2">
          <span className="bg-muted text-muted-foreground border-border rounded border border-dashed px-2 py-0.5 text-[11px]">
            （全局·所有非超管用户）
          </span>
        </div>
      )}
      {/* Grants summary (allow) */}
      {grantList.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {grantList.map((g, i) => {
            const permLabel =
              allPermissions.find((p) => p.id === g.permission)?.display_name ??
              g.permission;
            return (
              // EAI-CUSTOM (T14): 删除 grant.data_scope 显示 —— 引擎不消费 grants.data_scope，
              // 数据级 deny 走 deny_data_scopes；保留旧数据兼容但不再展示误导性后缀
              <span
                key={i}
                className="bg-primary/[0.06] text-primary border-primary/10 rounded border px-2 py-0.5 text-[11px] font-medium"
              >
                {permLabel}
              </span>
            );
          })}
        </div>
      )}
      {/* Deny summary (T14) — warning 色，与 allow 视觉区分 */}
      {(policy.denyPermissions?.length ?? 0) > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span className="text-warning inline-flex items-center gap-1 text-[11px] font-medium">
            <AlertTriangle className="h-3 w-3" />
            拒绝权限:
          </span>
          {policy.denyPermissions!.map((perm, i) => {
            const permLabel =
              allPermissions.find((p) => p.id === perm)?.display_name ?? perm;
            return (
              <span
                key={i}
                className="bg-warning/10 text-warning border-warning/30 rounded border px-2 py-0.5 text-[11px] font-medium"
              >
                {permLabel}
              </span>
            );
          })}
        </div>
      )}
      {(policy.denyDataScopes?.length ?? 0) > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span className="text-warning inline-flex items-center gap-1 text-[11px] font-medium">
            <AlertTriangle className="h-3 w-3" />
            拒绝范围:
          </span>
          {policy.denyDataScopes!.map((scope, i) => (
            <span
              key={i}
              className="bg-warning/10 text-warning border-warning/30 rounded border px-2 py-0.5 font-mono text-[11px]"
            >
              {scope}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Policy Edit Form ──────────────────────────────────────── */
/** EAI-CUSTOM: 授权权限选择对话框 —— 按 页面(模块) → 子页 → 操作 三级浏览单选（替代扁平下拉） */
// EAI-CUSTOM: 三态 checkbox（勾选/半选/未选）—— 级联权限树节点用
function TriCheckbox({
  checked,
  indeterminate,
  disabled,
  label,
  onChange,
}: {
  checked: boolean;
  indeterminate?: boolean;
  disabled?: boolean;
  label?: string;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={indeterminate ? "mixed" : checked}
      aria-label={label}
      disabled={disabled}
      onClick={onChange}
      className={cn(
        "flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors",
        checked
          ? "bg-primary border-primary"
          : indeterminate
            ? "bg-primary/25 border-primary/50"
            : "border-muted-foreground/40 hover:border-primary/40",
        disabled && "cursor-not-allowed opacity-40",
      )}
    >
      {checked ? (
        <span className="text-[10px] leading-none text-white">✓</span>
      ) : indeterminate ? (
        <span className="bg-primary/70 h-0.5 w-2" />
      ) : null}
    </button>
  );
}

// EAI-CUSTOM: 授权 = 完整访问单元 —— 操作 + page:<id>(页面可见) + nav:<id>(模块可见)。
// 级联：勾操作自动带出页面/模块可见；勾页面=可见+全操作；勾模块=可见+全部子项。三态半选表示部分选中。
function GrantPermissionDropdown({
  open,
  onOpenChange,
  modules,
  selected,
  onChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  modules: RegistryModule[];
  selected: string[];
  onChange: (permissionIds: string[]) => void;
}) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggleExpand = (key: string) =>
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  const match = (op: OperationItem) =>
    !search || op.display_name.includes(search) || op.id.includes(search);
  const isExpanded = (key: string) => expanded.has(key) || !!search; // 搜索时自动展开

  const perms = new Set(selected);
  const ops = new Set(
    [...perms].filter((p) => !p.startsWith("page:") && !p.startsWith("nav:")),
  );
  const pages = new Set(
    [...perms].filter((p) => p.startsWith("page:")).map((p) => p.slice(5)),
  );
  const navs = new Set(
    [...perms].filter((p) => p.startsWith("nav:")).map((p) => p.slice(4)),
  );

  const pageState = (page: {
    id: string;
    operations: OperationItem[];
  }): "checked" | "indeterminate" | "unchecked" => {
    const opIds = (page.operations || []).map((o) => o.id);
    const grantedCount = opIds.filter((o) => ops.has(o)).length;
    if (pages.has(page.id) && grantedCount === opIds.length) return "checked";
    if (pages.has(page.id) || grantedCount > 0) return "indeterminate";
    return "unchecked";
  };
  const moduleState = (
    mod: RegistryModule,
  ): "checked" | "indeterminate" | "unchecked" => {
    const navId = getNavIdForModule(mod.key);
    if (!navId) return "unchecked";
    const modPages = mod.pages ?? [];
    const allChecked =
      modPages.length > 0 && modPages.every((p) => pageState(p) === "checked");
    const anyGranted = modPages.some(
      (p) => pages.has(p.id) || (p.operations || []).some((o) => ops.has(o.id)),
    );
    if (navs.has(navId) && allChecked) return "checked";
    if (navs.has(navId) || anyGranted) return "indeterminate";
    return "unchecked";
  };

  const toggleOp = (
    opId: string,
    pageId: string | null | undefined,
    navId: string | null | undefined,
  ) => {
    const next = new Set(perms);
    if (next.has(opId)) next.delete(opId);
    else {
      next.add(opId);
      if (pageId) next.add(`page:${pageId}`);
      if (navId) next.add(`nav:${navId}`);
    }
    onChange([...next]);
  };
  const togglePage = (
    page: { id: string; operations: OperationItem[] },
    navId: string | null | undefined,
  ) => {
    const opIds = (page.operations || []).map((o) => o.id);
    const next = new Set(perms);
    const isFull = pages.has(page.id) && opIds.every((o) => ops.has(o));
    if (isFull) {
      next.delete(`page:${page.id}`);
      for (const o of opIds) next.delete(o);
    } else {
      next.add(`page:${page.id}`);
      for (const o of opIds) next.add(o);
      if (navId) next.add(`nav:${navId}`);
    }
    onChange([...next]);
  };
  const toggleModule = (mod: RegistryModule, navId: string) => {
    const modPages = mod.pages ?? [];
    const allOpIds = modPages.flatMap((p) =>
      (p.operations || []).map((o) => o.id),
    );
    const allPageIds = modPages.map((p) => p.id);
    const next = new Set(perms);
    const isFull =
      navs.has(navId) &&
      modPages.length > 0 &&
      modPages.every((p) => pageState(p) === "checked");
    if (isFull) {
      next.delete(`nav:${navId}`);
      for (const p of allPageIds) next.delete(`page:${p}`);
      for (const o of allOpIds) next.delete(o);
    } else {
      next.add(`nav:${navId}`);
      for (const p of allPageIds) next.add(`page:${p}`);
      for (const o of allOpIds) next.add(o);
    }
    onChange([...next]);
  };

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="border-input bg-background hover:border-input hover:bg-muted focus:ring-primary/50 focus:border-primary flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm transition-colors focus:ring-2 focus:outline-none"
        >
          <span
            className={cn(
              selected.length > 0 ? "text-foreground" : "text-muted-foreground",
            )}
          >
            {selected.length > 0
              ? `已选 ${selected.length} 项（含页面/模块可见）`
              : "选择权限（多选）"}
          </span>
          <ChevronDown className="text-muted-foreground h-4 w-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="bg-background border-border w-[30rem] rounded-lg border p-0 shadow-lg"
        align="start"
      >
        <div className="border-border border-b p-2">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索权限名称或代码…"
            className="h-8 text-xs"
          />
        </div>
        <div className="max-h-64 space-y-1 overflow-y-auto p-2">
          {modules
            .filter(
              (m) =>
                !search ||
                m.display_name.includes(search) ||
                (m.pages ?? []).some((pg) => pg.operations.some(match)),
            )
            .map((mod) => {
              const navId = getNavIdForModule(mod.key);
              const mState = moduleState(mod);
              return (
                <div
                  key={mod.key}
                  className="border-border/60 border-b py-1 last:border-0"
                >
                  <div className="flex w-full items-center gap-1.5">
                    <TriCheckbox
                      checked={mState === "checked"}
                      indeterminate={mState === "indeterminate"}
                      disabled={!navId}
                      label={mod.display_name}
                      onChange={() => navId && toggleModule(mod, navId)}
                    />
                    <button
                      type="button"
                      onClick={() => toggleExpand(mod.key)}
                      className="text-foreground hover:text-primary flex flex-1 items-center gap-1.5 py-1 text-sm font-semibold transition-colors"
                    >
                      <ChevronRight
                        className={cn(
                          "text-muted-foreground h-3.5 w-3.5 transition-transform",
                          isExpanded(mod.key) && "rotate-90",
                        )}
                      />
                      {mod.display_name}
                    </button>
                  </div>
                  {isExpanded(mod.key) &&
                    (mod.pages ?? []).map((page) => {
                      const pState = pageState(page);
                      return (
                        <div key={page.id} className="mb-2 ml-7">
                          <div className="flex items-center gap-1.5">
                            <TriCheckbox
                              checked={pState === "checked"}
                              indeterminate={pState === "indeterminate"}
                              label={page.display_name}
                              onChange={() => togglePage(page, navId)}
                            />
                            <span className="text-muted-foreground text-xs font-medium">
                              {page.display_name}
                            </span>
                          </div>
                          {page.operations.length > 0 ? (
                            <div className="mt-1 ml-6 flex flex-wrap gap-1.5">
                              {page.operations.filter(match).map((op) => {
                                const checked = ops.has(op.id);
                                return (
                                  <button
                                    key={op.id}
                                    type="button"
                                    onClick={() =>
                                      toggleOp(op.id, page.id, navId)
                                    }
                                    className={cn(
                                      "inline-flex items-center gap-1 rounded border px-2 py-1 text-sm transition-colors",
                                      checked
                                        ? "bg-primary/10 border-primary/40 text-primary font-medium"
                                        : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground",
                                    )}
                                  >
                                    <span
                                      className={cn(
                                        "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[2px] border",
                                        checked
                                          ? "bg-primary border-primary"
                                          : "border-muted-foreground/40",
                                      )}
                                    >
                                      {checked && (
                                        <span className="text-[10px] leading-none text-white">
                                          ✓
                                        </span>
                                      )}
                                    </span>
                                    {op.display_name}
                                  </button>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="text-muted-foreground/50 ml-6 text-[11px]">
                              暂无操作项
                            </div>
                          )}
                        </div>
                      );
                    })}
                </div>
              );
            })}
        </div>
        <div className="border-border flex items-center justify-between gap-2 border-t p-2">
          <span className="text-muted-foreground text-xs">
            已选 {selected.length} 项（勾选页面/模块 = 可见 + 操作级联）
          </span>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="bg-primary text-primary-foreground hover:bg-primary/90 h-8 rounded-lg px-4 text-xs font-medium transition-colors"
          >
            完成
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function PolicyEditForm({
  form,
  onChange,
  onSave,
  onCancel,
  allPermissions,
  modules,
  roles,
}: {
  form: PolicyEditState;
  onChange: (f: PolicyEditState) => void;
  onSave: () => void;
  onCancel: () => void;
  allPermissions: PermissionItem[];
  modules: RegistryModule[];
  roles: Role[];
}) {
  // EAI-CUSTOM: 条件值下拉建议 —— 按所选属性给 datalist 选项（可输入可点选），避免纯手输体验差。
  // role_code/role_level 来自已加载 roles；username/user_id/dept_id 懒加载用户/部门。
  const [users, setUsers] = useState<User[]>([]);
  const [depts, setDepts] = useState<Department[]>([]);
  const [projects, setProjects] = useState<Array<{ id: string; name: string }>>(
    [],
  ); // EAI-CUSTOM (P0): member_projects 值选项
  // EAI-CUSTOM: 条件值 tag-input —— 徽章式（可输入可点选、徽章带叉可删）；单值操作符仅 1 个徽章，in/not_in 可多个
  const [chipDrafts, setChipDrafts] = useState<Record<number, string>>({});
  const [chipOpens, setChipOpens] = useState<Record<number, boolean>>({});
  const chipsOf = (i: number): string[] =>
    (form.conditions[i]?.value ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  const isMultiRow = (i: number) =>
    form.conditions[i]?.operator === "in" ||
    form.conditions[i]?.operator === "not_in";
  const addChip = (i: number, raw: string) => {
    const v = String(raw ?? "").trim();
    if (!v) return;
    const opts = attrValueOptions(form.conditions[i]?.attribute ?? "");
    const canonical = opts.find((o) => o.value === v)?.value ?? v;
    const cur = chipsOf(i);
    const next = isMultiRow(i)
      ? cur.includes(canonical)
        ? cur
        : [...cur, canonical]
      : [canonical];
    updateCondition(i, { value: next.join(",") });
    setChipDrafts((d) => ({ ...d, [i]: "" }));
    setChipOpens((o) => ({ ...o, [i]: false }));
  };
  const removeChip = (i: number, v: string) =>
    updateCondition(i, {
      value: chipsOf(i)
        .filter((x) => x !== v)
        .join(","),
    });
  // EAI-CUSTOM: 授权权限选择器 —— 多选树形下拉（页面→子页→操作），grantPickerOpen 控制展开
  const [grantPickerOpen, setGrantPickerOpen] = useState(false);
  useEffect(() => {
    let active = true;
    userApi
      .list({ limit: 500 })
      .then((r) => {
        if (active) setUsers(r.users ?? []);
      })
      .catch(() => {
        /* suggestions optional */
      });
    deptApi
      .list()
      .then((r) => {
        if (active) setDepts(r.departments ?? []);
      })
      .catch(() => {
        /* suggestions optional */
      });
    projectApi
      .list({ limit: 500 })
      .then((r) => {
        if (active) setProjects(r.projects ?? []);
      })
      .catch(() => {
        /* suggestions optional */
      });
    return () => {
      active = false;
    };
  }, []);

  const attrValueOptions = (
    attr: string,
  ): { value: string; label: string }[] => {
    switch (attr) {
      case "role_code":
        return (roles || []).map((r) => ({
          value: r.code,
          label: r.name || r.code,
        }));
      case "role_level":
        return Array.from(
          new Set(
            (roles || []).map((r) => String(r.level ?? "")).filter(Boolean),
          ),
        )
          .sort()
          .map((lv) => ({ value: lv, label: lv }));
      case "username":
        return users.map((u) => ({
          value: u.username,
          label: u.full_name ?? u.username,
        }));
      case "user_id":
        return users.map((u) => ({
          value: u.id,
          label: u.full_name ?? u.username,
        }));
      case "dept_id":
        return depts.map((d) => ({ value: d.id, label: d.name }));
      case "dept_ids":
        return depts.map((d) => ({ value: d.id, label: d.name })); // EAI-CUSTOM (P0): 多值部门
      case "member_projects":
        return projects.map((p) => ({ value: p.id, label: p.name })); // EAI-CUSTOM (P0): 多值项目成员
      case "tags": {
        // EAI-CUSTOM (标签池): 派生 role:/dept: 标签（与后端 DefaultTagResolver 对齐）+ COMMON_TAGS 业务标签
        return [
          ...(roles || []).map((r) => ({
            value: `role:${r.code}`,
            label: `角色:${r.name || r.code}`,
          })),
          ...depts.map((d) => ({
            value: `dept:${d.name}`,
            label: `部门:${d.name}`,
          })),
          ...COMMON_TAGS.map((t) => ({ value: t, label: t })),
        ];
      }
      default:
        return [];
    }
  };
  const addCondition = () =>
    onChange({
      ...form,
      conditions: [
        ...form.conditions,
        { attribute: "", operator: "=", value: "" },
      ],
    });
  const removeCondition = (i: number) =>
    onChange({
      ...form,
      conditions: form.conditions.filter((_, idx) => idx !== i),
    });
  const updateCondition = (i: number, f: Partial<PolicyCondition>) => {
    const conds = [...form.conditions];
    conds[i] = { ...conds[i]!, ...f };
    onChange({ ...form, conditions: conds });
  };

  const removeGrant = (i: number) =>
    onChange({ ...form, grants: form.grants.filter((_, idx) => idx !== i) });
  // EAI-CUSTOM: 授权标签显示 —— 操作显示权限名，page:<id>/nav:<id> 显示页面/模块名
  const permLabel = (permission: string) => {
    if (permission.startsWith("page:")) {
      const pid = permission.slice(5);
      for (const m of modules)
        for (const pg of m.pages ?? [])
          if (pg.id === pid) return pg.display_name;
      return permission;
    }
    if (permission.startsWith("nav:")) {
      const nid = permission.slice(4);
      const m = modules.find((mm) => getNavIdForModule(mm.key) === nid);
      return m ? m.display_name : permission;
    }
    return (
      allPermissions.find((p) => p.id === permission)?.display_name ??
      permission
    );
  };
  // EAI-CUSTOM: 授权标签层级区分 —— 模块(indigo)/页面(sky)/操作(primary) 颜色 + 层级前缀
  const grantChipMeta = (
    permission: string,
  ): { level: string; cls: string } => {
    if (permission.startsWith("nav:"))
      return {
        level: "模块",
        cls: "bg-indigo-500/10 text-indigo-500 border-indigo-500/20",
      };
    if (permission.startsWith("page:"))
      return {
        level: "页面",
        cls: "bg-sky-500/10 text-sky-500 border-sky-500/20",
      };
    return {
      level: "操作",
      cls: "bg-primary/10 text-primary border-primary/10",
    };
  };

  // EAI-CUSTOM (T14→升级): deny 权限改搜索式分组 Combobox（Popover+Command）。
  // 仍支持精确（kb:delete）与通配（kb:*）；通配按 id 首段（prefix）匹配（见 engine.py deny 逻辑）。
  const [denySearch, setDenySearch] = useState("");
  const [denyPopoverOpen, setDenyPopoverOpen] = useState(false);
  // 按 prefix 分组：每组 = 精确操作 + 一条 <prefix>:* 通配
  const denyGroups = useMemo(() => {
    const map = new Map<string, PermissionItem[]>();
    for (const p of allPermissions) {
      const prefix = p.id.split(":")[0]!; // ponytail: id 形如 "<prefix>:<action>"，首段必存在
      if (!map.has(prefix)) map.set(prefix, []);
      map.get(prefix)!.push(p);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [allPermissions]);
  const allDenyChoices = useMemo(() => {
    const s = new Set<string>(allPermissions.map((p) => p.id));
    for (const [prefix] of denyGroups) s.add(`${prefix}:*`);
    return s;
  }, [allPermissions, denyGroups]);
  const addDenyPermissionValue = (v: string) => {
    const trimmed = v.trim();
    if (trimmed && !form.denyPermissions.includes(trimmed)) {
      onChange({
        ...form,
        denyPermissions: [...form.denyPermissions, trimmed],
      });
    }
    setDenySearch("");
    setDenyPopoverOpen(false);
  };
  const removeDenyPermission = (perm: string) =>
    onChange({
      ...form,
      denyPermissions: form.denyPermissions.filter((p) => p !== perm),
    });

  const toggleDenyDataScope = (scopeId: string) => {
    const has = form.denyDataScopes.includes(scopeId);
    onChange({
      ...form,
      denyDataScopes: has
        ? form.denyDataScopes.filter((s) => s !== scopeId)
        : [...form.denyDataScopes, scopeId],
    });
  };

  // EAI-CUSTOM: 条件属性白名单与引擎 AttributeSet 对齐（role_code/username 均为有效 identity 属性）。
  // 缺则 API/脚本建的 role_code 等条件在编辑下拉里显示空，保存会丢 attr。
  const ATTR_OPTIONS = [
    "role_code",
    "username",
    "tags",
    "role_level",
    "dept_id",
    "dept_ids",
    "member_projects",
    "user_id",
  ];
  const OP_OPTIONS = ["=", "!=", "contains", ">=", "<=", "in", "not_in"];

  // T14: 仅有 data_scopes 声明的 module 才出现到 deny 数据范围多选里
  const scopeModules = modules.filter(
    (m) => m.data_scopes && m.data_scopes.length > 0,
  );

  return (
    <div className="space-y-4">
      <div>
        <label className="text-foreground mb-1 block text-xs font-medium">
          策略名称
        </label>
        <input
          type="text"
          value={form.name}
          onChange={(e) => onChange({ ...form, name: e.target.value })}
          placeholder="例如：仅限高级用户访问"
          className="bg-background border-input focus:ring-primary/50 w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
        />
      </div>

      {/* Conditions */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <label className="text-foreground text-xs font-medium">
            条件 (Conditions)
          </label>
          <button
            type="button"
            onClick={addCondition}
            className="text-primary hover:text-primary/80 text-xs font-medium"
          >
            + 添加条件
          </button>
        </div>
        <div className="space-y-2">
          {form.conditions.map((c, i) => (
            <div key={i} className="flex items-center gap-2">
              {c.attribute === "__or__" ? (
                // EAI-CUSTOM (P0): or 树只读徽章 —— 不可编辑，保存保留原条件
                <span className="inline-flex items-center gap-1 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-600">
                  ⚠ 或(OR) 条件（只读，保存将保留原条件）
                </span>
              ) : (
                <>
                  <Select
                    value={c.attribute || "__none__"}
                    onValueChange={(v) =>
                      updateCondition(i, {
                        attribute: v === "__none__" ? "" : v,
                      })
                    }
                  >
                    <SelectTrigger className="h-8 w-[130px] text-sm">
                      <SelectValue placeholder="属性" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">
                        <span className="text-muted-foreground">选择属性</span>
                      </SelectItem>
                      {ATTR_OPTIONS.map((a) => (
                        <SelectItem key={a} value={a}>
                          {ATTR_LABELS[a] ?? a}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={c.operator}
                    onValueChange={(v) => {
                      // EAI-CUSTOM: 切到单值操作符(=/!=/>=/<=/contains)时清空值，避免 in/not_in 的多值残留
                      const isMultiOp = v === "in" || v === "not_in";
                      updateCondition(i, {
                        operator: v,
                        value: isMultiOp ? c.value : "",
                      });
                    }}
                  >
                    <SelectTrigger className="h-8 w-[100px] text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {OP_OPTIONS.map((o) => (
                        <SelectItem key={o} value={o}>
                          {OP_LABELS[o] ?? o}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {(() => {
                    // EAI-CUSTOM: 条件值 tag-input —— 徽章式（输入回车或点选建议添加；徽章带叉删除）；
                    // 单值操作符仅 1 个徽章，in/not_in 可多个（值=逗号连接，引擎 in/not_in 即列表）
                    const opts = attrValueOptions(c.attribute);
                    const chips = chipsOf(i);
                    const draft = chipDrafts[i] ?? "";
                    const filtered = opts.filter(
                      (o) =>
                        !chips.includes(o.value) &&
                        (!draft ||
                          o.label.includes(draft) ||
                          o.value.includes(draft)),
                    );
                    const labelOf = (v: string) =>
                      opts.find((o) => o.value === v)?.label ?? v;
                    return (
                      <div className="relative flex-1">
                        <div className="bg-background border-input focus-within:ring-primary/50 flex min-h-8 flex-wrap items-center gap-1 rounded border px-2 py-0.5 focus-within:ring-2">
                          {chips.map((v) => (
                            <span
                              key={v}
                              className="bg-primary/10 text-primary border-primary/20 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px]"
                            >
                              {labelOf(v)}
                              <button
                                type="button"
                                onClick={() => removeChip(i, v)}
                                title="删除"
                                className="hover:text-destructive transition-colors"
                              >
                                <X className="h-3 w-3" />
                              </button>
                            </span>
                          ))}
                          <input
                            type="text"
                            className="placeholder:text-muted-foreground h-6 min-w-[70px] flex-1 bg-transparent text-sm outline-none"
                            value={draft}
                            placeholder={chips.length ? "" : "输入或选择值"}
                            onChange={(e) =>
                              setChipDrafts((d) => ({
                                ...d,
                                [i]: e.target.value,
                              }))
                            }
                            onFocus={() =>
                              setChipOpens((o) => ({ ...o, [i]: true }))
                            }
                            onBlur={() =>
                              setTimeout(
                                () =>
                                  setChipOpens((o) => ({ ...o, [i]: false })),
                                150,
                              )
                            }
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                addChip(i, draft);
                              }
                              if (
                                e.key === "Backspace" &&
                                !draft &&
                                chips.length
                              )
                                removeChip(i, chips[chips.length - 1]!);
                            }}
                          />
                        </div>
                        {chipOpens[i] && filtered.length > 0 && (
                          <div className="bg-popover border-border absolute top-full right-0 left-0 z-20 mt-1 max-h-48 overflow-y-auto rounded-md border py-1 shadow-md">
                            {filtered.map((o) => (
                              <button
                                key={o.value}
                                type="button"
                                onMouseDown={(e) => {
                                  e.preventDefault();
                                  addChip(i, o.value);
                                }}
                                className="hover:bg-accent block w-full px-3 py-1.5 text-left text-xs"
                              >
                                {o.label}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </>
              )}
              <button
                onClick={() => removeCondition(i)}
                disabled={c.attribute === "__or__"}
                className="text-muted-foreground hover:text-destructive p-1 transition-colors disabled:opacity-30"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Grants —— 完整访问单元（操作 + 页面/模块可见），级联 checkbox */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <label className="text-foreground text-xs font-medium">
            权限授予 (Grants)
          </label>
          <span className="text-muted-foreground text-xs">
            {form.grants.length > 0 ? `已选 ${form.grants.length} 项` : ""}
          </span>
        </div>
        {form.grants.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {form.grants.map((g, i) => {
              const { level, cls } = grantChipMeta(g.permission);
              return (
                <span
                  key={g.permission}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-sm",
                    cls,
                  )}
                >
                  <span className="text-[10px] font-semibold opacity-70">
                    {level}
                  </span>
                  {permLabel(g.permission)}
                  <button
                    type="button"
                    onClick={() => removeGrant(i)}
                    className="opacity-70 hover:opacity-100"
                    title="删除"
                  >
                    ×
                  </button>
                </span>
              );
            })}
          </div>
        )}
        <GrantPermissionDropdown
          open={grantPickerOpen}
          onOpenChange={setGrantPickerOpen}
          modules={modules}
          selected={form.grants.map((g) => g.permission)}
          onChange={(ids) =>
            onChange({
              ...form,
              grants: ids.map((permission) => ({ permission })),
            })
          }
        />
      </div>

      {/* Deny (T14) — warning 色，与 allow 视觉区分；无二次确认（设计决策：警告色 + 审计日志即可） */}
      <div className="border-warning/40 bg-warning/[0.04] space-y-3 rounded-lg border p-3">
        <div className="text-warning flex items-center gap-1.5">
          <AlertTriangle className="h-3.5 w-3.5" />
          <span className="text-xs font-semibold">拒绝 (Deny)</span>
          <span className="text-warning/70 text-[10px] font-normal">
            命中即拒绝，优先于 allow
          </span>
        </div>

        {/* 拒绝权限 — 精确 (kb:delete) 或模块通配 (kb:*) */}
        <div>
          <label className="text-foreground/80 mb-1 block text-[11px] font-medium">
            拒绝权限
          </label>
          <Popover open={denyPopoverOpen} onOpenChange={setDenyPopoverOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="bg-background border-warning/30 text-muted-foreground hover:border-warning/50 flex h-8 w-full items-center gap-2 rounded border px-2 text-xs transition-colors"
              >
                <Search className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">搜索 / 选择拒绝权限…</span>
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-[420px] p-0" align="start">
              <Command shouldFilter={false}>
                <CommandInput
                  value={denySearch}
                  onValueChange={setDenySearch}
                  placeholder="搜索权限名称或代码（如 删除 / 知识库 / kb）…"
                  className="h-9"
                />
                <CommandList className="max-h-[280px]">
                  <CommandEmpty>无匹配权限</CommandEmpty>
                  {(() => {
                    const q = denySearch.trim().toLowerCase();
                    const groups = q
                      ? denyGroups
                          .map(
                            ([prefix, perms]) =>
                              [
                                prefix,
                                perms.filter(
                                  (p) =>
                                    p.id.toLowerCase().includes(q) ||
                                    p.display_name.toLowerCase().includes(q),
                                ),
                              ] as [string, PermissionItem[]],
                          )
                          .filter(
                            ([prefix, perms]) =>
                              perms.length > 0 || `${prefix}:*`.includes(q),
                          )
                      : denyGroups;
                    const customVal = denySearch.trim();
                    const showCustom =
                      q !== "" &&
                      !allDenyChoices.has(customVal) &&
                      !form.denyPermissions.includes(customVal);
                    return (
                      <>
                        {groups.map(([prefix, perms]) => (
                          <CommandGroup key={prefix} heading={prefix}>
                            {perms.map((p) => (
                              <CommandItem
                                key={p.id}
                                value={p.id}
                                disabled={form.denyPermissions.includes(p.id)}
                                onSelect={() => addDenyPermissionValue(p.id)}
                                className="text-xs"
                              >
                                <span>{p.display_name}</span>
                                <span className="text-muted-foreground ml-auto font-mono text-[10px]">
                                  {p.id}
                                </span>
                              </CommandItem>
                            ))}
                            <CommandItem
                              value={`${prefix}:*`}
                              disabled={form.denyPermissions.includes(
                                `${prefix}:*`,
                              )}
                              onSelect={() =>
                                addDenyPermissionValue(`${prefix}:*`)
                              }
                              className="text-warning text-xs"
                            >
                              <span>拒绝该前缀全部</span>
                              <span className="ml-auto font-mono text-[10px]">{`${prefix}:*`}</span>
                            </CommandItem>
                          </CommandGroup>
                        ))}
                        {showCustom && (
                          <>
                            <CommandSeparator />
                            <CommandGroup heading="自定义">
                              <CommandItem
                                value="__custom__"
                                onSelect={() =>
                                  addDenyPermissionValue(customVal)
                                }
                                className="text-xs"
                              >
                                <Plus className="mr-1 h-3.5 w-3.5" />
                                <span>添加自定义</span>
                                <span className="text-warning ml-auto font-mono text-[10px]">
                                  {customVal}
                                </span>
                              </CommandItem>
                            </CommandGroup>
                          </>
                        )}
                      </>
                    );
                  })()}
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
          {form.denyPermissions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {form.denyPermissions.map((perm) => {
                const permLabel =
                  allPermissions.find((p) => p.id === perm)?.display_name ??
                  perm;
                return (
                  <span
                    key={perm}
                    className="bg-warning/10 text-warning border-warning/30 inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-medium"
                  >
                    {permLabel}
                    <button
                      type="button"
                      onClick={() => removeDenyPermission(perm)}
                      className="hover:text-warning/70 transition-colors"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                );
              })}
            </div>
          )}
        </div>

        {/* 拒绝数据范围 —— 复用 registry 声明的 data_scopes，按 module 分组多选 */}
        <div>
          <label className="text-foreground/80 mb-1 block text-[11px] font-medium">
            拒绝数据范围
          </label>
          {scopeModules.length === 0 ? (
            <p className="text-muted-foreground text-[11px] italic">
              registry 暂无已声明的 data_scope
            </p>
          ) : (
            <div className="space-y-2">
              {scopeModules.map((module) => (
                <div
                  key={module.key}
                  className="flex flex-wrap items-center gap-1.5"
                >
                  <span
                    className="text-muted-foreground w-20 shrink-0 truncate text-[10px]"
                    title={module.display_name}
                  >
                    {module.display_name}
                  </span>
                  {module.data_scopes.map((scope) => {
                    const isSelected = form.denyDataScopes.includes(scope.id);
                    return (
                      <label
                        key={scope.id}
                        className={cn(
                          "flex cursor-pointer items-center gap-1 rounded border px-2 py-0.5 text-sm transition-colors",
                          isSelected
                            ? "bg-warning/10 border-warning/40 text-warning font-medium"
                            : "border-border text-muted-foreground hover:border-warning/30",
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleDenyDataScope(scope.id)}
                          className="sr-only"
                        />
                        <span
                          className={cn(
                            "flex h-3 w-3 shrink-0 items-center justify-center rounded-[2px] border",
                            isSelected
                              ? "bg-warning border-warning"
                              : "border-muted-foreground/40",
                          )}
                        >
                          {isSelected && (
                            <span className="text-[8px] leading-none text-white">
                              ✓
                            </span>
                          )}
                        </span>
                        <span>{scope.display_name}</span>
                      </label>
                    );
                  })}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="border-border flex items-center justify-end gap-2 border-t pt-2">
        <button
          onClick={onCancel}
          className="text-foreground bg-background border-input hover:bg-muted rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors"
        >
          取消
        </button>
        <button
          onClick={onSave}
          className="bg-primary hover:bg-primary/90 rounded-lg px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-colors"
        >
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
  const [activeTab, setActiveTab] = useState<
    "permissions" | "datascope" | "policies" | "users"
  >("permissions");
  const [showMatrix, setShowMatrix] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [roleUsers, setRoleUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  // EAI-CUSTOM (U1): role_id → 关联真实用户数，来自 GET /roles/assignments
  const [assignments, setAssignments] = useState<Record<string, number>>({});

  // Registry & policies
  const [registryModules, setRegistryModules] = useState<
    RegistryModule[] | null
  >(null);
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [policiesLoading, setPoliciesLoading] = useState(false);
  const [dataScopeSelections, setDataScopeSelections] = useState<
    Record<string, string>
  >({});

  const [createForm, setCreateForm] = useState<CreateRoleRequest>({
    name: "",
    code: "",
    permissions: [],
    description: "",
    level: 10,
    parent_role_id: undefined,
    nav: ALL_NAV_IDS,
  });
  const [editForm, setEditForm] = useState<{
    name: string;
    description: string;
    permissions: string[];
    level?: number;
    parent_role_id?: string;
    nav: string[];
  }>({
    name: "",
    description: "",
    permissions: [],
    nav: [],
  });
  /* EAI-CUSTOM: which nav modules are visible for the selected role (detail view) */
  const [detailNavSet, setDetailNavSet] = useState<Set<string>>(new Set()); // EAI-CUSTOM: starts empty, populated by loadData/handleSelectRole
  /* EAI-CUSTOM: which sub-pages are visible for the selected role (detail view) */
  const [detailPagesSet, setDetailPagesSet] = useState<Set<string>>(new Set());

  // EAI-CUSTOM (U4): 数据权限面板初始化 — deny-by-default：仅当角色 data_scopes 真实匹配某 module 的 scope 时才生成条目（无匹配则无该 module 条目，绝不虚构授权）
  // useCallback([registryModules]) so the registry effect below can list it as a dep without extra re-runs
  const initDataScopes = useCallback(
    (role: Role) => {
      setDataScopeSelections(
        resolveDataScopeSelections(registryModules ?? [], role.data_scopes),
      );
    },
    [registryModules],
  );

  // EAI-CUSTOM (T3): 子页面可见性初始化 — 把 role.pages（"*"/缺失=全可见）解析为可见页面 id 集合
  const initPageVisibility = useCallback(
    (role: Role) => {
      setDetailPagesSet(resolveVisiblePages(registryModules ?? [], role.pages));
    },
    [registryModules],
  );

  /* ── Data loading ────────────────────────────────────────── */
  const loadData = async () => {
    setIsLoading(true);
    try {
      const res = await roleApi.list();
      setRoles(res.roles);
      // U1: 用户数统计为 best-effort，失败不阻断角色列表渲染
      const asg = await roleApi.assignments().catch(() => []);
      setAssignments(
        Object.fromEntries(asg.map((a) => [a.role_id, a.user_count])),
      );
      setSelectedRole((prev) => {
        const next = prev
          ? (res.roles.find((r) => r.id === prev.id) ?? prev)
          : (res.roles[0] ?? null);
        // EAI-CUSTOM: sync nav visibility when role data refreshes
        if (next?.nav && next.nav.length > 0) {
          setDetailNavSet(new Set(next.nav));
        } else if (next) {
          setDetailNavSet(new Set(ALL_NAV_IDS));
        }
        // EAI-CUSTOM (U4): sync data scope selections when role data refreshes
        if (next) initDataScopes(next);
        // EAI-CUSTOM (T3): sync sub-page visibility when role data refreshes
        if (next) initPageVisibility(next);
        return next;
      });
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  // latest-ref pattern: run loadData exactly once on mount without re-running
  // when registryModules arrives (loadData identity changes with its helpers).
  const loadDataRef = useRef(loadData);
  useEffect(() => {
    loadDataRef.current = loadData;
  });
  useEffect(() => {
    void loadDataRef.current();
  }, []);

  // Fetch permissions registry on mount
  useEffect(() => {
    permissionsApi
      .getRegistry()
      .then((res) => setRegistryModules(res.modules))
      .catch((err) =>
        console.error("Failed to load permissions registry:", err),
      );
  }, []);

  // EAI-CUSTOM (U4): 注册表异步加载完成后补齐数据权限面板初始化（解决初始加载竞态——loadData 可能先于 registry 返回）
  useEffect(() => {
    if (registryModules && selectedRole) {
      initDataScopes(selectedRole);
      initPageVisibility(selectedRole);
    }
  }, [registryModules, selectedRole, initDataScopes, initPageVisibility]);

  // Fetch policies when tab changes to policies
  const loadPolicies = useCallback(async () => {
    setPoliciesLoading(true);
    try {
      const res = await permissionsApi.listPolicies();
      // EAI-CUSTOM: 后端存储条件为引擎 dict {and:[...]}，加载时转回 UI 数组，保证 PolicyRow/startEdit 读数组可用
      setPolicies(
        (res.policies || []).map((p) => {
          // EAI-CUSTOM (T14): allow 走 toGrantArray；deny 两键用 toDenyInfo 抽出挂到 PolicyItem，
          // 供 PolicyRow 展示与 startEdit 透传到编辑态。引擎 dict 是单事实源，UI 不另存。
          const deny = toDenyInfo(p.grants);
          return {
            ...p,
            conditions: toUIConditions(p.conditions),
            grants: toGrantArray(p.grants),
            denyPermissions: deny.denyPermissions,
            denyDataScopes: deny.denyDataScopes,
          };
        }),
      );
    } catch (err) {
      console.error("Failed to load policies:", err);
      setPolicies([]);
    } finally {
      setPoliciesLoading(false);
    }
  }, []);

  /* ── Handlers ────────────────────────────────────────────── */
  // EAI-CUSTOM: 角色列表排序 —— 超级管理员(is_system)置顶，其余按 level 降序、同名按 name 升序
  const filteredRoles = (
    searchQuery
      ? roles.filter(
          (r) =>
            r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            (r.code || "").toLowerCase().includes(searchQuery.toLowerCase()),
        )
      : roles
  )
    .slice()
    .sort((a, b) => {
      if (a.is_system !== b.is_system) return a.is_system ? -1 : 1;
      const lb = (b.level ?? 0) - (a.level ?? 0);
      if (lb !== 0) return lb;
      return a.name.localeCompare(b.name, "zh-CN");
    });

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await roleApi.create(createForm);
      setIsCreateModalOpen(false);
      setCreateForm({
        name: "",
        code: "",
        permissions: [],
        description: "",
        nav: ALL_NAV_IDS,
      });
      void loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "创建失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定要删除该角色吗？")) return;
    try {
      await roleApi.delete(id);
      void loadData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "删除失败");
    }
  };

  const openEditModal = (role: Role) => {
    setEditForm({
      name: role.name,
      description: role.description ?? "",
      permissions: role.permissions ?? [],
      level: role.level,
      parent_role_id: role.parent_role_id,
      nav: role.nav ?? ALL_NAV_IDS,
    });
    setIsEditModalOpen(true);
  };

  const handleEdit = async () => {
    if (!selectedRole) return;
    try {
      await roleApi.update(selectedRole.id, editForm);
      setIsEditModalOpen(false);
      void loadData();
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
    // EAI-CUSTOM: initialize nav visibility from role data (DB values)
    if (role.nav && role.nav.length > 0) {
      setDetailNavSet(new Set(role.nav));
    } else {
      setDetailNavSet(new Set(ALL_NAV_IDS));
    }
    // EAI-CUSTOM (U4): initialize data scope selections from role data (切换角色重置)
    initDataScopes(role);
    // EAI-CUSTOM (T3): initialize sub-page visibility from role data (切换角色重置)
    initPageVisibility(role);
  };

  const handleTabChange = (
    tab: "permissions" | "datascope" | "policies" | "users",
  ) => {
    setActiveTab(tab);
    if (
      tab === "users" &&
      selectedRole &&
      roleUsers.length === 0 &&
      !usersLoading
    ) {
      void loadRoleUsers(selectedRole);
    }
    if (tab === "policies" && policies.length === 0 && !policiesLoading) {
      void loadPolicies();
    }
  };

  // Policy CRUD handlers
  const handlePolicyToggle = async (id: string, enabled: boolean) => {
    try {
      await permissionsApi.updatePolicy(id, { enabled });
      setPolicies((prev) =>
        prev.map((p) => (p.id === id ? { ...p, enabled } : p)),
      );
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
      // EAI-CUSTOM (T14): allow 走 toEngineConditions/toEngineGrants；deny 经 toEngineGrants 拼到 grants dict
      // (deny_permissions/​deny_data_scopes)。后端 policy_routers._validate_grants (T9) 校验形状 + scope id 已声明。
      const payload = {
        name: policy.name,
        conditions: toEngineConditions(policy.conditions),
        grants: toEngineGrants(
          policy.grants.map((g) => g.permission).filter(Boolean),
          policy.denyPermissions ?? [],
          policy.denyDataScopes ?? [],
        ),
      };
      if (policy.id) {
        await permissionsApi.updatePolicy(policy.id, payload);
        setPolicies((prev) =>
          prev.map((p) =>
            p.id === policy.id
              ? {
                  ...p,
                  name: policy.name,
                  conditions: policy.conditions,
                  grants: policy.grants,
                  denyPermissions: policy.denyPermissions,
                  denyDataScopes: policy.denyDataScopes,
                }
              : p,
          ),
        );
      } else {
        const created = await permissionsApi.createPolicy({
          ...payload,
          enabled: true,
        });
        // EAI-CUSTOM: 后端返回完整行（conditions/grants 为引擎 dict），转回 UI 数组再入列表；T14: deny 同步抽出
        const createdDeny = toDenyInfo(created.grants);
        setPolicies((prev) => [
          ...prev,
          {
            ...created,
            conditions: toUIConditions(created.conditions),
            grants: toGrantArray(created.grants),
            denyPermissions: createdDeny.denyPermissions,
            denyDataScopes: createdDeny.denyDataScopes,
          },
        ]);
      }
    } catch (err) {
      console.error("Failed to save policy:", err);
      alert("保存策略失败");
    }
  };

  // EAI-CUSTOM (U4): 保存数据权限 — 仅发送 data_scopes，绝不回传 DB 镜像的 permissions/nav（会覆盖 overlay yaml 更新后的值）
  const handleDataScopeChange = async (selections: Record<string, string>) => {
    setDataScopeSelections(selections);
    if (selectedRole && !selectedRole.is_system) {
      try {
        await roleApi.update(selectedRole.id, {
          data_scopes: Object.values(selections),
        });
      } catch (err) {
        console.error("Failed to save data scopes:", err);
      }
    }
  };

  if (isLoading) {
    return <PageLoadingOverlay text="加载中" />;
  }

  const modules = registryModules ?? [];

  return (
    <main className="bg-background mx-auto flex h-full w-full max-w-[1600px] overflow-hidden">
      {/* Left Sidebar */}
      <div className="border-border bg-muted/30 flex w-80 shrink-0 flex-col border-r">
        <div className="border-border bg-card border-b p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-foreground font-semibold">角色列表</h2>
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="bg-primary/10 text-primary hover:bg-primary/20 rounded-md p-1.5 transition-colors"
              title="新建角色"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
          <div className="relative">
            <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
            <input
              type="text"
              placeholder="搜索角色..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-secondary focus:bg-background focus:border-primary focus:ring-primary/20 w-full rounded-lg border-transparent py-2 pr-4 pl-9 text-sm transition-all outline-none focus:ring-2"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-3">
          {filteredRoles.length === 0 ? (
            <div className="text-muted-foreground py-4 text-center text-sm">
              暂无角色
            </div>
          ) : (
            filteredRoles.map((role) => {
              const isSelected = selectedRole?.id === role.id;
              return (
                <button
                  key={role.id}
                  onClick={() => handleSelectRole(role)}
                  className={cn(
                    "w-full rounded-xl border p-3 text-left transition-all duration-200",
                    isSelected
                      ? "bg-card border-primary/30 ring-primary/10 shadow-sm ring-1"
                      : "hover:bg-accent border-transparent",
                  )}
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span
                      className={cn(
                        "truncate text-sm font-medium",
                        isSelected ? "text-primary" : "text-foreground",
                      )}
                    >
                      {role.name}
                    </span>
                    {role.is_system && (
                      <span className="bg-secondary text-muted-foreground ml-1 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium">
                        系统
                      </span>
                    )}
                  </div>
                  <div className="text-muted-foreground mb-2 line-clamp-1 min-h-[1rem] text-xs">
                    {/* EAI-CUSTOM: truthiness check via .length (not `??`) — description can legitimately be "" (create form defaults to ""), placeholder must still show */}
                    {role.description?.length ? (
                      role.description
                    ) : (
                      <span className="opacity-40">暂无描述</span>
                    )}
                  </div>
                  <div className="text-muted-foreground flex items-center gap-3 text-xs">
                    <span className="flex items-center gap-1">
                      <Users className="h-3 w-3" /> {assignments[role.id] ?? 0}
                    </span>
                    <span className="flex items-center gap-1">
                      {/* EAI-CUSTOM: 通配符展开 —— superadmin permissions=["*"] 显示全部权限数 */}
                      <Key className="h-3 w-3" />{" "}
                      {
                        expandWildcardPerms(role.permissions, registryModules)
                          .length
                      }{" "}
                      权限
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Right Side */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {selectedRole ? (
          <>
            {/* Header */}
            <div className="shrink-0 px-8 pt-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-muted-foreground mb-2 flex items-center gap-2 text-sm">
                    <Settings className="h-4 w-4" />
                    <span>角色详情</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <h1 className="text-foreground text-2xl font-bold tracking-tight">
                      {selectedRole.name}
                    </h1>
                    <span className="bg-muted text-muted-foreground border-border rounded-md border px-2 py-1 font-mono text-xs font-medium">
                      {selectedRole.code}
                    </span>
                    {selectedRole.is_system && (
                      <span className="text-warning bg-warning/10 border-warning/50 flex items-center gap-1 rounded-full border px-2 py-1 text-xs font-medium">
                        <Lock className="h-3 w-3" /> 系统预设角色，不可修改
                      </span>
                    )}
                  </div>
                  {selectedRole.description && (
                    <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">
                      {selectedRole.description}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {!selectedRole.is_system && (
                    <>
                      <button
                        onClick={() => openEditModal(selectedRole)}
                        className="text-foreground bg-background border-input hover:bg-muted flex items-center gap-1.5 rounded-lg border px-4 py-2 text-sm font-medium shadow-sm transition-colors"
                      >
                        <Pencil className="h-4 w-4" /> 编辑
                      </button>
                      <button
                        onClick={() => handleDelete(selectedRole.id)}
                        className="text-destructive bg-background border-destructive/30 hover:bg-destructive/10 flex items-center gap-1.5 rounded-lg border px-4 py-2 text-sm font-medium shadow-sm transition-colors"
                      >
                        <Trash2 className="h-4 w-4" /> 删除
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Tabs */}
              <div className="border-border -mx-8 mt-4 flex items-center gap-6 overflow-x-auto border-b px-8">
                <button
                  onClick={() => handleTabChange("permissions")}
                  className={cn(
                    "relative pb-3 text-sm font-medium whitespace-nowrap transition-colors",
                    activeTab === "permissions"
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <KeyRound className="mr-1.5 inline h-3.5 w-3.5" />
                  操作权限
                  {activeTab === "permissions" && (
                    <motion.div
                      layoutId="roleActiveTab"
                      className="bg-primary absolute right-0 bottom-0 left-0 h-0.5"
                    />
                  )}
                </button>
                <button
                  onClick={() => handleTabChange("datascope")}
                  className={cn(
                    "relative pb-3 text-sm font-medium whitespace-nowrap transition-colors",
                    activeTab === "datascope"
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Filter className="mr-1.5 inline h-3.5 w-3.5" />
                  数据权限
                  {activeTab === "datascope" && (
                    <motion.div
                      layoutId="roleActiveTab"
                      className="bg-primary absolute right-0 bottom-0 left-0 h-0.5"
                    />
                  )}
                </button>
                <button
                  onClick={() => handleTabChange("policies")}
                  className={cn(
                    "relative pb-3 text-sm font-medium whitespace-nowrap transition-colors",
                    activeTab === "policies"
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <GripVertical className="mr-1.5 inline h-3.5 w-3.5" />
                  自定义策略
                  {activeTab === "policies" && (
                    <motion.div
                      layoutId="roleActiveTab"
                      className="bg-primary absolute right-0 bottom-0 left-0 h-0.5"
                    />
                  )}
                </button>
                <button
                  onClick={() => handleTabChange("users")}
                  className={cn(
                    "relative pb-3 text-sm font-medium whitespace-nowrap transition-colors",
                    activeTab === "users"
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  关联用户
                  {activeTab === "users"
                    ? ` (${usersLoading ? "…" : roleUsers.length})`
                    : ""}
                  {activeTab === "users" && (
                    <motion.div
                      layoutId="roleActiveTab"
                      className="bg-primary absolute right-0 bottom-0 left-0 h-0.5"
                    />
                  )}
                </button>
                {/* Matrix view toggle — only for permissions tab */}
                {activeTab === "permissions" && (
                  <div className="ml-auto flex items-center gap-1 pb-3">
                    <button
                      type="button"
                      onClick={() => setShowMatrix(false)}
                      className={cn(
                        "rounded p-1.5 transition-colors",
                        !showMatrix
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                      title="列表视图"
                    >
                      <List className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowMatrix(true)}
                      className={cn(
                        "rounded p-1.5 transition-colors",
                        showMatrix
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                      title="矩阵概览"
                    >
                      <LayoutGrid className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Tab Content */}
            <div className="bg-muted/20 min-h-0 flex-1 overflow-y-auto p-8">
              <AnimatePresence mode="wait">
                {activeTab === "permissions" ? (
                  <motion.div
                    key="permissions"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                    className="w-full"
                  >
                    {showMatrix ? (
                      <div>
                        <h3 className="mb-3 text-sm font-semibold">
                          角色权限矩阵
                        </h3>
                        <div className="bg-card border-border overflow-hidden rounded-xl border">
                          <RoleMatrixOverview
                            roles={roles}
                            modules={registryModules}
                          />
                        </div>
                      </div>
                    ) : (
                      <>
                        {selectedRole.is_system && (
                          <p className="text-muted-foreground mb-4 text-xs">
                            系统角色权限为只读
                          </p>
                        )}
                        <PermissionPanel
                          selected={selectedRole.permissions ?? []}
                          readonly={selectedRole.is_system}
                          modules={registryModules}
                          enabledNavs={detailNavSet}
                          onNavToggle={async (navId, enabled) => {
                            const newNavs = enabled
                              ? [...detailNavSet, navId]
                              : [...detailNavSet].filter((n) => n !== navId);
                            setDetailNavSet(new Set(newNavs));
                            try {
                              await roleApi.update(selectedRole.id, {
                                nav: newNavs,
                              });
                            } catch (err: unknown) {
                              alert(
                                err instanceof Error
                                  ? err.message
                                  : "更新导航可见性失败",
                              );
                            }
                          }}
                          enabledPages={detailPagesSet}
                          onPageToggle={async (pageId, enabled) => {
                            const next = new Set(detailPagesSet);
                            if (enabled) {
                              next.add(pageId);
                            } else {
                              next.delete(pageId);
                            }
                            setDetailPagesSet(next);
                            if (selectedRole && !selectedRole.is_system) {
                              try {
                                await roleApi.update(selectedRole.id, {
                                  pages: serializePages(
                                    next,
                                    registryModules ?? [],
                                  ),
                                });
                              } catch (err: unknown) {
                                alert(
                                  err instanceof Error
                                    ? err.message
                                    : "更新页面可见性失败",
                                );
                              }
                            }
                          }}
                          onChange={async (perms) => {
                            try {
                              await roleApi.update(selectedRole.id, {
                                permissions: perms,
                              });
                              void loadData();
                            } catch (err: unknown) {
                              alert(
                                err instanceof Error
                                  ? err.message
                                  : "更新权限失败",
                              );
                            }
                          }}
                        />
                      </>
                    )}
                  </motion.div>
                ) : activeTab === "datascope" ? (
                  <motion.div
                    key="datascope"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                  >
                    {selectedRole.is_system && (
                      <p className="text-muted-foreground mb-4 text-xs">
                        系统角色数据权限为只读
                      </p>
                    )}
                    <DataScopePanel
                      modules={modules}
                      selections={dataScopeSelections}
                      onChange={handleDataScopeChange}
                      readonly={selectedRole.is_system}
                    />
                  </motion.div>
                ) : activeTab === "policies" ? (
                  <motion.div
                    key="policies"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                  >
                    <PoliciesPanel
                      policies={policies}
                      policiesLoading={policiesLoading}
                      onToggle={handlePolicyToggle}
                      onDelete={handlePolicyDelete}
                      onAdd={loadPolicies}
                      onSave={handlePolicySave}
                      modules={modules}
                      roles={roles}
                    />
                  </motion.div>
                ) : (
                  <motion.div
                    key="users"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                  >
                    {usersLoading ? (
                      <div className="text-muted-foreground flex items-center justify-center py-12 text-sm">
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        加载中...
                      </div>
                    ) : roleUsers.length === 0 ? (
                      <div className="bg-card border-border mx-auto max-w-lg rounded-2xl border p-8 text-center shadow-sm">
                        <div className="bg-muted text-muted-foreground mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                          <Users className="h-8 w-8" />
                        </div>
                        <h3 className="text-foreground mb-2 text-base font-medium">
                          暂无关联用户
                        </h3>
                        <p className="text-muted-foreground mb-6 text-sm">
                          当前没有用户被分配 &quot;{selectedRole.name}&quot;
                          角色，可前往用户管理页面进行分配。
                        </p>
                        <Link
                          href="/admin/users"
                          className="bg-primary hover:bg-primary/90 inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors"
                        >
                          前往用户管理
                        </Link>
                      </div>
                    ) : (
                      <div className="max-w-3xl">
                        <div className="mb-6 grid grid-cols-2 gap-3">
                          {roleUsers.map((user) => (
                            <div
                              key={user.id}
                              className="bg-card border-border flex items-center gap-3 rounded-xl border p-3 transition-all hover:shadow-sm"
                            >
                              <div className="bg-primary/10 text-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold">
                                {(user.full_name ?? user.username)
                                  .charAt(0)
                                  .toUpperCase()}
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="text-foreground truncate text-sm font-medium">
                                  {user.full_name ?? user.username}
                                </div>
                                <div className="text-muted-foreground truncate text-xs">
                                  {user.email}
                                </div>
                              </div>
                              <span
                                className={cn(
                                  "shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium",
                                  user.status === "active"
                                    ? "bg-success/10 text-success"
                                    : "bg-secondary text-muted-foreground",
                                )}
                              >
                                {user.status === "active" ? "正常" : "停用"}
                              </span>
                            </div>
                          ))}
                        </div>
                        <div className="text-center">
                          <Link
                            href="/admin/users"
                            className="text-primary hover:text-primary/80 text-sm font-medium transition-colors"
                          >
                            前往用户管理 →
                          </Link>
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </>
        ) : (
          <div className="text-muted-foreground flex flex-1 items-center justify-center">
            <div className="text-center">
              <Shield className="mx-auto mb-3 h-12 w-12 opacity-30" />
              <p className="text-sm">请选择一个角色查看详情</p>
            </div>
          </div>
        )}
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {isCreateModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsCreateModalOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="bg-background relative flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl shadow-xl"
            >
              <div className="border-border flex shrink-0 items-center justify-between border-b px-6 py-4">
                <h3 className="text-foreground text-lg font-semibold">
                  新建角色
                </h3>
                <button
                  onClick={() => setIsCreateModalOpen(false)}
                  className="text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg p-2 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <form
                onSubmit={handleCreate}
                className="flex-1 space-y-5 overflow-y-auto p-6"
              >
                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      角色名称 <span className="text-destructive">*</span>
                    </label>
                    <Input
                      placeholder="例如：管理员"
                      value={createForm.name}
                      onChange={(e) =>
                        setCreateForm({ ...createForm, name: e.target.value })
                      }
                      required
                    />
                  </div>
                  <div>
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      角色代码 <span className="text-destructive">*</span>
                    </label>
                    <Input
                      placeholder="例如：admin"
                      value={createForm.code}
                      onChange={(e) =>
                        setCreateForm({ ...createForm, code: e.target.value })
                      }
                      required
                    />
                  </div>
                </div>
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    描述
                  </label>
                  <textarea
                    rows={2}
                    placeholder="角色描述（选填）"
                    value={createForm.description ?? ""}
                    onChange={(e) =>
                      setCreateForm({
                        ...createForm,
                        description: e.target.value,
                      })
                    }
                    className="bg-background border-input focus:ring-primary/50 focus:border-primary w-full resize-none rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-foreground mb-2 block text-sm font-medium">
                    权限配置
                  </label>
                  <PermissionPanel
                    selected={createForm.permissions ?? []}
                    modules={registryModules}
                    compact
                    enabledNavs={new Set(createForm.nav ?? ALL_NAV_IDS)}
                    onNavToggle={(navId, enabled) => {
                      setCreateForm((prev) => ({
                        ...prev,
                        nav: enabled
                          ? [...(prev.nav ?? ALL_NAV_IDS), navId]
                          : (prev.nav ?? ALL_NAV_IDS).filter(
                              (n) => n !== navId,
                            ),
                      }));
                    }}
                    onChange={(perms) =>
                      setCreateForm({ ...createForm, permissions: perms })
                    }
                  />
                </div>
              </form>
              <div className="bg-muted border-border flex shrink-0 items-center justify-end gap-3 border-t px-6 py-4">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="text-foreground bg-background border-input hover:bg-muted rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
                >
                  取消
                </button>
                <button
                  type="submit"
                  onClick={handleCreate}
                  className="bg-primary hover:bg-primary/90 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors"
                >
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
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsEditModalOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="bg-background relative flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl shadow-xl"
            >
              <div className="border-border flex shrink-0 items-center justify-between border-b px-6 py-4">
                <h3 className="text-foreground text-lg font-semibold">
                  编辑角色 — {selectedRole?.name}
                </h3>
                <button
                  onClick={() => setIsEditModalOpen(false)}
                  className="text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg p-2 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="flex-1 space-y-5 overflow-y-auto p-6">
                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      角色名称
                    </label>
                    <Input
                      value={editForm.name}
                      onChange={(e) =>
                        setEditForm({ ...editForm, name: e.target.value })
                      }
                    />
                  </div>
                  <div>
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      角色代码
                    </label>
                    <Input
                      value={selectedRole?.code ?? ""}
                      disabled
                      className="bg-muted text-muted-foreground cursor-not-allowed"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    描述
                  </label>
                  <textarea
                    rows={2}
                    placeholder="角色描述（选填）"
                    value={editForm.description ?? ""}
                    onChange={(e) =>
                      setEditForm({ ...editForm, description: e.target.value })
                    }
                    className="bg-background border-input focus:ring-primary/50 focus:border-primary w-full resize-none rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      层级
                    </label>
                    <input
                      type="number"
                      value={editForm.level ?? 10}
                      onChange={(e) =>
                        setEditForm({
                          ...editForm,
                          level: parseInt(e.target.value) || 10,
                        })
                      }
                      className="bg-background border-input focus:ring-primary/50 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                      min="1"
                      max="100"
                    />
                  </div>
                  <div>
                    <label className="text-foreground mb-1 block text-sm font-medium">
                      继承角色
                    </label>
                    <Select
                      value={editForm.parent_role_id ?? "__none__"}
                      onValueChange={(v) =>
                        setEditForm({
                          ...editForm,
                          parent_role_id: v === "__none__" ? undefined : v,
                        })
                      }
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="无继承" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">
                          <span className="flex items-center gap-2">
                            <span className="bg-muted-foreground/30 h-1.5 w-1.5 shrink-0 rounded-full" />
                            <span className="text-muted-foreground">
                              无继承
                            </span>
                          </span>
                        </SelectItem>
                        {roles
                          .filter((r) => r.id !== selectedRole?.id)
                          .map((r) => (
                            <SelectItem key={r.id} value={r.id}>
                              <span className="flex items-center gap-2">
                                <span
                                  className={cn(
                                    "h-1.5 w-1.5 shrink-0 rounded-full",
                                    r.is_system
                                      ? "bg-amber-400"
                                      : "bg-primary/60",
                                  )}
                                />
                                <span>{r.name}</span>
                                <span className="text-muted-foreground bg-muted rounded px-1.5 py-0.5 font-mono text-[10px]">
                                  Lv.{r.level}
                                </span>
                                {r.is_system && (
                                  <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:bg-amber-950/30">
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
                  <label className="text-foreground mb-2 block text-sm font-medium">
                    权限配置
                  </label>
                  <PermissionPanel
                    selected={editForm.permissions}
                    modules={registryModules}
                    compact
                    enabledNavs={new Set(editForm.nav)}
                    onNavToggle={(navId, enabled) => {
                      setEditForm((prev) => ({
                        ...prev,
                        nav: enabled
                          ? [...prev.nav, navId]
                          : prev.nav.filter((n) => n !== navId),
                      }));
                    }}
                    onChange={(perms) =>
                      setEditForm({ ...editForm, permissions: perms })
                    }
                  />
                </div>
              </div>
              <div className="bg-muted border-border flex shrink-0 items-center justify-end gap-3 border-t px-6 py-4">
                <button
                  onClick={() => setIsEditModalOpen(false)}
                  className="text-foreground bg-background border-input hover:bg-accent rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleEdit}
                  className="bg-primary hover:bg-primary/90 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors"
                >
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
