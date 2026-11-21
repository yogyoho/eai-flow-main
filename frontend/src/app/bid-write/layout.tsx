"use client";

import {
  Bolt,
  BookMarked,
  LibraryBig,
  BookOpen,
  Boxes,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FileArchive,
  FileText,
  FolderKanban,
  Moon,
  Sun,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import { QueryClientProvider } from "@/components/query-client-provider";
import { Toaster } from "@/components/ui/sonner";
import { WorkspaceLoginRedirect } from "@/components/workspace/workspace-login-redirect";
import { PermissionProvider } from "@/core/permissions";
import { useBidWriteTasks } from "@/extensions/bid-write/hooks";
import {
  effectiveWriteTaskId,
  writeNavBadges,
  writeTaskHref,
  WRITE_PAGE_PATHS,
  type WritePage,
} from "@/extensions/bid-write/nav";
import type { WriteTaskOut } from "@/extensions/bid-write/types";
import { AuthProvider, useAuth } from "@/extensions/hooks/useAuth";
import { cn } from "@/lib/utils";

import "../bid-review/bid-review.css";
import "./bid-write.css";

const navItems: Array<{
  href: string;
  label: string;
  icon: typeof FolderKanban;
  exact?: boolean;
  group: 0 | 1 | 2;
  taskPage?: WritePage;
  badge?: "active" | "blocked";
}> = [
  {
    href: WRITE_PAGE_PATHS.projects,
    label: "项目列表",
    icon: FolderKanban,
    exact: true,
    group: 0,
    badge: "active",
  },
  {
    href: WRITE_PAGE_PATHS.intake,
    label: "① 解析确认",
    icon: FileText,
    group: 0,
    taskPage: "intake",
    badge: "blocked",
  },
  {
    href: WRITE_PAGE_PATHS.materials,
    label: "② 素材核对",
    icon: Boxes,
    group: 0,
    taskPage: "materials",
  },
  {
    href: WRITE_PAGE_PATHS.generate,
    label: "③ 生成配置",
    icon: Bolt,
    group: 0,
    taskPage: "generate",
  },
  {
    href: WRITE_PAGE_PATHS.workbench,
    label: "④ 写作工作台",
    icon: BookOpen,
    group: 0,
    taskPage: "workbench",
  },
  {
    href: WRITE_PAGE_PATHS.review,
    label: "⑤ 预审查",
    icon: ClipboardList,
    group: 1,
    taskPage: "review",
  },
  {
    href: WRITE_PAGE_PATHS.export,
    label: "⑥ 导出适配",
    icon: FileArchive,
    group: 1,
    taskPage: "export",
  },
  {
    href: WRITE_PAGE_PATHS.materials_library,
    label: "资质素材库",
    icon: LibraryBig,
    group: 2,
    taskPage: "materials_library",
  },
  {
    href: WRITE_PAGE_PATHS.registry,
    label: "质量规则中心",
    icon: BookMarked,
    group: 2,
  },
];

const GROUP_LABELS = ["写作闭环", "质量与交付", "治理"];

function StandaloneGate({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return <div className="brx brx-splash" aria-busy="true" />;
  }
  if (!user) {
    return <WorkspaceLoginRedirect />;
  }
  return <>{children}</>;
}

function useDarkTheme() {
  const [dark, setDark] = useState<boolean | null>(null);
  useEffect(() => {
    try {
      setDark(window.localStorage.getItem("br-theme") === "dark" ? true : null);
    } catch {
      setDark(null);
    }
  }, []);
  const toggle = () => {
    setDark((prev) => {
      const systemDark = window.matchMedia(
        "(prefers-color-scheme: dark)",
      ).matches;
      const current = prev ?? systemDark;
      const next = !current;
      try {
        if (next) window.localStorage.setItem("br-theme", "dark");
        else window.localStorage.removeItem("br-theme");
      } catch {
        // storage 不可用时仅本次会话生效
      }
      return next;
    });
  };
  return { dark, toggle };
}

function WriteNavGroups({
  groups,
  badges,
  tasks,
  collapsed = false,
}: {
  groups: Array<Array<(typeof navItems)[number]>>;
  badges: ReturnType<typeof writeNavBadges>;
  tasks: WriteTaskOut[] | undefined;
  /** 收起态:仅图标列,悬停以 title 提示菜单名。 */
  collapsed?: boolean;
}) {
  const pathname = usePathname();
  const effId = effectiveWriteTaskId(
    tasks ?? [],
    useSearchParams().get("task_id"),
  );
  return (
    <>
      {groups.map((items, groupIndex) =>
        items.length === 0 ? null : (
          <nav className="chrome-group" key={groupIndex}>
            <div className="g-label">{GROUP_LABELS[groupIndex]}</div>
            {items.map(
              ({ href, label, icon: Icon, exact, badge, taskPage }) => {
                const isActive = exact
                  ? pathname === href
                  : pathname.startsWith(href);
                const linkHref =
                  taskPage && effId ? writeTaskHref(taskPage, effId) : href;
                const count = badge ? badges[badge] : 0;
                return (
                  <Link
                    key={href}
                    href={linkHref}
                    className={cn("nav-item", isActive && "on")}
                    title={collapsed ? label : undefined}
                  >
                    <Icon size={15} className="ic" aria-hidden="true" />
                    {label}
                    {badge && count > 0 ? (
                      <span
                        className={cn("nav-cnt", badge === "blocked" && "warn")}
                      >
                        {count}
                      </span>
                    ) : null}
                  </Link>
                );
              },
            )}
          </nav>
        ),
      )}
    </>
  );
}

function BidWriteLayoutContent({ children }: { children: ReactNode }) {
  const { dark, toggle } = useDarkTheme();
  const { data } = useBidWriteTasks();
  const tasks = data?.items ?? [];
  const badges = writeNavBadges(tasks, tasks[0]?.id ?? null);
  const groups = [0, 1, 2].map((group) =>
    navItems.filter((item) => item.group === group),
  );
  // 左侧菜单收起态。null=未从 storage 读出,首屏按展开渲染,避免 SSR 水合不一致。
  const [sideCollapsed, setSideCollapsed] = useState<boolean | null>(null);
  useEffect(() => {
    try {
      setSideCollapsed(
        window.localStorage.getItem("bw-side") === "collapsed",
      );
    } catch {
      setSideCollapsed(false);
    }
  }, []);
  const collapsed = sideCollapsed === true;
  const toggleSide = () => {
    setSideCollapsed((prev) => {
      const next = !(prev ?? false);
      try {
        if (next) window.localStorage.setItem("bw-side", "collapsed");
        else window.localStorage.removeItem("bw-side");
      } catch {
        // storage 不可用时仅本次会话生效
      }
      return next;
    });
  };

  return (
    <div
      className="brx bwx"
      data-theme={dark === true ? "dark" : dark === false ? "light" : undefined}
    >
      <div className={cn("chrome", collapsed && "bw-side-collapsed")}>
        <aside className="chrome-side">
          <div className="chrome-brand">
            <div className="brand-row">
              <BookOpen size={17} className="brand-ic" aria-hidden="true" />
              <div className="brand-txt">
                <h1>投标方案写作</h1>
                <p className="g-sub">Bid Proposal Writing</p>
              </div>
            </div>
          </div>
          <Suspense fallback={null}>
            <WriteNavGroups
              groups={groups}
              badges={badges}
              tasks={tasks}
              collapsed={collapsed}
            />
          </Suspense>
          <div className="chrome-foot">
            <button
              type="button"
              className="nav-item"
              onClick={toggle}
              title="切换深浅色"
            >
              {dark ? (
                <Sun size={15} className="ic" aria-hidden="true" />
              ) : (
                <Moon size={15} className="ic" aria-hidden="true" />
              )}
              深浅色
            </button>
          </div>
        </aside>
        {/* 收起/展开按钮挂在 .chrome 上:侧栏有 overflow,挂里面会被裁剪。 */}
        <button
          type="button"
          className="bw-side-toggle"
          onClick={toggleSide}
          aria-label={collapsed ? "展开菜单" : "收起菜单"}
          aria-expanded={!collapsed}
          title={collapsed ? "展开菜单" : "收起菜单"}
        >
          {collapsed ? (
            <ChevronRight size={14} aria-hidden="true" />
          ) : (
            <ChevronLeft size={14} aria-hidden="true" />
          )}
        </button>
        <main className="chrome-main">{children}</main>
      </div>
      <Toaster />
    </div>
  );
}

export default function BidWriteLayout({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider>
      <AuthProvider>
        <PermissionProvider>
          <StandaloneGate>
            <BidWriteLayoutContent>{children}</BidWriteLayoutContent>
          </StandaloneGate>
        </PermissionProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
