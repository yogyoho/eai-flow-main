import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

// ---------------------------------------------------------------------------
// Mock helpers for extensions API
// ---------------------------------------------------------------------------

/** Mock the extensions API endpoints used by the knowledge factory page. */
function mockExtensionsAPI(page: Page) {
  // Mock auth/me — critical: must be set before page navigation
  void page.route("**/api/extensions/auth/me", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "00000000-0000-0000-0000-000000000001",
        username: "admin",
        email: "admin@example.com",
        full_name: "Admin User",
        role_name: "admin",
        role_code: "admin",
        permissions: ["kb:read", "kb:create", "kb:upload", "kb:update", "kb:delete"],
      }),
    });
  });

  // Mock knowledge-bases list — returns an empty list
  void page.route("**/api/extensions/knowledge-bases*", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ knowledge_bases: [], total: 0 }),
    });
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Knowledge Factory page", () => {
  test.beforeEach(async ({ page }) => {
    // Mock token + user in localStorage BEFORE navigation so useAuth succeeds.
    // This prevents the redirect to /login that would otherwise break tests.
    await page.addInitScript(() => {
      window.localStorage.setItem("access_token", "mock-e2e-token");
      // Store a fake user so the sidebar renders without calling auth/me
      window.localStorage.setItem("_mock_user", JSON.stringify({
        id: "00000000-0000-0000-0000-000000000001",
        username: "admin",
        email: "admin@example.com",
        full_name: "Admin User",
        role_name: "admin",
        role_code: "admin",
        permissions: ["kb:read", "kb:create", "kb:upload", "kb:update", "kb:delete"],
      }));
    });

    // Intercept auth/me — return mock user directly
    void page.route("**/api/extensions/auth/me", (route) => {
      void route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "00000000-0000-0000-0000-000000000001",
          username: "admin",
          email: "admin@example.com",
          full_name: "Admin User",
          role_name: "admin",
          role_code: "admin",
          permissions: ["kb:read", "kb:create", "kb:upload", "kb:update", "kb:delete"],
        }),
      });
    });

    // Mock knowledge-bases list
    void page.route("**/api/extensions/knowledge-bases*", (route) => {
      void route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ knowledge_bases: [], total: 0 }),
      });
    });

    mockLangGraphAPI(page);
  });

  test("renders the page header and all 8 navigation tabs", async ({ page }) => {
    await page.goto("/knowledge-factory");

    // Page title / header
    await expect(page.locator("span", { hasText: "知识工厂" }).first()).toBeVisible({ timeout: 10_000 });

    // All 8 nav tabs
    const tabs = [
      "样例管理",
      "模板抽取",
      "模板编辑",
      "法规标准",
      "合规规则",
      "版本管理",
      "质量评估",
      "网页爬取",
    ];
    for (const label of tabs) {
      await expect(page.locator("nav", { has: page.locator(`text="${label}"`) })).toBeVisible({ timeout: 5_000 });
    }
  });

  test("SampleReports tab loads without 500 error and shows empty state", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto("/knowledge-factory?tab=reports");

    // Heading visible
    await expect(page.locator("h2", { hasText: "样例报告库" })).toBeVisible({ timeout: 10_000 });

    // Upload button visible
    await expect(page.getByRole("button", { name: /上传新报告/i })).toBeVisible();

    // Refresh button visible
    await expect(page.getByRole("button", { name: /刷新/i })).toBeVisible();

    // Search textbox visible
    await expect(page.getByRole("textbox", { name: /搜索报告名称/i })).toBeVisible();

    // Combobox controls visible (AdminSelect with Radix Select renders as combobox)
    await expect(page.locator("[role=combobox]").first()).toBeVisible();
    await expect(page.locator("[role=combobox]").nth(1)).toBeVisible();

    // No 500 error logged
    const kb500Errors = consoleErrors.filter(
      (t) => t.includes("500") || t.includes("Internal Server Error")
    );
    expect(kb500Errors).toHaveLength(0);
  });

  test("search box accepts input without crashing", async ({ page }) => {
    await page.goto("/knowledge-factory?tab=reports");
    await expect(page.locator("h2", { hasText: "样例报告库" })).toBeVisible({ timeout: 10_000 });

    const searchBox = page.getByRole("textbox", { name: /搜索报告名称/i });
    await expect(searchBox).toBeVisible();
    await searchBox.fill("测试关键词");
    await page.waitForTimeout(300);
  });

  test("upload button is visible and clickable", async ({ page }) => {
    await page.goto("/knowledge-factory?tab=reports");
    await expect(page.locator("h2", { hasText: "样例报告库" })).toBeVisible({ timeout: 10_000 });

    const uploadBtn = page.getByRole("button", { name: /上传新报告/i });
    await expect(uploadBtn).toBeVisible();
    await uploadBtn.click();
    await page.waitForTimeout(300);
  });
});
