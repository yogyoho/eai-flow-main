"use client";

import {
  Bot,
  Factory,
  BookOpen,
  Settings2,
  Settings,
  LogOut,
  UserCircle,
  FolderCheck,
  ClipboardList,
  LayoutDashboard,
  Blocks,
  KanbanSquare,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { useAuth } from "@/extensions/hooks/useAuth";
import { useLicense } from "@/extensions/license/useLicense";
import { usePermission } from "@/core/permissions";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  adminOnly?: boolean;
  /** If set, this nav item is hidden when the license module is not authorized */
  licenseModule?: string;
  navId?: string;
  newTab?: boolean;
}

const allNavItems: NavItem[] = [
  { href: "/dashboard", label: "工作台", icon: LayoutDashboard, licenseModule: "dashboard", navId: "nav:dashboard" },
  { href: "/writing", label: "智能写作", icon: Bot, newTab: true, licenseModule: "platform", navId: "nav:writing" },
  { href: "/projects", label: "报告项目", icon: ClipboardList, licenseModule: "project", navId: "nav:projects" },
  // EAI-CUSTOM: Collab Workspace 协作工作台（避开 /workspace 对话布局，独立路由）
  { href: "/agentspace", label: "协作工作台", icon: KanbanSquare, licenseModule: "platform", navId: "nav:collab-workspace" },
  { href: "/docmgr", label: "文档空间", icon: FolderCheck, licenseModule: "platform", navId: "nav:docmgr" },
  { href: "/knowledge-factory", label: "知识工厂", icon: Factory, licenseModule: "platform", navId: "nav:knowledge-factory" },
  { href: "/knowledge", label: "知识库", icon: BookOpen, licenseModule: "platform", navId: "nav:knowledge" },
  { href: "/app-center", label: "应用中心", icon: Blocks, licenseModule: "platform", navId: "nav:app-center" },
  { href: "/admin", label: "系统管理", icon: Settings2, adminOnly: true, licenseModule: "platform", navId: "nav:admin" },
  { href: "/settings", label: "设置", icon: Settings, licenseModule: "platform", navId: "nav:settings" },
];

const bottomNavItems: NavItem[] = [];

function NavIcon({
  href,
  label,
  icon: Icon,
  isActive,
  newTab,
}: {
  href: string;
  label: string;
  icon: React.ElementType;
  isActive: boolean;
  newTab?: boolean;
}) {
  return (
    <Tooltip delayDuration={300}>
      <TooltipTrigger asChild>
        <Link
          href={href}
          target={newTab ? "_blank" : undefined}
          className={cn(
            "flex items-center justify-center w-10 h-10 rounded-lg transition-colors",
            isActive
              ? "text-primary bg-primary/10"
              : "text-muted-foreground hover:text-primary hover:bg-accent"
          )}
        >
          <Icon className="h-5 w-5" />
        </Link>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

export function ExtensionsSidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { hasModule, isLoading: licenseLoading } = useLicense();
  const { canNav, is_admin, isLoading } = usePermission();
  const [mounted, setMounted] = useState(false);

  // EAI-CUSTOM: gate admin nav by permission-system is_admin (A3/U2), not display-name check.
  // Fail-open during /me load so the admin entry doesn't flash-hidden (Task 15 convention).
  const isAdmin = isLoading || is_admin;

  // Filter by admin role + license module authorization + nav-level permission
  const navItems = allNavItems.filter((item) => {
    // Admin-only items: skip if not admin
    if (item.adminOnly && !isAdmin) return false;
    // License-gated items: skip if module not authorized (show during loading)
    if (item.licenseModule && !licenseLoading && !hasModule(item.licenseModule)) return false;
    // Nav-level permission: skip if user doesn't have nav permission
    if (item.navId && !canNav(item.navId)) return false;
    return true;
  });

  // EAI-CUSTOM (nav flash fix): 权限/许可证加载完成前不渲染导航项——用骨架屏占位保持
  // 布局稳定，避免 canNav 加载期 fail-open 导致的"无权图标闪现后消失"。
  const navReady = !isLoading && !licenseLoading;

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleLogout = () => {
    logout();
  };

  return (
    <TooltipProvider delayDuration={300}>
      <div className="relative z-30 w-14 shrink-0 flex flex-col items-center border-r border-border bg-background dark:bg-sidebar">
        {/* Logo */}
        <div className="p-3">
          <Link
            href="/"
            className="w-9 h-9 rounded-lg flex items-center justify-center hover:bg-accent transition-colors"
          >
            <img src="/favicon.svg" alt="Logo" className="w-7 h-7" />
          </Link>
        </div>

        {/* Main navigation */}
        <nav className="flex flex-col items-center py-4 gap-2 flex-1">
          {!navReady ? (
            /* Skeleton while permissions/license resolve — nothing flashes in/out */
            Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="w-10 h-10 rounded-lg bg-muted/60 animate-pulse" />
            ))
          ) : (
            navItems.map(({ href, label, icon, newTab }) => {
              const isActive =
                pathname === href ||
                (href !== "/" && pathname.startsWith(href + "/"));
              return (
                <NavIcon
                  key={href}
                  href={href}
                  label={label}
                  icon={icon}
                  isActive={isActive}
                  newTab={newTab}
                />
              );
            })
          )}
        </nav>

        {/* Bottom navigation (settings) */}
        <nav className="flex flex-col items-center gap-2 mt-auto">
          {bottomNavItems.map(({ href, label, icon }) => {
            const isActive = pathname === href;
            return (
              <NavIcon
                key={href}
                href={href}
                label={label}
                icon={icon}
                isActive={isActive}
              />
            );
          })}
        </nav>

        {/* User menu */}
        <div className="p-2 flex flex-col items-center gap-1">
          {mounted && (
            <DropdownMenu>
              <Tooltip delayDuration={300}>
                <TooltipTrigger asChild>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="flex items-center justify-center w-10 h-10 rounded-lg text-muted-foreground hover:text-primary hover:bg-accent transition-colors"
                    >
                      <UserCircle className="h-5 w-5" />
                    </button>
                  </DropdownMenuTrigger>
                </TooltipTrigger>
                <TooltipContent side="right" sideOffset={8}>
                  用户信息
                </TooltipContent>
              </Tooltip>
              <DropdownMenuContent side="right" sideOffset={8} className="w-48">
                <div className="px-2 py-2 border-b border-border">
                  <div className="text-sm font-medium text-foreground">
                    {user?.username ?? "—"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {user?.role_name ?? ""}
                  </div>
                </div>
                <DropdownMenuItem
                  className="cursor-pointer text-destructive focus:text-destructive"
                  onClick={handleLogout}
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  退出登录
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}