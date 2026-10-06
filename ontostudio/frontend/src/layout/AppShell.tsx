/**
 * OntoStudio 应用外壳（EAI-CUSTOM）：侧栏导航 + hash 路由（零新依赖）。
 * 视觉对照 docs/designs/ontostudio-frontend-design.html（青卷版）。
 *
 * 路由映射：01 总览 / 02 图谱 / 04 消解 → OntologyPage 真实三视图（常驻挂载，
 * 切去骨架页仅隐藏，避免 sigma 画布重载）；03/05-09 → 骨架占位页（src/pages/*）。
 */
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  BrainCircuit,
  Database,
  DraftingCompass,
  FileInput,
  FileOutput,
  GitMerge,
  LayoutDashboard,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { fetchPendingReviewCount } from "@/api/ontology-graph-api";
import eaiLogo from "@/assets/eai-logo.svg";
import { OntologyPage, type PageView } from "@/components/OntologyPage";
import { usePermission } from "@/lib/permissions";
import { DashboardPage } from "@/pages/DashboardPage";
import { EntitiesPage } from "@/pages/EntitiesPage";
import { ExportPage } from "@/pages/ExportPage";
import { IngestPage } from "@/pages/IngestPage";
import { ModelerPage } from "@/pages/ModelerPage";
import { ReasoningPage } from "@/pages/ReasoningPage";
import { ValidationPage } from "@/pages/ValidationPage";
import { cn } from "@/lib/utils";

type RouteId =
  | "dashboard"
  | "graph"
  | "entities"
  | "resolve"
  | "modeler"
  | "reasoning"
  | "validation"
  | "ingest"
  | "export";

/** 知识层路由 → OntologyPage 内部视图；onViewChange 反向映射回路由。
 *  EAI-CUSTOM(2026-09-27): dashboard 改为独立 DashboardPage（运营仪表盘，
 *  见 pages/DashboardPage.tsx），不再走 OntologyPage overview 视图——
 *  graph/resolve 仍常驻挂载保 sigma 画布。 */
const ROUTE_VIEW: Partial<Record<RouteId, PageView>> = {
  graph: "map",
  resolve: "resolution",
};
const VIEW_ROUTE: Record<PageView, RouteId> = {
  overview: "dashboard",
  map: "graph",
  resolution: "resolve",
};

const NAV: Array<{ group: string; items: Array<[RouteId, string]> }> = [
  { group: "总览", items: [["dashboard", "工作台总览"]] },
  {
    group: "知识层",
    items: [
      ["graph", "图谱浏览"],
      ["entities", "实体库"],
      ["resolve", "消解审核"],
    ],
  },
  {
    group: "建模层",
    items: [
      ["modeler", "本体建模器"],
      ["reasoning", "推理工作台"],
      ["validation", "校验中心"],
    ],
  },
  {
    group: "管线",
    items: [
      ["ingest", "抽取导入"],
      ["export", "导出互操作"],
    ],
  },
];
const ROUTE_NO: Record<RouteId, string> = {
  dashboard: "01",
  graph: "02",
  entities: "03",
  resolve: "04",
  modeler: "05",
  reasoning: "06",
  validation: "07",
  ingest: "08",
  export: "09",
};
const ROUTE_IDS = Object.keys(ROUTE_NO) as RouteId[];

/** 菜单项语义图标（lucide）：左侧槽位，替换序号列。 */
const ROUTE_ICON: Record<RouteId, LucideIcon> = {
  dashboard: LayoutDashboard,
  graph: Network,
  entities: Database,
  resolve: GitMerge,
  modeler: DraftingCompass,
  reasoning: BrainCircuit,
  validation: ShieldCheck,
  ingest: FileInput,
  export: FileOutput,
};

/** hash 路由：解析非法/空 hash 落到 graph（知识层主视图）。
 *  EAI-CUSTOM(F6 深链): 支持 `modeler:<domain>` 后缀——总览域行点击直达建模器对应域。 */
