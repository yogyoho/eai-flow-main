"use client";

import { Users, Shield, Network, FileText, Loader2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";
import { useAuth } from "@/extensions/hooks/useAuth";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/admin/users", label: "用户管理", icon: Users },
  { href: "/admin/roles", label: "角色管理", icon: Shield },
  { href: "/admin/departments", label: "部门管理", icon: Network },
  { href: "/admin/templates", label: "流程管理", icon: FileText },
];

/** Check if the current user has admin privileges. */
function isAdmin(roleName?: string | null): boolean {
  return roleName === "Super Admin";
}

function AdminLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Top navigation bar */}
      <header className="bg-background border-b border-border h-16 flex items-center px-6 shrink-0">
        <span className="font-bold text-lg tracking-tight text-foreground mr-8">系统管理</span>
        <nav className="flex items-center gap-6 text-sm font-medium text-muted-foreground h-full">
          {navItems.map(({ href, label }) => {
            const isActive = pathname === href;
            return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center h-full transition-colors py-5 border-b-2",
                    isActive
                      ? "text-primary border-primary"
                      : "border-transparent hover:text-foreground"
                  )}
                >
                {label}
              </Link>
            );
          })}
        </nav>
      </header>

      {/* Main content area */}
      <div className="flex-1 overflow-hidden min-w-0 min-h-0">{children}</div>
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
        <div className="flex items-center justify-center h-full">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </SimpleShellLayout>
    );
  }

  if (!isAdmin(user?.role_name)) {
    return null;
  }

  return (
    <SimpleShellLayout>
      <AdminLayoutContent>{children}</AdminLayoutContent>
    </SimpleShellLayout>
  );
}
