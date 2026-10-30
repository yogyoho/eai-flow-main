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
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { QueryClientProvider } from "@/components/query-client-provider";
import { WorkspaceLoginRedirect } from "@/components/workspace/workspace-login-redirect";
import { usePermission, PermissionProvider } from "@/core/permissions";
import { AuthProvider, useAuth } from "@/extensions/hooks/useAuth";
import { cn } from "@/lib/utils";

import "./bid-review.css";

// EAI-CUSTOM (2026-10-30 独立子系统改造): /bid-review 脱离 EAI 壳(ShellLayout/
// ExtensionsSidebar),换为本组件自绘原型 chrome(参照 docs/designs/2026-10-30-bid-review-ui.html,
// 样式全量收敛在 .brx 根类)。入口约定:应用中心卡片 target=_blank 新 tab 打开
// (AppCard.tsx),站内其余入口不跳转至此。providers 自备(原由 ShellLayout 提供):
// QueryClientProvider + AuthProvider + PermissionProvider;登录门=StandaloneGate
// (未登录复用 WorkspaceLoginRedirect,fetcher 401 兜底跳登录由共享 fetcher 承担)。
// 子路由映射到子页面权限点(/api/permissions/me 的 pages),供 canPage 过滤——
// 此行为是 micro-B 回归门(tests/unit/app/bid-review-layout.dom.test.tsx)锁定契约,
// 导航文案/href 勿改;规则效果(metrics)挂 bid:page:rules(同治理域,无独立权限点)。
const navItems = [
  {
    href: "/bid-review",
    // 2026-10-30 用户定案:「任务总览」——首项即任务工作台(s1),改名与「审查工作台」区分
    label: "任务总览",
    icon: ListChecks,
    exact: true,
    pageId: "bid:page:tasks",
    group: 0,
  },
  {
    href: "/bid-review/workbench",
    label: "审查工作台",
    icon: FileText,
    pageId: "bid:page:workbench",
    group: 0,
  },
  {
    // EAI-CUSTOM (2026-10-31 二期 spec §五 s6):need_human 队列复核;
    // 挂 bid:page:workbench(同治理域,先例=metrics 挂 bid:page:rules)
    href: "/bid-review/review",
    label: "复核工作台",
    icon: UserCheck,
    pageId: "bid:page:workbench",
    group: 0,
  },
  {
    href: "/bid-review/baseline",
    label: "基准确认",
    icon: ClipboardCheck,
    pageId: "bid:page:baseline",
    group: 0,
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

function BidReviewLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  const { dark, toggle } = useDarkTheme();
  // EAI-CUSTOM: 权限加载中 fail-open 全显,加载完按 canPage(pageId) 过滤
  const visibleItems = isLoading
    ? navItems
    : navItems.filter((n) => canPage(n.pageId));
  const groups = [0, 1].map((g) => visibleItems.filter((n) => n.group === g));

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
          {groups.map((items, g) =>
            items.length === 0 ? null : (
              <nav className="chrome-group" key={g}>
                <div className="g-label">{GROUP_LABELS[g]}</div>
                {items.map(({ href, label, icon: Icon, exact }) => {
                  const isActive = exact
                    ? pathname === href
                    : pathname.startsWith(href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      className={cn("nav-item", isActive && "on")}
                    >
                      <Icon size={15} className="ic" aria-hidden="true" />
                      {label}
                    </Link>
                  );
                })}
              </nav>
            ),
          )}
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
