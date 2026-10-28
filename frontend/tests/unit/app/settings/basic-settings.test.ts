import { expect, test } from "@rstest/core";

import { ragflowSsoHref } from "@/app/settings/basic-settings";

// Regression: ISSUE-001 — the settings-page RAGFlow entry linked the raw web UI
// (http://<host>:9381/), which lands on RAGFlow's own login page and locks out
// SSO-provisioned users (they have no usable password). Found by /qa on 2026-10-28.
// Report: .gstack/qa-reports/qa-report-ragflow-sso-2026-10-28.md

test("ragflow settings entry targets the backend SSO login endpoint", () => {
  const href = ragflowSsoHref();
  expect(href.endsWith("/api/extensions/auth/ragflow-sso/login")).toBe(true);
  // Never regress to the raw web port: that URL bypasses SSO entirely.
  expect(href.includes(":9381")).toBe(false);
});
