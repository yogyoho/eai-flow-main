import "@/styles/globals.css";
import "katex/dist/katex.min.css";

import { type Metadata } from "next";

import { ThemeProvider } from "@/components/theme-provider";
import { I18nProvider } from "@/core/i18n/context";
import { detectLocaleServer } from "@/core/i18n/server";
import { AuthProvider } from "@/extensions/hooks/useAuth";
import { LicenseShell } from "@/extensions/license/LicenseShell";

export const metadata: Metadata = {
  title: "EAIFlow",
  description: "A LangChain-based framework for building super agents.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await detectLocaleServer();
  return (
    <html lang={locale} suppressContentEditableWarning suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" enableSystem disableTransitionOnChange>
          <I18nProvider initialLocale={locale}>
            <AuthProvider>
              <LicenseShell>{children}</LicenseShell>
            </AuthProvider>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
