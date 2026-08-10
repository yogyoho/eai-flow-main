"use client";

import { usePathname } from "next/navigation";
import { ThemeProvider as NextThemesProvider } from "next-themes";

export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  const pathname = usePathname();
  // next-themes 会在组件树内渲染内联 <script>(防 FOUC),触发 React 19.3 dev-only 警告
  // "Encountered a script tag while rendering React component"。生产构建无此警告,主题功能正常,
  // 上游(issue #387)未修复且包已弃维护——已知问题,忽略。Next 16.2.6 起的 canary react-dom 引入。
  return (
    <NextThemesProvider
      {...props}
      forcedTheme={undefined}
    >
      {children}
    </NextThemesProvider>
  );
}
