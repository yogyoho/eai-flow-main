"use client";

// EAI-CUSTOM: forked from app/bid-quote/layout.tsx (geo-sample-bank Phase 1).
// 必须走 ShellLayout —— 它提供 QueryClientProvider/PermissionProvider,
// usePermission 与视图里的 TanStack hooks 都依赖这些 Provider。
import { FileStack, History, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { usePermission } from "@/core/permissions";
import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 子路由映射到子页面权限点(/api/permissions/me 的 pages),供 canPage 过滤
const navItems = [
  {
    href: "/geo-samples",
    label: "样例文档库",
    icon: FileStack,
    exact: true,
    pageId: "gsb:page:documents",
  },
  {
    href: "/geo-samples/review",
    label: "脱敏抽审",
    icon: ShieldCheck,
    pageId: "gsb:page:review",
  },
  {
    href: "/geo-samples/tasks",
    label: "运行记录",
    icon: History,
    pageId: "gsb:page:tasks",
  },
];

function GeoSamplesLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  // EAI-CUSTOM: 权限加载中 fail-open 全显,加载完按 canPage(pageId) 过滤不可见子路由
  const visibleItems = isLoading
    ? navItems
    : navItems.filter((n) => canPage(n.pageId));

  return (
    <div className="bg-background flex h-full flex-col">
      <header className="border-border bg-background flex h-16 shrink-0 items-center border-b px-6">
        <span className="text-foreground mr-8 text-lg font-bold tracking-tight">
          地质样例库
        </span>
        <nav className="text-muted-foreground flex h-full items-center gap-6 text-sm font-medium">
          {visibleItems.map(({ href, label, icon: Icon, exact }) => {
            const isActive = exact
              ? pathname === href
              : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex h-full items-center gap-1.5 border-b-2 py-5 transition-colors",
                  isActive
                    ? "border-primary text-primary"
                    : "hover:text-foreground border-transparent",
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

export default function GeoSamplesLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <ShellLayout>
      <GeoSamplesLayoutContent>{children}</GeoSamplesLayoutContent>
    </ShellLayout>
  );
}
