"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  // EAI-CUSTOM: 不强制首页 dark。上游 forcedTheme={"/" ? "dark"} 是为上游暗色 landing 设计的;
  // EAI 的 landing-new 支持明暗双主题,须跟随 /settings 基本设置里用户选择的主题。
  // 2026-07-19 上游同步曾回退此改动导致首页强制 dark(与 light 设置不符),勿再回退。
  return (
    <NextThemesProvider {...props} forcedTheme={undefined}>
      {children}
    </NextThemesProvider>
  );
}
