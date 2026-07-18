import { redirect } from "next/navigation";
import { type ReactNode } from "react";

import { GatewayOfflineFallback } from "@/components/workspace/gateway-offline-fallback";
import { getServerSideUser } from "@/core/auth/server";
import { assertNever } from "@/core/auth/types";

export const dynamic = "force-dynamic";

/**
 * Auth route group layout — server-side guard for /login, /setup, /auth/callback.
 * AuthProvider is provided by the root layout — this layout only handles
 * redirects and gateway-offline fallback.
 */
export default async function AuthLayout({
  children,
}: {
  children: ReactNode;
}) {
  const result = await getServerSideUser();

  switch (result.tag) {
    case "authenticated":
      redirect("/workspace");
    case "needs_setup":
    case "system_setup_required":
    case "unauthenticated":
      return <>{children}</>;
    case "gateway_unavailable":
      return (
        <GatewayOfflineFallback renderBanner>
          <div className="flex h-screen flex-col items-center justify-center gap-4">
            <p className="text-muted-foreground">
              Service temporarily unavailable.
            </p>
          </div>
        </GatewayOfflineFallback>
      );
    case "config_error":
      throw new Error(result.message);
    default:
      assertNever(result);
  }
}
