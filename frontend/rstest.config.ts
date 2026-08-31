import { resolve } from "path";

import { pluginReact } from "@rsbuild/plugin-react";
import { defineConfig } from "@rstest/core";

// Build wiring is identical across projects; only the environment and which
// files each one claims differ.
const shared = {
  plugins: [pluginReact()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  output: {
    // EAI-CUSTOM: Streamdown imports KaTeX CSS as a side effect, and the @blocknote/*
    // packages import their own dist/style.css. Bundle these packages so
    // Rsbuild processes the CSS imports instead of Node trying to load them.
    bundleDependencies: [
      "streamdown",
      "katex",
      "@blocknote/core",
      "@blocknote/react",
      "@blocknote/shadcn",
      "@blocknote/xl-ai",
      "@defensestation/blocknote-math",
      "highlight.js",
    ],
  },
};

export default defineConfig({
  projects: [
    {
      ...shared,
      name: "node",
      include: ["tests/unit/**/*.test.ts", "tests/unit/**/*.test.tsx"],
      // A DOM environment costs roughly 3x the runtime of this suite, so the
      // pure-logic tests that make up nearly all of it stay on node and only
      // `*.dom.test.*` pays for a document.
      exclude: { patterns: ["**/*.dom.test.*"], override: false },
    },
    {
      ...shared,
      name: "dom",
      testEnvironment: "happy-dom",
      include: ["tests/unit/**/*.dom.test.ts", "tests/unit/**/*.dom.test.tsx"],
    },
  ],
});
