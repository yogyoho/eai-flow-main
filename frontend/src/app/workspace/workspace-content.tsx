import { cookies } from "next/headers";
import { Toaster } from "sonner";

import { QueryClientProvider } from "@/components/query-client-provider";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { CommandPalette } from "@/components/workspace/command-palette";
// EAI-CUSTOM: 对齐上游 —— 设置弹窗统一挂在 workspace-content（app 级单实例，
// 内部 dynamic 懒加载），nav-menu/palette/deep-link 都只通过 store 触发。
import { SettingsDialogHost } from "@/components/workspace/settings";
import { WorkspaceSettingsDeepLink } from "@/components/workspace/workspace-settings-deep-link";
import { WorkspaceSidebar } from "@/components/workspace/workspace-sidebar";
// EAI-CUSTOM: nav-level permission gating for sidebar and settings
import { PermissionProvider } from "@/core/permissions";

function parseSidebarOpenCookie(
  value: string | undefined,
): boolean | undefined {
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

export async function WorkspaceContent({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const cookieStore = await cookies();
  const initialSidebarOpen = parseSidebarOpenCookie(
    cookieStore.get("sidebar_state")?.value,
  );

  return (
    <QueryClientProvider>
      <PermissionProvider>
        <SidebarProvider className="h-screen" defaultOpen={initialSidebarOpen}>
          <WorkspaceSidebar />
          <SidebarInset className="min-w-0">{children}</SidebarInset>
        </SidebarProvider>
        <CommandPalette />
        <SettingsDialogHost />
        <WorkspaceSettingsDeepLink />
        <Toaster position="bottom-right" richColors closeButton />
      </PermissionProvider>
    </QueryClientProvider>
  );
}
