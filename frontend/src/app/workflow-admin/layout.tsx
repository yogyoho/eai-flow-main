"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";
import { useAuth } from "@/extensions/hooks/useAuth";

function isAdmin(roleName?: string | null): boolean {
  return roleName === "Super Admin";
}

export default function WorkflowAdminLayout({ children }: { children: ReactNode }) {
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

  return <SimpleShellLayout>{children}</SimpleShellLayout>;
}
