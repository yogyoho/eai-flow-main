"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  // EAI-CUSTOM: 不强制首页 dark。上游 forcedTheme={"/" ? "dark"} 是为上游暗色 landing 设计的;
  // EAI 的 landing-new 支持明暗双主题,须跟随 /settings 基本设置里用户选择的主题。
  // 2026-07-19 上游同步曾回退此改动导致首页强制 dark(与 light 设置不符),勿再回退。
  //
  // EAI-CUSTOM: console 报 "Encountered a script tag while rendering React component" 为已知
  // dev-only 噪音(bug-1091):next-themes 0.4.6 在 Provider 树内渲染防 FOUC 内联 <script>,
  // Next 16.2.6 打包的 react-dom 19.3.0-canary 新增此警告(宿主 react-dom 19.2.4 与生产构建
  // 均无)。主题功能正常,产品决策=忽略不修;勿为消除它改 ThemeProvider 或升级依赖。
  return (
    <NextThemesProvider {...props} forcedTheme={undefined}>
      {children}
    </NextThemesProvider>
  );
}
