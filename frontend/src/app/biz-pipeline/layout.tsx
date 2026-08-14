"use client";

import { LayoutDashboard, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { usePermission } from "@/core/permissions";
import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 子路由映射到子页面权限点(/api/permissions/me 的 pages),供 canPage 过滤
const navItems = [
  { href: "/biz-pipeline", label: "管线仪表盘", icon: LayoutDashboard, exact: true, pageId: "bpp:page:dashboard" },
  { href: "/biz-pipeline/query", label: "数据查询", icon: Search, pageId: "bpp:page:query" },
];

function BizPipelineLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  // EAI-CUSTOM: 权限加载中 fail-open 全显,加载完按 canPage(pageId) 过滤
  const visibleItems = isLoading ? navItems : navItems.filter((n) => canPage(n.pageId));

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="flex h-16 shrink-0 items-center border-b border-border bg-background px-6">
        <span className="mr-8 text-lg font-bold tracking-tight text-foreground">管线查询</span>
        <nav className="flex h-full items-center gap-6 text-sm font-medium text-muted-foreground">
          {visibleItems.map(({ href, label, icon: Icon, exact }) => {
            const isActive = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex h-full items-center gap-1.5 border-b-2 py-5 transition-colors",
                  isActive ? "border-primary text-primary" : "border-transparent hover:text-foreground",
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

export default function BizPipelineLayout({ children }: { children: ReactNode }) {
  return (
    <ShellLayout>
      <BizPipelineLayoutContent>{children}</BizPipelineLayoutContent>
    </ShellLayout>
  );
}
