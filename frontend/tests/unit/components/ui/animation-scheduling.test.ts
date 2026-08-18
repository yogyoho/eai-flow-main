import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "@rstest/core";

const frontendRoot = join(import.meta.dirname, "../../../..");

// EAI-CUSTOM: 永久不适配（用户定案 2026-08-19）——本系统落地页已由
// landing-new（src/components/landing-new/）替代上游 landing，测试断言的
// src/components/landing/hero.tsx 等文件不再是线上渲染路径，以本地代码为
// 准，不做差分移植。保留 skip 仅作上游对照标记。
describe.skip("decorative animation scheduling", () => {
  it("suspends the Galaxy render loop when its container is inactive", () => {
    const source = readFileSync(
      join(frontendRoot, "src/components/landing/hero.tsx"),
      "utf8",
    );

    expect(source).toContain("useRenderActivity");
    expect(source).toContain("renderGalaxy && (");
    expect(source).toContain(
      'dynamic(() => import("@/components/ui/galaxy"), { ssr: false })',
    );
  });

  it("scopes and coalesces Magic Bento spotlight pointer work", () => {
    const source = readFileSync(
      join(
        frontendRoot,
        "src/components/landing/sections/whats-new-section.tsx",
      ),
      "utf8",
    );

    expect(source).toContain("useRenderActivity");
    expect(source).toContain("enableSpotlight={false}");
    expect(source).toContain('import("@/components/ui/magic-bento")');
    expect(source).toContain("ssr: false");
    expect(source).toContain(
      "useRenderActivity(bentoContainerRef, false, false)",
    );
    expect(source).toContain("disableAnimations={reducedMotion}");
    expect(source).toContain('container.addEventListener("pointermove"');
    expect(source).toContain("pendingPointerFrame");
  });

  it("does not load the skills animation before its section is visible", () => {
    const source = readFileSync(
      join(frontendRoot, "src/components/landing/sections/skills-section.tsx"),
      "utf8",
    );

    expect(source).toContain('import("../progressive-skills-animation")');
    expect(source).toContain("ssr: false");
    expect(source).toContain("useRenderActivity(animationRef, false)");
    expect(source).toContain(
      "renderAnimation && <ProgressiveSkillsAnimation />",
    );
  });
});
