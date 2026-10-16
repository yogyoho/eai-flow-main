import { redirect } from "next/navigation";

import { GatewayOfflineFallback } from "@/components/workspace/gateway-offline-fallback";
import { WorkspaceLoginRedirect } from "@/components/workspace/workspace-login-redirect";
import { AuthProvider } from "@/core/auth/AuthProvider";
import { getServerSideUser } from "@/core/auth/server";
import { ACCOUNT_DISABLED_LOGIN_URL, assertNever } from "@/core/auth/types";
import { I18nProvider } from "@/core/i18n/context";
import { detectLocaleServer } from "@/core/i18n/server";

import { WorkspaceContent } from "./workspace-content";

export const dynamic = "force-dynamic";

export default async function WorkspaceLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await detectLocaleServer();
  const result = await getServerSideUser();

  let content: React.ReactNode;

  switch (result.tag) {
    case "authenticated":
      content = (
        <AuthProvider initialUser={result.user}>
          <WorkspaceContent>{children}</WorkspaceContent>
        </AuthProvider>
      );
      break;
    case "needs_setup":
      redirect("/setup");
    case "system_setup_required":
      redirect("/setup");
    case "unauthenticated":
      // Not redirect(): a layout cannot read the request URL, so the browser
      // carries the page it is on into `next`.
      content = <WorkspaceLoginRedirect />;
      break;
    case "account_disabled":
      // The login page renders the disabled-account reason from the error
      // param instead of a plain sign-in form the user cannot complete.
      redirect(ACCOUNT_DISABLED_LOGIN_URL);
    case "gateway_unavailable":
      // EAI-CUSTOM (bug-2235): the bare static HTML here had no client probe,
      // so once the gateway recovered the error page stuck until a manual hard
      // reload (a <Link> Retry is a soft nav — the mounted layout segment is
      // reused and the force-dynamic server layout never re-executes). Wrap in
      // the offline fallback: its banner probes /auth/me every 10s and
      // hard-reloads on recovery; the Retry control is a plain <a> for the
      // same reason — full page load re-runs this layout.
      content = (
        <GatewayOfflineFallback renderBanner>
          <div className="flex h-screen flex-col items-center justify-center gap-4">
            <p className="text-muted-foreground">
              Service temporarily unavailable.
            </p>
            <p className="text-muted-foreground text-xs">
              The backend may be restarting. Please wait a moment and try again.
            </p>
            <div className="flex gap-3">
              {/* Intentionally NOT <Link>: a soft nav reuses the mounted
                  layout segment and would keep showing this error page
                  (bug-2235). The plain <a> forces a full page load so the
                  force-dynamic server layout re-executes. */}
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
              <a
                href="/workspace"
                className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm"
              >
                Retry
              </a>
              <form action="/api/v1/auth/logout" method="post">
                <button
                  type="submit"
                  className="text-muted-foreground hover:bg-muted rounded-md border px-4 py-2 text-sm"
                >
                  Logout &amp; Reset
                </button>
              </form>
            </div>
          </div>
        </GatewayOfflineFallback>
      );
      break;
    case "config_error":
      throw new Error(result.message);
    default:
      assertNever(result);
  }

  return <I18nProvider initialLocale={locale}>{content}</I18nProvider>;
}
