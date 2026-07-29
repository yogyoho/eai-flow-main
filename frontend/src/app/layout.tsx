import "@/styles/globals.css";
import "katex/dist/katex.min.css";

import { type Metadata } from "next";

import { ThemeProvider } from "@/components/theme-provider";
import { I18nProvider } from "@/core/i18n/context";
import { detectLocaleServer } from "@/core/i18n/server";
import { AuthProvider as CoreAuthProvider } from "@/core/auth/AuthProvider";
import { getServerSideUser } from "@/core/auth/server";
import { assertNever, type User } from "@/core/auth/types";
import { AuthProvider } from "@/extensions/hooks/useAuth";
import { LicenseShell } from "@/extensions/license/LicenseShell";
import { ChunkErrorHandler } from "@/components/chunk-error-handler";
// EAI-CUSTOM: 按客户品牌化（构建期注入，见 brand.ts）
import { BRAND_NAME } from "@/brand";

export const metadata: Metadata = {
  title: BRAND_NAME,
  description: "A LangChain-based framework for building super agents.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await detectLocaleServer();
  const authResult = await getServerSideUser();

  let initialUser: User | null = null;
  switch (authResult.tag) {
    case "authenticated":
    case "needs_setup":
      initialUser = authResult.user;
      break;
    case "system_setup_required":
    case "unauthenticated":
    case "gateway_unavailable":
      initialUser = null;
      break;
    case "config_error":
      throw new Error(authResult.message);
    default:
      assertNever(authResult);
  }

  return (
    <html lang={locale} suppressContentEditableWarning suppressHydrationWarning>
      <body>
        <ChunkErrorHandler />
        <ThemeProvider attribute="class" enableSystem disableTransitionOnChange>
          <I18nProvider initialLocale={locale}>
            <AuthProvider>
              <CoreAuthProvider initialUser={initialUser}>
                <LicenseShell>{children}</LicenseShell>
              </CoreAuthProvider>
            </AuthProvider>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
