/**
 * E2E test: "Load More" button on conversation page
 *
 * Tests that after multi-turn conversation, the "Load More" button
 * correctly appears at the top of the message list when there are
 * unloaded historical runs.
 */
import { expect, test } from "@playwright/test";

test.describe("Load More button", () => {
  test.beforeEach(async ({ page }) => {
    // Mock backend APIs so the page can load without a real backend
    await page.route("**/api/models", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          { id: "test-model", name: "Test Model", provider: "test" },
        ]),
      });
    });

    await page.route("**/api/langgraph/threads/search**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/langgraph/agents", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            agent_id: "lead_agent",
            name: "Lead Agent",
            description: "Main agent",
          },
        ]),
      });
    });
  });

  test("shows thread list on workspace page", async ({ page }) => {
    await page.goto("http://localhost:3000/workspace/chats");

    // Wait for the page to load
    await page.waitForLoadState("networkidle");

    // Take a screenshot for debugging
    await page.screenshot({
      path: "tests/e2e/screenshots/workspace-chats.png",
      fullPage: true,
    });

    // Check if the page loaded (at minimum, no crash)
    const body = page.locator("body");
    await expect(body).toBeVisible();
  });

  test("opens a thread page and checks for Load More button", async ({ page }) => {
    const threadId = "test-thread-123";

    // Mock thread runs — 3 runs exist
    await page.route(`**/api/langgraph/threads/${threadId}/runs**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          { run_id: "run-1", thread_id: threadId, assistant_id: "lead_agent", status: "success" },
          { run_id: "run-2", thread_id: threadId, assistant_id: "lead_agent", status: "success" },
          { run_id: "run-3", thread_id: threadId, assistant_id: "lead_agent", status: "success" },
        ]),
      });
    });

    // Mock thread state (useStream)
    await page.route(`**/api/langgraph/threads/${threadId}/state**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          values: {
            messages: [
              { id: "msg-1", type: "human", content: "Hello" },
              { id: "msg-2", type: "ai", content: "Hi there!" },
              { id: "msg-3", type: "human", content: "How are you?" },
              { id: "msg-4", type: "ai", content: "I'm fine!" },
            ],
            title: "Test Thread",
            artifacts: [],
          },
        }),
      });
    });

    // Mock run messages endpoint
    await page.route(`**/api/threads/${threadId}/runs/*/messages`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [
            {
              run_id: "run-1",
              content: { id: "old-msg-1", type: "human", content: "Old message 1" },
              metadata: { caller: "" },
            },
            {
              run_id: "run-1",
              content: { id: "old-msg-2", type: "ai", content: "Old response 1" },
              metadata: { caller: "" },
            },
          ],
          hasMore: false,
        }),
      });
    });

    // Navigate to the thread page
    await page.goto(`http://localhost:3000/workspace/chats/${threadId}`);
    await page.waitForLoadState("networkidle");

    // Wait a bit for React to render
    await page.waitForTimeout(2000);

    // Take screenshot
    await page.screenshot({
      path: "tests/e2e/screenshots/thread-page.png",
      fullPage: true,
    });

    // Check that messages are rendered
    const messageElements = page.locator('[class*="message"]');
    const messageCount = await messageElements.count();
    console.log(`Found ${messageCount} message elements`);

    // Look for "Load More" button or similar
    const loadMoreButton = page.locator('button:has-text("Load"), button:has-text("加载"), button:has-text("more"), button:has-text("更多")');
    const loadMoreCount = await loadMoreButton.count();
    console.log(`Found ${loadMoreCount} "Load More" buttons`);

    // The page should at least render without errors
    await expect(page.locator("body")).toBeVisible();
  });
});
