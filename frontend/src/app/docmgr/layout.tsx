"use client";

import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";

import { PageLoadingOverlay } from "@/components/ui/page-loading-overlay";
import { AuthProvider, useAuth } from "@/extensions/hooks/useAuth";

function DocMgrAuthGuard({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (isLoading) return;
    if (!user) {
      const loginUrl = "/login?redirect=" + encodeURIComponent(pathname || "/docmgr");
      router.replace(loginUrl);
    }
  }, [user, isLoading, router, pathname]);

  if (isLoading) {
    return <PageLoadingOverlay text="加载中..." />;
  }

  if (!user) {
    return null;
  }

  return <>{children}</>;
}

export default function DocMgrShellLayout({ children }: { children: React.ReactNode }) {
  return (
    <DocMgrAuthGuard>{children}</DocMgrAuthGuard>
  );
}
