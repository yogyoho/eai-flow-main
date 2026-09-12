/**
 * 画布主题适配——运行时读 globals.css 变量驱动 Sigma (EAI-CUSTOM, plan 2026-09-12 Task 2 Step 2.6).
 *
 * 禁止引入 Explorer 的 --ws-* 主题体系；明暗取值完全落本系统令牌。
 * 明暗判定按本系统现实适配：ThemeProvider 为 attribute="class"（next-themes 在
 * <html> 上置 .dark 类，enableSystem），故主通道 = classList.contains("dark")，
 * prefers-color-scheme 仅作水合前的回退通道（本仓库不用 data-theme 属性）。
 */

export interface CanvasTheme {
  bg: string;
  nodeText: string;
  labelBg: string;
  labelBorder: string;
  edge: string;
  sel: string;
}

function isDarkMode(): boolean {
  if (typeof document === "undefined") return false;
  const root = document.documentElement;
  if (root.classList.contains("dark")) return true;
  const hasExplicitLight =
    root.classList.length > 0 || root.hasAttribute("data-theme");
  if (hasExplicitLight && !root.classList.contains("dark")) return false;
  return (
    typeof matchMedia === "function" &&
    matchMedia("(prefers-color-scheme: dark)").matches
  );
}

export function canvasTheme(): CanvasTheme {
  const s = getComputedStyle(document.documentElement);
  const v = (name: string, fb: string) => s.getPropertyValue(name).trim() || fb;
  const dark = isDarkMode();
  return {
    bg: v("--background", dark ? "#0f0f0f" : "#ffffff"),
    nodeText: v("--foreground", dark ? "#eff2f2" : "#1a1b1b"),
    labelBg: v("--card", dark ? "#1a1b1b" : "#ffffff"),
    labelBorder: v("--border", dark ? "rgba(255,255,255,.1)" : "#e4e6e6"),
    edge: dark ? "rgba(255,255,255,.2)" : "rgba(0,0,0,.16)",
    sel: v("--primary", dark ? "#6a63e8" : "#5148d6"),
  };
}

/**
 * 订阅主题变化（.dark 类切换 / 系统明暗切换），返回取消订阅函数。
 * 供页面层在变更时刷新画布配色（plan Task 3 Step 3.5 消费）。
 */
export function onThemeChange(callback: () => void): () => void {
  if (
    typeof document === "undefined" ||
    typeof MutationObserver === "undefined"
  ) {
    return () => undefined; // no-op unsubscribe（SSR / 无 Observer 环境）
  }
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class", "data-theme"],
  });
  let media: MediaQueryList | null = null;
  const onMedia = () => callback();
  if (typeof matchMedia === "function") {
    media = matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", onMedia);
  }
  return () => {
    observer.disconnect();
    media?.removeEventListener("change", onMedia);
  };
}
