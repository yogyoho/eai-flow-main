"use client";

import {
  BookOpen,
  ClipboardCheck,
  FileText,
  Gauge,
  ListChecks,
  Moon,
  Sun,
  UserCheck,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import { QueryClientProvider } from "@/components/query-client-provider";
import { WorkspaceLoginRedirect } from "@/components/workspace/workspace-login-redirect";
import { usePermission, PermissionProvider } from "@/core/permissions";
import { useBidTasks } from "@/extensions/bid-review/hooks";
import {
  sidebarBadges,
  taskHref,
  type SidebarBadges,
  type TaskPage,
} from "@/extensions/bid-review/nav";
import type { TaskOut } from "@/extensions/bid-review/types";
import { AuthProvider, useAuth } from "@/extensions/hooks/useAuth";
import { cn } from "@/lib/utils";

import "./bid-review.css";

// EAI-CUSTOM (2026-10-30 独立子系统改造;2026-10-31 UX 重构 Plan 1 流程化):
// /bid-review 脱离 EAI 壳(ShellLayout/ExtensionsSidebar),换为本组件自绘原型
// chrome(参照 docs/designs/2026-10-30-bid-review-ui.html,样式全量收敛在 .brx
// 根类)。入口约定:应用中心卡片 target=_blank 新 tab 打开(AppCard.tsx),站内
// 其余入口不跳转至此。providers 自备(原由 ShellLayout 提供):
// QueryClientProvider + AuthProvider + PermissionProvider;登录门=StandaloneGate
// (未登录复用 WorkspaceLoginRedirect,fetcher 401 兜底跳登录由共享 fetcher 承担)。
// 子路由映射到子页面权限点(/api/permissions/me 的 pages),供 canPage 过滤——
// micro-B 回归门(tests/unit/app/bid-review-layout.dom.test.tsx)锁定 href/label
// 契约,勿改。UX 重构 Plan 1:组 0 按审查闭环流程序排列(基准确认→复核工作台),
// 徽标数据来自共享 useBidTasks(badge 键见 SidebarBadges);/workbench 为 results
// 拆分(Plan 6)落地前的暂用路由,届时换 /results + 重定向 shim。徽标点击直达
// task_id 属任务选择器计划(Plan 3)——徽标在 Link 内,嵌套 <a> 非法。
const navItems: Array<{
  href: string;
  label: string;
  icon: typeof ListChecks;
  exact?: boolean;
  pageId: string;
  group: 0 | 1;
  badge?: keyof SidebarBadges;
  // UX 重构 Plan 2 T2(spec §3.2):任务链页 href 携带 effective task_id;
  // 治理页不挂,保持裸路径。
  taskPage?: TaskPage;
}> = [
  {
    href: "/bid-review",
    // 2026-10-30 用户定案:「任务总览」——首项即任务工作台(s1),改名与「审查工作台」区分
    label: "任务总览",
    icon: ListChecks,
    exact: true,
    pageId: "bid:page:tasks",
    group: 0,
    badge: "running",
    taskPage: "tasks",
  },
  {
    href: "/bid-review/workbench",
    label: "审查工作台",
    icon: FileText,
    pageId: "bid:page:workbench",
    group: 0,
    taskPage: "workbench",
  },
  {
    href: "/bid-review/baseline",
    label: "基准确认",
    icon: ClipboardCheck,
    pageId: "bid:page:baseline",
    group: 0,
    badge: "awaitingConfirm",
    taskPage: "baseline",
  },
  {
    // EAI-CUSTOM (2026-10-31 二期 spec §五 s6):need_human 队列复核;
    // 挂 bid:page:workbench(同治理域,先例=metrics 挂 bid:page:rules)
    href: "/bid-review/review",
    label: "复核工作台",
    icon: UserCheck,
    pageId: "bid:page:workbench",
    group: 0,
    badge: "reviewTodo",
    taskPage: "review",
  },
  {
    href: "/bid-review/rules",
    label: "规则库",
    icon: BookOpen,
    pageId: "bid:page:rules",
    group: 1,
  },
  {
    href: "/bid-review/metrics",
    label: "规则效果",
    icon: Gauge,
    pageId: "bid:page:rules",
    group: 1,
  },
];

const GROUP_LABELS = ["审查闭环", "规则治理"];

/** 未登录 → 复用 workspace 登录跳转(保留 returnPath);加载中给纯色底避免闪现。 */
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

/** 独立子系统的暗色开关:作用于 .brx 根(data-theme),localStorage 'br-theme'
 * 记忆;undefined = 跟随系统(prefers-color-scheme)。try/catch——storage 可能被禁。 */
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

/** 审查闭环 nav:任务链页 href 携带 effective task_id(六页互跳不断档,spec §3.2);
 * 治理页 href 保持裸路径。isActive 仍按基路径匹配(query 不参与)。
 * groups/badges/tasks 全部由父组件传入,本组件只补 useSearchParams 算 effective
 * (必须在 Suspense 边界内,由调用处包裹)。 */
function TaskNavGroups({
  groups,
  badges,
  tasks,
}: {
  groups: Array<Array<(typeof navItems)[number]>>;
  badges: SidebarBadges;
  tasks: TaskOut[] | undefined;
}) {
  const pathname = usePathname();
  const effId = useSearchParams().get("task_id") ?? tasks?.[0]?.id ?? null;
  return (
    <>
      {groups.map((items, g) =>
        items.length === 0 ? null : (
          <nav className="chrome-group" key={g}>
            <div className="g-label">{GROUP_LABELS[g]}</div>
            {items.map(({ href, label, icon: Icon, exact, badge, taskPage }) => {
              const isActive = exact
                ? pathname === href
                : pathname.startsWith(href);
              const linkHref =
                taskPage && effId ? taskHref(taskPage, effId) : href;
              const count = badge ? badges[badge] : 0;
              return (
                <Link
                  key={href}
                  href={linkHref}
                  className={cn("nav-item", isActive && "on")}
                >
                  <Icon size={15} className="ic" aria-hidden="true" />
                  {label}
                  {badge && count > 0 ? (
                    <span
                      className={cn(
                        "nav-cnt",
                        badge === "awaitingConfirm" && "warn",
                      )}
                    >
                      {count}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </nav>
        ),
      )}
    </>
  );
}

function BidReviewLayoutContent({ children }: { children: ReactNode }) {
  const { canPage, isLoading } = usePermission();
  const { dark, toggle } = useDarkTheme();
  // EAI-CUSTOM: 权限加载中 fail-open 全显,加载完按 canPage(pageId) 过滤
  const visibleItems = isLoading
    ? navItems
    : navItems.filter((n) => canPage(n.pageId));
  const groups = [0, 1].map((g) => visibleItems.filter((n) => n.group === g));
  // 徽标共享查询(与 TasksView 同 key 同缓存);数据未到时徽标不渲染(禁伪零)
  const { data: tasks } = useBidTasks();
  const badges = sidebarBadges(tasks ?? []);

  return (
    <div
      className="brx"
      data-theme={dark === true ? "dark" : dark === false ? "light" : undefined}
    >
      <div className="chrome">
        <aside className="chrome-side">
          <div className="chrome-brand">
            <div className="brand-row">
              <ClipboardCheck
                size={17}
                className="brand-ic"
                aria-hidden="true"
              />
              <div className="brand-txt">
                <h1>投标方案审查</h1>
                <p className="g-sub">Bid Proposal Review</p>
              </div>
            </div>
          </div>
          {/* 2026-10-31 用户定案:选中任务号不进侧栏(原 chip 摘除),
              随各页页头标题展示(TaskTitleTag,见 components/TaskTitleTag.tsx) */}
          <Suspense fallback={null}>
            <TaskNavGroups groups={groups} badges={badges} tasks={tasks} />
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
        <main className="chrome-main">{children}</main>
      </div>
    </div>
  );
}

export default function BidReviewLayout({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider>
      <AuthProvider>
        <PermissionProvider>
          <StandaloneGate>
            <BidReviewLayoutContent>{children}</BidReviewLayoutContent>
          </StandaloneGate>
        </PermissionProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