function useHashRoute(): [RouteId, (id: RouteId) => void] {
  const parse = useCallback((): RouteId => {
    const raw = window.location.hash.replace(/^#/, "").split(":")[0] ?? "";
    return (ROUTE_IDS as string[]).includes(raw) ? (raw as RouteId) : "dashboard";
  }, []);
  const [route, setRoute] = useState<RouteId>(parse);
  useEffect(() => {
    const onHashChange = () => setRoute(parse());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [parse]);
  const go = useCallback(
    (id: RouteId) => {
      if (window.location.hash === `#${id}`) {
        setRoute(id);
      } else {
        window.location.hash = id;
      }
    },
    [],
  );
  return [route, go];
}

export function AppShell() {
  const [route, go] = useHashRoute();
  const { me } = usePermission();
  const knowledgeView = ROUTE_VIEW[route];
  // F6 深链参数：`#modeler:<domain>` → 建模器初始域文件；无后缀时 undefined（保持默认选中）
  const modelerInitialFile = (() => {
    const raw = window.location.hash.replace(/^#/, "");
    if (!raw.startsWith("modeler:")) return undefined;
    const domain = decodeURIComponent(raw.slice("modeler:".length));
    return domain ? `${domain}.yaml` : undefined;
  })();
  // 校验违规下钻深链：`#entities:<uuid>` → 实体库抽屉直开该实体
  const entitiesInitial = (() => {
    const raw = window.location.hash.replace(/^#/, "");
    return raw.startsWith("entities:")
      ? decodeURIComponent(raw.slice("entities:".length)) || undefined
      : undefined;
  })();

  // 侧栏消解待审红点：真实 pending 计数；失败（403/网络）静默隐藏
  const pendingQuery = useQuery({
    queryKey: ["ontology", "pending-review-count"],
    queryFn: fetchPendingReviewCount,
    staleTime: 30_000,
    retry: false,
  });
  const pendingCount = pendingQuery.data ?? 0;

  // 侧栏折叠：图标轨道模式；偏好持久化（localStorage）
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("ontostudio-sidebar-collapsed") === "1";
    } catch {
      return false;
    }
  });
  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      try {
        localStorage.setItem("ontostudio-sidebar-collapsed", prev ? "0" : "1");
      } catch {
        /* 隐私模式等场景忽略 */
      }
      return !prev;
    });
  };

  return (
    <div className="bg-background flex h-full min-h-0">
      <aside
        className={cn(
          "border-sidebar-border bg-sidebar flex flex-none flex-col border-r transition-[width] duration-200",
          collapsed ? "w-[60px]" : "w-56",
        )}
      >
        <div
          className={cn(
            "border-border flex items-center gap-2 border-b px-3 py-4",
            collapsed && "justify-center px-1.5",
          )}
        >
          {!collapsed ? (
            <>
              <span className="grid h-8 w-8 flex-none place-items-center overflow-hidden rounded-lg p-1">
                <img src={eaiLogo} alt="EAI" className="h-full w-full object-contain" />
              </span>
              <div className="min-w-0">
                <b className="block text-[15px] leading-tight font-black tracking-wide">
                  OntoStudio
                </b>
                <small className="text-muted-foreground text-xs tracking-[0.14em]">
                  本体建模工作台
                </small>
              </div>
            </>
          ) : null}
          <button
            type="button"
            onClick={toggleCollapsed}
            title={collapsed ? "展开菜单" : "收起菜单"}
            aria-label={collapsed ? "展开菜单" : "收起菜单"}
            className="text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground ml-auto flex h-7 w-7 flex-none items-center justify-center rounded-md transition-colors"
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </button>
        </div>

        <nav className="min-h-0 flex-1 overflow-y-auto p-2">
          {NAV.map((section) => (
            <div key={section.group}>
              {collapsed ? (
                <div className="border-sidebar-border mx-2 mt-4 border-t" />
              ) : (
                <div className="text-muted-foreground mt-4 px-2.5 pb-1.5 text-xs font-medium tracking-[0.1em]">
                  {section.group}
                </div>
              )}
              {section.items.map(([id, label]) => {
                const ItemIcon = ROUTE_ICON[id];
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => go(id)}
                    aria-current={route === id ? "page" : undefined}
                    title={label}
                    className={cn(
                      "flex w-full items-center rounded-lg text-sm font-medium transition-colors",
                      collapsed
                        ? "justify-center px-0 py-2"
                        : "gap-2.5 px-2.5 py-2 text-left",
                      route === id
                        ? "bg-sidebar-accent text-sidebar-accent-foreground font-semibold"
                        : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                    )}
                  >
                    <ItemIcon
                      className={cn(
                        "h-4 w-4 flex-none",
                        route === id ? "text-primary" : "opacity-70",
                      )}
                    />
                    {!collapsed ? label : null}
                    {!collapsed && id === "resolve" && pendingCount > 0 ? (
                      <span
                        className="bg-destructive ml-auto h-1.5 w-1.5 rounded-full"
                        title={`${pendingCount} 个实体待复核`}
                      />
                    ) : null}
                    {collapsed && id === "resolve" && pendingCount > 0 ? (
                      <span
                        className="bg-destructive absolute top-1 right-1 h-1.5 w-1.5 rounded-full"
                        title={`${pendingCount} 个实体待复核`}
                      />
                    ) : null}
                  </button>
                );
              })}
            </div>
          ))}
          {/* 文档分组：文档中心（独立文档站，新标签打开） */}
          <div>
            {collapsed ? (
              <div className="border-sidebar-border mx-2 mt-4 border-t" />
            ) : (
              <div className="text-muted-foreground mt-4 px-2.5 pb-1.5 text-xs font-medium tracking-[0.1em]">
                文档
              </div>
            )}
            <a
              href="/ontostudio/docs/"
              target="_blank"
              rel="noreferrer"
              title="文档中心"
              className={cn(
                "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground hover:text-primary flex w-full items-center rounded-lg py-2 text-sm font-medium transition-colors",
                collapsed ? "justify-center px-0" : "gap-2.5 px-2.5 text-left",
              )}
            >
              <BookOpen className="h-4 w-4 flex-none opacity-70" />
              {!collapsed ? "文档中心" : null}
            </a>
          </div>
        </nav>
        {/* 账户区（2026-10-06）：真身份——/api/permissions/me 的 email/full_name/dept_name，
            替代此前硬编码「知识工程组/admin@eai-flow.com」。加载中/未登录回退占位。 */}
        <div
          className={cn(
            "border-border flex items-center gap-2.5 border-t px-4 py-3",
            collapsed && "justify-center px-2",
          )}
        >
          <span className="bg-primary text-primary-foreground grid h-7 w-7 flex-none place-items-center rounded-full text-xs font-semibold">
            {me.avatarChar || "·"}
          </span>
          {!collapsed ? (
            <div className="min-w-0 leading-tight">
              <b className="block truncate text-sm font-medium">
                {me.fullName || me.email || "未登录"}
              </b>
              <span className="text-muted-foreground block truncate text-xs">
                {me.email || me.deptName || "—"}
              </span>
            </div>
          ) : null}
        </div>
      </aside>

      <main className="min-h-0 min-w-0 flex-1">
        {/* graph/resolve 常驻挂载：切走时仅隐藏，保 sigma 画布/查询状态。
            dashboard 为独立运营仪表盘（DashboardPage）。 */}
        <div className={cn("h-full min-h-0", knowledgeView ? "" : "hidden")}>
          <OntologyPage
            initialView={knowledgeView ?? "map"}
            onViewChange={(view) => go(VIEW_ROUTE[view])}
          />
        </div>
        {route === "dashboard" ? <DashboardPage /> : null}
        {route === "entities" ? <EntitiesPage initialEntity={entitiesInitial} /> : null}
        {route === "modeler" ? <ModelerPage initialFile={modelerInitialFile} /> : null}
        {route === "reasoning" ? <ReasoningPage /> : null}
        {route === "validation" ? <ValidationPage /> : null}
        {route === "ingest" ? <IngestPage /> : null}
        {route === "export" ? <ExportPage /> : null}
      </main>
    </div>
  );
}
