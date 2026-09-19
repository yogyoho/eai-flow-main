import { cookies } from "next/headers";
import { Toaster } from "sonner";

import { QueryClientProvider } from "@/components/query-client-provider";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { CommandPalette } from "@/components/workspace/command-palette";
import { GatewayOfflineBanner } from "@/components/workspace/gateway-offline-banner";
import { ModelLoadErrorBanner } from "@/components/workspace/model-load-error-banner";
import { SettingsDialogHost } from "@/components/workspace/settings";
import { WorkspaceSettingsDeepLink } from "@/components/workspace/workspace-settings-deep-link";
import { WorkspaceSidebar } from "@/components/workspace/workspace-sidebar";
// EAI-CUSTOM: nav-level permission gating for sidebar and settings
import { PermissionProvider } from "@/core/permissions";
import { UserPreferencesBoundary } from "@/core/settings/user-preferences-boundary";

function parseSidebarOpenCookie(
  value: string | undefined,
): boolean | undefined {
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

export async function WorkspaceContent({
  children,
  gatewayUnavailable = false,
}: Readonly<{
  children: React.ReactNode;
  gatewayUnavailable?: boolean;
}>) {
  const cookieStore = await cookies();
  const initialSidebarOpen = parseSidebarOpenCookie(
    cookieStore.get("sidebar_state")?.value,
  );

  return (
    <QueryClientProvider>
      {/* Upstream #5397: scopes the settings store per account owner and gates
          the subtree during account switch. PermissionProvider nests inside so
          per-user permissions refetch when the owner changes. */}
      <UserPreferencesBoundary>
        {/* EAI-CUSTOM: PermissionProvider wraps the workspace for nav-level gating */}
        <PermissionProvider>
          <SidebarProvider
            className="h-screen"
            defaultOpen={initialSidebarOpen}
          >
            <WorkspaceSidebar />
            <SidebarInset className="min-w-0">
              <GatewayOfflineBanner gatewayUnavailable={gatewayUnavailable} />
              <ModelLoadErrorBanner gatewayUnavailable={gatewayUnavailable} />
              {children}
            </SidebarInset>
          </SidebarProvider>
          <CommandPalette />
          <SettingsDialogHost />
          <WorkspaceSettingsDeepLink />
          {/* EAI-CUSTOM: bottom-right rich toaster with close button (upstream: top-center) */}
          <Toaster position="bottom-right" richColors closeButton />
        </PermissionProvider>
      </UserPreferencesBoundary>
    </QueryClientProvider>
  );
}
