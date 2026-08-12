"use client";

import {
  LayoutDashboard,
  FileText,
  Boxes,
  ListChecks,
  History,
  Settings,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { usePermission } from "@/core/permissions";
import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 每个子路由映射到子页面权限点（/api/permissions/me 的 pages），供 canPage 过滤
const navItems = [
  { href: "/spare-parts", label: "总览", icon: LayoutDashboard, exact: true, pageId: "csp:page:overview" },
  { href: "/spare-parts/contracts", label: "文档解析", icon: FileText, pageId: "csp:page:contracts" },
  { href: "/spare-parts/customers", label: "客户管理", icon: Users, pageId: "csp:page:customers" },
  { href: "/spare-parts/items", label: "分项校验", icon: ListChecks, pageId: "csp:page:items" },
  { href: "/spare-parts/clusters", label: "分组审核", icon: Boxes, pageId: "csp:page:clusters" },
  { href: "/spare-parts/tasks", label: "任务中心", icon: History, pageId: "csp:page:tasks" },
  { href: "/spare-parts/settings", label: "配置", icon: Settings, pageId: "csp:page:settings" },
];

function SparePartsLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  // EAI-CUSTOM: 权限加载中 fail-open 全显，加载完成后按 canPage(pageId) 过滤不可见子路由
  const visibleItems = isLoading ? navItems : navItems.filter((n) => canPage(n.pageId));

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="flex h-16 shrink-0 items-center border-b border-border bg-background px-6">
        <span className="mr-8 text-lg font-bold tracking-tight text-foreground">
          备品备件价格分析
        </span>
        <nav className="flex h-full items-center gap-6 text-sm font-medium text-muted-foreground">
          {visibleItems.map(({ href, label, icon: Icon, exact }) => {
            const isActive = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex h-full items-center gap-1.5 border-b-2 py-5 transition-colors",
                  isActive
                    ? "border-primary text-primary"
                    : "border-transparent hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </header>
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">{children}</div>
    </div>
  );
}

export default function SparePartsLayout({ children }: { children: ReactNode }) {
  return (
    <ShellLayout>
      <SparePartsLayoutContent>{children}</SparePartsLayoutContent>
    </ShellLayout>
  );
}
