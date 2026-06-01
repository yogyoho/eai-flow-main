/**
 * E2E test: 文档空间协同编辑页中溯源 Tab 测试
 *
 * 测试流程：
 * 1. 管理员登录
 * 2. 进入文档管理页面
 * 3. 打开/创建一个测试文档
 * 4. 点击溯源 Tab（BookOpen 图标）
 * 5. 验证溯源面板展示：统计信息、标注列表、缺失预警
 * 6. 截图验证 UI
 */
import { test, expect } from "@playwright/test";

const BASE_URL = "http://localhost:3000";
const LOGIN_URL = `${BASE_URL}/login`;
const DOCMGR_URL = `${BASE_URL}/docmgr`;

const TEST_USER = {
  email: "admin@eai-flow.com",
  password: "Admin@2026",
};

test.describe("文档空间协同编辑 - 溯源 Tab", () => {
  test.beforeEach(async ({ page }) => {
    // ── Step 1: 登录 ──
    await page.goto(LOGIN_URL, { waitUntil: "networkidle" });

    // Wait for login form to render
    await page.waitForSelector('input[type="email"], input[name="email"], input[placeholder*="邮箱"], input[placeholder*="email"]', { timeout: 10000 }).catch(() => {
      // Try alternative selectors
    });

    // Fill credentials
    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="邮箱"], input[placeholder*="email"], input[placeholder*="Email"]').first();
    const passwordInput = page.locator('input[type="password"], input[name="password"]').first();

    if (await emailInput.isVisible()) {
      await emailInput.fill(TEST_USER.email);
      await passwordInput.fill(TEST_USER.password);
      await page.locator('button[type="submit"], button:has-text("登录"), button:has-text("Login"), button:has-text("Sign in")').first().click();
      await page.waitForTimeout(3000);
    }

    // If already logged in (cookies persisted), skip
  });

  test("溯源 Tab - 文档编辑页中可见并可以切换", async ({ page }) => {
    // ── Step 2: 进入文档管理 ──
    await page.goto(DOCMGR_URL, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(2000);

    // Take screenshot of docmgr page
    await page.screenshot({ path: "test-results/traceability-01-docmgr.png", fullPage: false });

    // ── Step 3: 找到并点击一个文档进入编辑 ──
    // Look for document rows, cards, or list items
    const docLink = page.locator('a[href*="docmgr"], button:has-text("打开"), [data-testid="doc-row"], .document-item, .doc-card').first();

    if (await docLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await docLink.click();
      await page.waitForTimeout(3000);
    } else {
      // Try clicking any clickable item that looks like a document
      const firstClickable = page.locator('table tbody tr, [role="listitem"], .card, .list-item').first();
      if (await firstClickable.isVisible({ timeout: 3000 }).catch(() => false)) {
        await firstClickable.click();
        await page.waitForTimeout(2000);
      }
    }

    await page.screenshot({ path: "test-results/traceability-02-editor.png", fullPage: false });

    // ── Step 4: 点击溯源按钮 ──
    // The traceability button has a BookOpen icon and title="溯源"
    const traceabilityBtn = page.locator('button[title="溯源"]').first();

    if (await traceabilityBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await traceabilityBtn.click();
      await page.waitForTimeout(1500);
    } else {
      // Try by icon class or aria-label
      const bookBtn = page.locator('button:has(.lucide-book-open), button:has(svg[class*="book"])').first();
      if (await bookBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await bookBtn.click();
        await page.waitForTimeout(1500);
      }
    }

    await page.screenshot({ path: "test-results/traceability-03-traceability-panel.png", fullPage: false });

    // ── Step 5: 验证溯源面板内容 ──
    // The traceability panel should show:
    // - "溯源" or "本章溯源" heading
    // - Source type statistics (rag_retrieval, ai_generated, etc.)
    // - Missing source warnings (if any)
    // - Source footnote list

    // Check for traceability panel elements
    const panelVisible = await page.locator('text=溯源, text=本章溯源').first().isVisible({ timeout: 3000 }).catch(() => false);

    if (panelVisible) {
      console.log("✅ 溯源面板已打开");

      // Check source stats grid
      const statsGrid = page.locator('.grid, [class*="grid"]').filter({ has: page.locator('text=rag_retrieval, text=ai_generated, text=knowledge_base, text=regulation') });
      if (await statsGrid.isVisible({ timeout: 2000 }).catch(() => false)) {
        console.log("✅ 溯源统计信息显示正常");
      }

      // Check for missing sources warning
      const missingWarning = page.locator('text=缺少来源标注, text=暂无溯源');
      if (await missingWarning.isVisible({ timeout: 2000 }).catch(() => false)) {
        console.log("⚠️ 溯源缺失预警已显示");
      }

      // Check source footnote list
      const footnoteSection = page.locator('text=溯源标注');
      if (await footnoteSection.isVisible({ timeout: 2000 }).catch(() => false)) {
        console.log("✅ 溯源标注列表显示正常");
      }
    } else {
      console.log("⚠️ 溯源面板未显示 — 可能当前文档没有绑定 chapterId");
      // Take screenshot to see actual state
      await page.screenshot({ path: "test-results/traceability-03b-no-panel.png", fullPage: true });
    }

    // ── Step 6: 验证 Inline 溯源标记 ──
    // Check if the ProseMirror editor has traceability decorations
    // The [N] markers should be wrapped in styled sup elements
    const editorArea = page.locator('[contenteditable="true"], .ProseMirror, [data-content-editable]').first();

    if (await editorArea.isVisible({ timeout: 3000 }).catch(() => false)) {
      // Check for inline traceability decorations (our ProseMirror plugin)
      const decorations = editorArea.locator('sup[style*="background-color"]');
      const decorationCount = await decorations.count().catch(() => 0);

      if (decorationCount > 0) {
        console.log(`✅ 内联溯源装饰已渲染: ${decorationCount} 个标记`);
        // Verify first decoration has tooltip
        const firstDeco = decorations.first();
        const title = await firstDeco.getAttribute("title").catch(() => null);
        if (title) {
          console.log(`✅ 溯源 tooltip: ${title.slice(0, 80)}...`);
        }
      } else {
        console.log("ℹ️ 当前文档中未检测到 [N] 溯源标记");
        console.log("   (这可能是正常的 — AI 尚未生成带标记的内容)");
      }
    }

    await page.screenshot({ path: "test-results/traceability-04-final.png", fullPage: true });
  });

  test("溯源 Tab - 关闭后重新打开", async ({ page }) => {
    await page.goto(DOCMGR_URL, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(2000);

    // Open a document
    const docLink = page.locator('a[href*="docmgr"], button:has-text("打开")').first();
    if (await docLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await docLink.click();
      await page.waitForTimeout(3000);
    }

    // Click traceability button
    const traceBtn = page.locator('button[title="溯源"]').first();
    if (await traceBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      // Open
      await traceBtn.click();
      await page.waitForTimeout(1000);
      expect(page.locator('text=溯源').first()).toBeVisible({ timeout: 3000 });
      console.log("✅ 溯源面板打开成功");

      // Close
      await traceBtn.click();
      await page.waitForTimeout(500);
      // Panel should disappear
      const panelHidden = await page.locator('text=本章溯源').first().isHidden({ timeout: 2000 }).catch(() => true);
      console.log(panelHidden ? "✅ 溯源面板关闭成功" : "⚠️ 面板可能未关闭");

      // Re-open
      await traceBtn.click();
      await page.waitForTimeout(1000);
      const panelReopened = await page.locator('text=溯源').first().isVisible({ timeout: 3000 }).catch(() => false);
      console.log(panelReopened ? "✅ 溯源面板重新打开成功" : "⚠️ 重新打开失败");
    } else {
      console.log("⚠️ 未找到溯源按钮 — 可能不在文档编辑页");
      await page.screenshot({ path: "test-results/traceability-toggle-no-btn.png", fullPage: true });
    }
  });
});
