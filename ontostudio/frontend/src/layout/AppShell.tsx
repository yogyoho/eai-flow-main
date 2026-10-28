/**
 * OntoStudio application shell (EAI-CUSTOM): sidebar navigation + hash routing (no new deps).
 * Visual reference: docs/designs prototype 2026-10-20 (indigo / orange / zinc).
 *
 * Route mapping: 01 overview / 02 graph / 04 resolution → OntologyPage real three views
 * (kept mounted, hidden when navigating to skeleton pages, so the sigma canvas does not reload);
 * 03/05-09 → dedicated pages (src/pages/*).
 */
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bell,
  BookOpen,
  BrainCircuit,
  ChevronRight,
  Database,
  DraftingCompass,
  FileInput,
  FileOutput,
  GitMerge,
  LayoutDashboard,
  Menu,
  Moon,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { fetchPendingReviewCount } from "@/api/ontology-graph-api";
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

/** Knowledge-layer routes → OntologyPage internal view; onViewChange maps back to a route.
 *  EAI-CUSTOM(2026-09-27): dashboard is a standalone DashboardPage (ops dashboard),
 *  graph/resolve stay mounted to preserve the sigma canvas. */
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

const ROUTE_LABEL = NAV.flatMap((section) => section.items).reduce(
  (acc, [id, label]) => {
    acc[id] = label;
    return acc;
  },
  {} as Record<RouteId, string>,
);
const ROUTE_GROUP = NAV.reduce(
  (acc, section) => {
    for (const [id] of section.items) acc[id] = section.group;
    return acc;
  },
  {} as Record<RouteId, string>,
);
const ROUTE_DESC: Record<RouteId, string> = {
  dashboard: "运营指标 · 管线健康 · 治理合规链",
  graph: "力导向图 · 社区着色 · 邻域展开",
  entities: "实体检索 · 属性明细 · 证据链",
  resolve: "同名实体 · 合并 / 拆分审核",
  modeler: "YAML 编辑 · 公理派生 · 校验",
  reasoning: "CONSTRUCT · 物化派生 · 规则链",
  validation: "SHACL · 一致性校验 · 违规治理",
  ingest: "抽取任务 · 置信度 · 证据引文",
  export: "导出 · 装载对账 · 快照",
};

/** Menu semantic icons (lucide): left slot, replacing the ordinal column. */
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

/** Hash routing: invalid/empty hash falls back to dashboard.
 *  EAI-CUSTOM(F6 deep links): supports `modeler:<domain>` and `entities:<uuid>` suffixes. */
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
  const go = useCallback((id: RouteId) => {
    if (window.location.hash === `#${id}`) {
      setRoute(id);
    } else {
      window.location.hash = id;
    }
  }, []);
  return [route, go];
}

