"use client";

// EAI-CUSTOM (translation 一期): 必须走 ShellLayout —— 它提供 QueryClientProvider/PermissionProvider,
// AssetLibrary 里的 TanStack hooks 与权限过滤都依赖这些 Provider（同 geo-samples/contract-price 布局）。
import {
  BookMarked,
  ClipboardCheck,
  FolderOpen,
  Languages,
  ListChecks,
  Settings,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { usePermission } from "@/core/permissions";
import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

import Metadata from "./metadata";

// 子路由映射到子页面权限点（/api/permissions/me 的 pages），供 canPage 过滤；
const navItems = [
  {
    href: "/translation",
    label: "文档资产库",
    icon: FolderOpen,
    exact: true,
    pageId: "translation:page:assets",
  },
  {
    href: "/translation/tasks",
    label: "任务管理",
    icon: ListChecks,
    exact: false,
    pageId: "translation:page:assets",
  },
  {
    href: "/translation/review",
    label: "复核工作台",
    icon: ClipboardCheck,
    exact: false,
    pageId: "translation:page:assets",
  },
  {
    href: "/translation/glossary",
    label: "术语库",
    icon: BookMarked,
    exact: false,
    pageId: "translation:page:assets",
  },
  {
    href: "/translation/settings",
    label: "设置",
    icon: Settings,
    exact: false,
    pageId: "translation:page:assets",
  },
];

function TranslationLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  // 权限加载中 fail-open 全显，加载完成后按 canPage(pageId) 过滤不可见子路由
  const visibleItems = isLoading
    ? navItems
    : navItems.filter((n) => canPage(n.pageId));

  return (
    <div className="bg-background flex h-full flex-col">
      <Metadata />
      <header className="border-border bg-background flex h-16 shrink-0 items-center border-b px-6">
        <span className="text-foreground mr-8 flex items-center gap-2 text-lg font-bold tracking-tight">
          <Languages className="h-5 w-5" />
          文档翻译工作台
        </span>
        <nav className="text-muted-foreground flex h-full items-center gap-6 text-sm font-medium">
          {visibleItems.map(({ href, label, icon: Icon, exact }) => {
            const isActive = exact
              ? pathname === href
              : (pathname?.startsWith(href) ?? false);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex h-full items-center gap-1.5 border-b-2 px-1",
                  isActive
                    ? "border-primary text-foreground"
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
      <div className="min-h-0 flex-1">{children}</div>
      {/* 操作反馈 toast（sonner,右下角)——对齐知识工厂,替代各 tab 内嵌通知条 */}
      <Toaster />
    </div>
  );
}

export default function TranslationLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <ShellLayout>
      <TranslationLayoutContent>{children}</TranslationLayoutContent>
    </ShellLayout>
  );
}
