/**
 * OntoStudio 应用外壳（EAI-CUSTOM）：侧栏导航 + hash 路由（零新依赖）。
 * 视觉对照 docs/designs/ontostudio-frontend-design.html（青卷版）。
 *
 * 路由映射：01 总览 / 02 图谱 / 04 消解 → OntologyPage 真实三视图（常驻挂载，
 * 切去骨架页仅隐藏，避免 sigma 画布重载）；03/05-09 → 骨架占位页（src/pages/*）。
 */
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { fetchPendingReviewCount } from "@/api/ontology-graph-api";
import { OntologyPage, type PageView } from "@/components/OntologyPage";
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

/** 知识层三页 → OntologyPage 内部视图；onViewChange 反向映射回路由。 */
const ROUTE_VIEW: Partial<Record<RouteId, PageView>> = {
  dashboard: "overview",
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

/** hash 路由：解析非法/空 hash 落到 graph（知识层主视图）。 */
function useHashRoute(): [RouteId, (id: RouteId) => void] {
  const parse = useCallback((): RouteId => {
    const raw = window.location.hash.replace(/^#/, "");
    return (ROUTE_IDS as string[]).includes(raw) ? (raw as RouteId) : "graph";
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
  const knowledgeView = ROUTE_VIEW[route];

  // 侧栏消解待审红点：真实 pending 计数；失败（403/网络）静默隐藏
  const pendingQuery = useQuery({
    queryKey: ["ontology", "pending-review-count"],
    queryFn: fetchPendingReviewCount,
    staleTime: 30_000,
    retry: false,
  });
  const pendingCount = pendingQuery.data ?? 0;

  return (
    <div className="bg-background flex h-full min-h-0">
      <aside className="border-border bg-card flex w-56 flex-none flex-col border-r">
        <div className="border-border flex items-center gap-2.5 border-b px-4 py-4">
          <span className="bg-primary text-primary-foreground font-display grid h-8 w-8 flex-none place-items-center rounded-lg text-[15px] font-black">
            本
          </span>
          <div>
            <b className="font-display block text-[15px] leading-tight font-black tracking-wide">
              OntoStudio
            </b>
            <small className="text-muted-foreground text-[10.5px] tracking-[0.14em]">
              本体建模工作台
            </small>
          </div>
        </div>

        <nav className="min-h-0 flex-1 overflow-y-auto p-2">
          {NAV.map((section) => (
            <div key={section.group}>
              <div className="text-muted-foreground mt-3.5 px-2.5 pb-1 text-[10.5px] font-medium tracking-[0.1em]">
                {section.group}
              </div>
              {section.items.map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => go(id)}
                  aria-current={route === id ? "page" : undefined}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] font-medium transition-colors",
                    route === id
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  <span
                    className={cn(
                      "w-4 flex-none font-mono text-[10px]",
                      route === id
                        ? "text-primary-foreground/70"
                        : "text-muted-foreground/80",
                    )}
                  >
                    {ROUTE_NO[id]}
                  </span>
                  {label}
                  {id === "resolve" && pendingCount > 0 ? (
                    <span
                      className="bg-seal ml-auto h-1.5 w-1.5 rounded-full"
                      title={`${pendingCount} 个实体待复核`}
                    />
                  ) : null}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="border-border flex items-center gap-2.5 border-t px-4 py-3">
          <span className="bg-primary text-primary-foreground grid h-7 w-7 flex-none place-items-center rounded-full text-[11px] font-semibold">
            管
          </span>
          <div className="leading-tight">
            <b className="block text-xs font-medium">知识工程组</b>
            <span className="text-muted-foreground text-[10.5px]">admin@eai-flow.com</span>
          </div>
        </div>
      </aside>

      <main className="min-h-0 min-w-0 flex-1">
        {/* 知识层三视图常驻挂载：切骨架页时仅隐藏，保 sigma 画布/查询状态 */}
        <div className={cn("h-full min-h-0", knowledgeView ? "" : "hidden")}>
          <OntologyPage
            initialView={knowledgeView ?? "map"}
            onViewChange={(view) => go(VIEW_ROUTE[view])}
          />
        </div>
        {route === "entities" ? <EntitiesPage /> : null}
        {route === "modeler" ? <ModelerPage /> : null}
        {route === "reasoning" ? <ReasoningPage /> : null}
        {route === "validation" ? <ValidationPage /> : null}
        {route === "ingest" ? <IngestPage /> : null}
        {route === "export" ? <ExportPage /> : null}
      </main>
    </div>
  );
}
