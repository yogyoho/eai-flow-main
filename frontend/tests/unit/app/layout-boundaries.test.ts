import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "@rstest/core";

const FRONTEND_ROOT = path.resolve(__dirname, "../../..");

function source(relativePath: string) {
  return readFileSync(path.join(FRONTEND_ROOT, relativePath), "utf8");
}

// EAI-CUSTOM: 决策 = 不采纳（2026-08-19 分析定案）。上游 root layout 最小化
// (仅 ThemeProvider) 的前提是无全局认证、i18n 只覆盖 docs/blog——对 EAI 均不
// 成立：EAI 是多用户企业部署，root layout 必须全局包裹 cookie-JWT 认证
// (CoreAuthProvider)、全应用 i18n(detectLocaleServer+I18nProvider，见
// full-upstream-gap-triage "不可同步核心")与 LicenseShell 许可门。
// katex 全局 CSS(~9KB gz)是有意取舍：admin/docmgr/knowledge 等扩展页也渲染
// LaTeX，leaf 化需逐页核对、回归面大而收益小。blog/docs/showcase 的 leaf
// import 已并存(双导入幂等)。除非未来重构 EAI 认证/i18n 架构，否则保持 skip。
describe.skip("layout performance boundaries", () => {
  it("keeps request locale and rich-content styles out of the root layout", () => {
    const rootLayout = source("src/app/layout.tsx");

    expect(rootLayout).not.toContain("detectLocaleServer");
    expect(rootLayout).not.toContain("I18nProvider");
    expect(rootLayout).not.toContain("katex/dist/katex.min.css");
    expect(rootLayout).not.toContain("streamdown/styles.css");
    expect(rootLayout).toContain("DEFAULT_LOCALE");
  });

  it("assigns rich-content styles to routes that render them", () => {
    expect(source("src/app/workspace/layout.tsx")).toContain(
      'import "streamdown/styles.css"',
    );
    expect(source("src/app/[lang]/docs/layout.tsx")).toContain(
      'import "katex/dist/katex.min.css"',
    );
    expect(source("src/app/blog/layout.tsx")).toContain(
      'import "katex/dist/katex.min.css"',
    );
  });

  it("passes only serializable locale state through server layouts", () => {
    for (const layout of [
      source("src/app/(auth)/layout.tsx"),
      source("src/app/workspace/layout.tsx"),
    ]) {
      expect(layout).toContain("detectLocaleServer");
      expect(layout).not.toContain("initialTranslations");
      expect(layout).not.toContain("getI18n");
    }
  });
});
