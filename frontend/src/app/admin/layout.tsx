"use client";

import {
  Users,
  Shield,
  Network,
  Loader2,
  Settings2,
  Blocks,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";
// EAI-CUSTOM: button-level permission control
import { PermissionProvider, usePermission } from "@/core/permissions";
import { useAuth } from "@/extensions/hooks/useAuth";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/admin/users", label: "用户管理", icon: Users },
  { href: "/admin/roles", label: "角色管理", icon: Shield },
  { href: "/admin/departments", label: "部门管理", icon: Network },
  { href: "/admin/app-center", label: "应用管理", icon: Blocks },
];

/** Check if the current user has admin privileges. */
function isAdmin(roleName?: string | null): boolean {
  // EAI-CUSTOM: A3 顶层判权在 PermissionProvider 挂载前，显示名仅作兜底（含中文显示名）；
  // 真实权威以 /api/permissions/me 的 is_admin（角色 is_system）为准。
  return roleName === "Super Admin" || roleName === "超级管理员";
}

function AdminLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // EAI-CUSTOM: A3 以 /me 的 is_admin（角色 is_system）为准，替代仅靠显示名判权；
  // 加载中 fail-open 显示导航（与 canNav 的既有约定一致），避免闪跳。
  const { is_admin, isLoading } = usePermission();
  const showNav = isLoading || is_admin;

  return (
    <div className="bg-background flex h-full flex-col">
      {/* Top navigation bar */}
      <header className="bg-background border-border flex h-16 shrink-0 items-center border-b px-6">
        <div className="mr-3 shrink-0 rounded-sm border border-slate-200 bg-slate-50 p-1 text-slate-600">
          <Settings2 className="h-4 w-4" />
        </div>
        <span className="text-foreground mr-8 text-lg font-bold tracking-tight">
          系统管理
        </span>
        <nav className="text-muted-foreground flex h-full items-center gap-6 text-sm font-medium">
          {showNav &&
            navItems.map(({ href, label }) => {
              const isActive = pathname === href;
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex h-full items-center border-b-2 py-5 transition-colors",
                    isActive
                      ? "text-primary border-primary"
                      : "hover:text-foreground border-transparent",
                  )}
                >
                  {label}
                </Link>
              );
            })}
        </nav>
      </header>

      {/* Main content area */}
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}

export default function AdminLayout({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAdmin(user?.role_name)) {
      router.replace("/dashboard");
    }
  }, [isLoading, user, router]);

  if (isLoading) {
    return (
      <SimpleShellLayout>
        <div className="flex h-full items-center justify-center">
          <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
        </div>
      </SimpleShellLayout>
    );
  }

  if (!isAdmin(user?.role_name)) {
    return null;
  }

  return (
    <PermissionProvider>
      <SimpleShellLayout>
        <AdminLayoutContent>{children}</AdminLayoutContent>
      </SimpleShellLayout>
    </PermissionProvider>
  );
}
