"use client";

import { usePathname } from "next/navigation";
import { ThemeProvider as NextThemesProvider } from "next-themes";

const LIGHT_THEME_PATHS = new Set(["/", "/login"]);

export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  const pathname = usePathname();
  return (
    <NextThemesProvider
      {...props}
      forcedTheme={LIGHT_THEME_PATHS.has(pathname) ? "light" : undefined}
    >
      {children}
    </NextThemesProvider>
  );
}
