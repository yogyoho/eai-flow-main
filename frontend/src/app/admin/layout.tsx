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
  // EAI-CUSTOM: A3 PermissionProvider 置于判权门之上，使 AdminGate 能消费 /me 的 is_admin
  // 作为唯一判权依据（不再依赖角色显示名），避免改名但 is_system 的超管被误锁门外。
  return (
    <PermissionProvider>
      <AdminGate>{children}</AdminGate>
    </PermissionProvider>
  );
}

function AdminGate({ children }: { children: ReactNode }) {
  const { isLoading: userLoading } = useAuth();
  const { is_admin, isLoading: permLoading } = usePermission();
  const router = useRouter();
  const loading = userLoading || permLoading;
  const authorized = is_admin;

  useEffect(() => {
    if (!loading && !authorized) {
      router.replace("/dashboard");
    }
  }, [loading, authorized, router]);

  if (loading) {
    return (
      <SimpleShellLayout>
        <div className="flex h-full items-center justify-center">
          <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
        </div>
      </SimpleShellLayout>
    );
  }

  if (!authorized) {
    return null;
  }

  return (
    <SimpleShellLayout>
      <AdminLayoutContent>{children}</AdminLayoutContent>
    </SimpleShellLayout>
  );
}
