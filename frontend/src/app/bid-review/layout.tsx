"use client";

import { BookOpen, ClipboardCheck, FileText, ListChecks } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { usePermission } from "@/core/permissions";
import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 子路由映射到子页面权限点(/api/permissions/me 的 pages),供 canPage 过滤。
// bid-review 此前无 layout(六兄弟扩展模块中唯一缺席),四页仅任务列表可达,
// 规则库页完全无站内入口(Task 17 遗留,e242a00bf ②;micro-B 2026-10-29 按
// contract-price/bid-quote 子路由导航先例补齐,勿自创导航形态)
const navItems = [
  {
    href: "/bid-review",
    label: "任务列表",
    icon: ListChecks,
    exact: true,
    pageId: "bid:page:tasks",
  },
  {
    href: "/bid-review/workbench",
    label: "审查工作台",
    icon: FileText,
    pageId: "bid:page:workbench",
  },
  {
    href: "/bid-review/baseline",
    label: "基准确认",
    icon: ClipboardCheck,
    pageId: "bid:page:baseline",
  },
  {
    href: "/bid-review/rules",
    label: "规则库",
    icon: BookOpen,
    pageId: "bid:page:rules",
  },
];

function BidReviewLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  // EAI-CUSTOM: 权限加载中 fail-open 全显,加载完按 canPage(pageId) 过滤
  const visibleItems = isLoading
    ? navItems
    : navItems.filter((n) => canPage(n.pageId));

  return (
    <div className="bg-background flex h-full flex-col">
      <header className="border-border bg-background flex h-16 shrink-0 items-center border-b px-6">
        <span className="text-foreground mr-8 text-lg font-bold tracking-tight">
          投标方案审查
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

export default function BidReviewLayout({ children }: { children: ReactNode }) {
  return (
    <ShellLayout>
      <BidReviewLayoutContent>{children}</BidReviewLayoutContent>
    </ShellLayout>
  );
}