export function AppShell() {
  const [route, go] = useHashRoute();
  const { me } = usePermission();
  const knowledgeView = ROUTE_VIEW[route];

  // F6 deep-link params: `#modeler:<domain>`; undefined keeps the default selection.
  const modelerInitialFile = (() => {
    const raw = window.location.hash.replace(/^#/, "");
    if (!raw.startsWith("modeler:")) return undefined;
    const domain = decodeURIComponent(raw.slice("modeler:".length));
    return domain ? `${domain}.yaml` : undefined;
  })();
  // Validation-violation deep link: `#entities:<uuid>` opens the entity drawer directly.
  const entitiesInitial = (() => {
    const raw = window.location.hash.replace(/^#/, "");
    return raw.startsWith("entities:")
      ? decodeURIComponent(raw.slice("entities:".length)) || undefined
      : undefined;
  })();

  // Sidebar pending-review badge: real count; failures (403/network) stay silent.
  const pendingQuery = useQuery({
    queryKey: ["ontology", "pending-review-count"],
    queryFn: fetchPendingReviewCount,
    staleTime: 30_000,
    retry: false,
  });
  const pendingCount = pendingQuery.data ?? 0;

  // Sidebar collapse: icon-rail mode; preference persisted.
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
        /* ignore private mode */
      }
      return !prev;
    });
  };

  // Mobile drawer + theme + command palette + notification popover.
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem("ontostudio-theme") === "dark";
    } catch {
      return false;
    }
  });
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("ontostudio-theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);

  useEffect(() => {
    setMobileOpen(false);
  }, [route]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
        setNotifOpen(false);
        setMobileOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!paletteOpen) return;
    setQuery("");
    setSelected(0);
  }, [paletteOpen]);

  useEffect(() => {
    if (!notifOpen) return;
    const onDown = (event: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setNotifOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [notifOpen]);

  const needle = query.trim().toLowerCase();
  // Rank label hits above description hits so typing “校验” opens 校验中心 first.
  const searchScore = (id: RouteId): number => {
    const label = ROUTE_LABEL[id].toLowerCase();
    if (label === needle) return 0;
    if (label.startsWith(needle)) return 1;
    if (label.includes(needle)) return 2;
    if (ROUTE_GROUP[id].toLowerCase().includes(needle)) return 3;
    if (`${ROUTE_NO[id]} ${ROUTE_DESC[id]}`.toLowerCase().includes(needle)) return 4;
    return -1;
  };
  const paletteItems = ROUTE_IDS.map((id) => ({ id, score: needle ? searchScore(id) : 0 }))
    .filter((item) => item.score >= 0)
    .sort((a, b) => a.score - b.score)
    .map((item) => item.id);
  const activeIndex = Math.min(selected, Math.max(0, paletteItems.length - 1));

  const openRoute = (id: RouteId) => {
    go(id);
    setPaletteOpen(false);
  };

  const themeLabel = dark ? "切换浅色模式" : "切换深色模式";

  return (
    <div className="bg-background flex h-full min-h-0 overflow-hidden">
      {mobileOpen ? (
        <div
          className="fixed inset-0 z-30 bg-black/40 min-[901px]:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      ) : null}

      <aside
        className={cn("os-sidebar", collapsed && "collapsed", mobileOpen && "open")}
      >
        <div className="os-brand">
          <div className="os-brand-logo">
            <Network />
          </div>
          <div className="os-brand-text min-w-0">
            <h1>OntoStudio</h1>
            <p>
              本体建模工作台 <span className="os-brand-ver">v0.1</span>
            </p>
          </div>
          <button
            type="button"
            className="os-icon-btn os-side-close"
            onClick={() => setMobileOpen(false)}
            aria-label="关闭菜单"
          >
            <X />
          </button>
        </div>

        <div className="os-side-search">
          <button type="button" onClick={() => setPaletteOpen(true)}>
            <Search className="h-3.5 w-3.5" />
            <span>搜索页面…</span>
            <kbd>⌘K</kbd>
          </button>
        </div>

        <nav className="os-nav">
          {NAV.map((section, sectionIndex) => (
            <div className="os-nav-group" key={section.group}>
              <div className="os-nav-label">
                <span className="os-nav-code">
                  {String(sectionIndex + 1).padStart(2, "0")}
                </span>
                {section.group}
              </div>
              {section.items.map(([id, label]) => {
                const ItemIcon = ROUTE_ICON[id];
                const on = route === id;
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => {
                      go(id);
                      setMobileOpen(false);
                    }}
                    aria-current={on ? "page" : undefined}
                    title={collapsed ? `${ROUTE_NO[id]} ${label}` : label}
                    className={cn("os-nav-item", on && "on")}
                  >
                    <ItemIcon />
                    <span className="os-nav-text flex-1 truncate">{label}</span>
                    {id === "resolve" && pendingCount > 0 ? (
                      <span
                        className="os-badge"
                        title={`${pendingCount} 个实体待复核`}
                      >
                        {pendingCount > 99 ? "99+" : pendingCount}
                      </span>
                    ) : null}
                    {id === "resolve" && pendingCount > 0 && collapsed ? (
                      <span className="bg-destructive absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full" />
                    ) : null}
                  </button>
                );
              })}
            </div>
          ))}
          <div className="os-nav-group">
            <div className="os-nav-label">
              <span className="os-nav-code">05</span>
              文档
            </div>
            <a
              href="/ontostudio/docs/"
              target="_blank"
              rel="noreferrer"
              title="文档中心"
              className="os-nav-item"
            >
              <BookOpen />
              <span className="os-nav-text flex-1 truncate">文档中心</span>
              <span className="os-nav-text text-muted-foreground text-[9px]">
                新窗口
              </span>
            </a>
          </div>
        </nav>

        <div className="os-side-foot">
          <span className="os-avatar">{me.avatarChar || "·"}</span>
          <div className="os-side-foot-text min-w-0 flex-1 leading-tight">
            <b className="block truncate text-[11.5px] font-semibold">
              {me.fullName || me.email || "未登录"}
            </b>
            <span className="text-muted-foreground block truncate text-[9.5px]">
              {me.deptName || me.email || "—"}
            </span>
          </div>
          <button
            type="button"
            onClick={toggleCollapsed}
            title={collapsed ? "展开菜单" : "收起菜单"}
            aria-label={collapsed ? "展开菜单" : "收起菜单"}
            className="os-icon-btn os-side-collapse"
          >
            <PanelLeftClose />
          </button>
          <button
            type="button"
            onClick={toggleCollapsed}
            title="展开菜单"
            aria-label="展开菜单"
            className="os-icon-btn os-side-expand"
          >
            <PanelLeftOpen />
          </button>
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="os-topbar">
          <button
            type="button"
            className="os-icon-btn os-menu-btn"
            onClick={() => setMobileOpen(true)}
            aria-label="打开菜单"
          >
            <Menu />
          </button>

          <div className="os-crumb">
            <span className="os-crumb-root">本体工作台</span>
            <ChevronRight className="os-crumb-root h-3 w-3" />
            <span className="os-crumb-group">{ROUTE_GROUP[route]}</span>
            <ChevronRight className="os-crumb-group h-3 w-3" />
            <b>{ROUTE_LABEL[route]}</b>
          </div>

          <div className="os-top-search">
            <button type="button" onClick={() => setPaletteOpen(true)}>
              <Search className="h-3.5 w-3.5" />
              <span>搜索页面、功能与跳转…</span>
              <kbd>⌘K</kbd>
            </button>
          </div>

          <div className="os-top-actions">
            <a
              href="/ontostudio/docs/"
              target="_blank"
              rel="noreferrer"
              className="os-icon-btn os-top-docs"
              title="文档中心"
              aria-label="文档中心"
            >
              <BookOpen />
            </a>
            <button
              type="button"
              className="os-icon-btn"
              onClick={() => setDark((value) => !value)}
              title={themeLabel}
              aria-label={themeLabel}
            >
              {dark ? <Sun /> : <Moon />}
            </button>
            <div className="relative" ref={notifRef}>
              <button
                type="button"
                className="os-icon-btn"
                onClick={() => setNotifOpen((open) => !open)}
                title="待办提醒"
                aria-label="待办提醒"
              >
                <Bell />
                {pendingCount > 0 ? <span className="os-notif-dot" /> : null}
              </button>
              {notifOpen ? (
                <div className="os-popover">
                  <div className="os-pop-hd">
                    <Bell className="h-3.5 w-3.5" />
                    待办提醒
                    {pendingCount > 0 ? (
                      <span className="os-pill os-pill-err ml-auto">
                        {pendingCount}
                      </span>
                    ) : null}
                  </div>
                  {pendingCount > 0 ? (
                    <button
                      type="button"
                      className="os-pop-item"
                      onClick={() => {
                        openRoute("resolve");
                        setNotifOpen(false);
                      }}
                    >
                      <GitMerge className="text-primary mt-0.5 h-3.5 w-3.5 flex-none" />
                      <span>
                        <b className="block text-[10.5px] font-semibold">
                          {pendingCount} 个实体待复核
                        </b>
                        <span className="text-muted-foreground">
                          消解审核 · 合并 / 拆分待确认
                        </span>
                      </span>
                    </button>
                  ) : (
                    <div className="text-muted-foreground px-3 py-5 text-center text-[10px]">
                      暂无待办
                    </div>
                  )}
                  <button
                    type="button"
                    className="os-pop-foot w-full"
                    onClick={() => {
                      openRoute("resolve");
                      setNotifOpen(false);
                    }}
                  >
                    查看全部待办 →
                  </button>
                </div>
              ) : null}
            </div>
            <div className="os-divider" />
            <div className="os-user-chip">
              <span className="os-avatar sm">{me.avatarChar || "·"}</span>
              <div className="os-user-meta min-w-0">
                <b>{me.fullName || me.email || "未登录"}</b>
                <span>{me.deptName || "本体建模"}</span>
              </div>
            </div>
          </div>
        </header>

        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
          {/* graph/resolve stay mounted: hidden on other routes to preserve sigma state. */}
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

      {paletteOpen ? (
        <div
          className="os-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setPaletteOpen(false);
          }}
        >
          <div
            className="os-palette"
            role="dialog"
            aria-modal="true"
            aria-label="快速跳转"
          >
            <div className="os-palette-input">
              <Search />
              <input
                autoFocus
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setSelected(0);
                }}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setSelected((value) =>
                      Math.min(value + 1, Math.max(0, paletteItems.length - 1)),
                    );
                  } else if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setSelected((value) => Math.max(0, value - 1));
                  } else if (event.key === "Enter") {
                    const item = paletteItems[activeIndex];
                    if (item) openRoute(item);
                  }
                }}
                placeholder="搜索页面或功能…"
                aria-label="搜索页面或功能"
              />
              <kbd>ESC</kbd>
            </div>
            <div className="os-palette-list">
              {paletteItems.length > 0 ? (
                <>
                  <div className="os-palette-cat">导航</div>
                  {paletteItems.map((id, index) => {
                    const ItemIcon = ROUTE_ICON[id];
                    return (
                      <button
                        key={id}
                        type="button"
                        className={cn("os-palette-item", index === activeIndex && "on")}
                        onMouseEnter={() => setSelected(index)}
                        onClick={() => openRoute(id)}
                      >
                        <ItemIcon />
                        <span className="min-w-0 flex-1">
                          <b>{ROUTE_LABEL[id]}</b>
                          <span>{ROUTE_DESC[id]}</span>
                        </span>
                        <kbd>
                          {ROUTE_NO[id]} · {ROUTE_GROUP[id]}
                        </kbd>
                      </button>
                    );
                  })}
                </>
              ) : (
                <div className="text-muted-foreground px-3 py-8 text-center text-[11px]">
                  没有匹配的页面
                </div>
              )}
            </div>
            <div className="os-palette-foot">
              <span>↑↓ 选择</span>
              <span>↵ 打开</span>
              <span>esc 关闭</span>
              <span className="ml-auto">OntoStudio 快速跳转</span>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
