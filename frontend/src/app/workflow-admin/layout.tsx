"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";
// EAI-CUSTOM (F4): 以 /me 的 is_admin 判权，替代硬编码 role_name === "Super Admin"
import { PermissionProvider, usePermission } from "@/core/permissions";
import { useAuth } from "@/extensions/hooks/useAuth";

export default function WorkflowAdminLayout({ children }: { children: ReactNode }) {
  // EAI-CUSTOM (F4): PermissionProvider 置于判权门之上，使 WorkflowAdminGate 能消费 /me 的 is_admin
  // （同 admin/layout.tsx AdminGate 模式），改名但 is_system 的超管不会被误锁门外。
  return (
    <PermissionProvider>
      <WorkflowAdminGate>{children}</WorkflowAdminGate>
    </PermissionProvider>
  );
}

function WorkflowAdminGate({ children }: { children: ReactNode }) {
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

  return <SimpleShellLayout>{children}</SimpleShellLayout>;
}
