"""Verify workflow template publish status and visibility in project creation."""
import asyncio, sys, io
from playwright.async_api import async_playwright

# Fix Windows GBK console issue
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = "http://localhost:2026"
OUTPUT = "verify_template_output.txt"

async def main():
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1522, "height": 800})

        # 1. Login
        results.append("=== 1. Login ===")
        await page.goto(f"{BASE}/workspace")
        await page.wait_for_load_state("networkidle")
        await page.fill('input[type="email"]', "admin@eai-flow.com")
        await page.fill('input[type="password"]', "Admin@2026")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard**", timeout=10000)
        results.append("[OK] Login successful")

        # 2. Check template list in admin
        results.append("\n=== 2. Admin Templates List ===")
        await page.goto(f"{BASE}/admin/templates")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1500)
        # Get all heading text
        all_h = await page.locator('h1,h2,h3,h4').all_text_contents()
        results.append(f"Headings: {all_h}")
        # Buttons
        btns = await page.locator('button').all_text_contents()
        results.append(f"Buttons: {btns}")
        await page.screenshot(path="verify_template_list.png")

        # 3. Open template detail page
        results.append("\n=== 3. Template Detail Page ===")
        await page.goto(f"{BASE}/admin/templates/9771dd40-4765-47ac-997f-f8a9d7cefad0")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)

        page_text = await page.locator('main, body').first.inner_text()
        results.append(f"Page text:\n{page_text[:3000]}")

        inputs = await page.locator('input:not([type="hidden"])').all()
        for inp in inputs:
            name = await inp.get_attribute('name')
            val = await inp.input_value()
            ph = await inp.get_attribute('placeholder')
            results.append(f"  Input: name={name}, value={val}, placeholder={ph}")

        buttons = await page.locator('button').all()
        for btn in buttons:
            text = await btn.inner_text()
            results.append(f"  Button: {text.strip()[:60]}")

        await page.screenshot(path="verify_template_detail.png")

        # 4. Check project creation flow
        results.append("\n=== 4. Project Creation Flow ===")
        await page.goto(f"{BASE}/dashboard")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        create_btn = page.locator('a:has-text("create"), button:has-text("新建")').first
        if await create_btn.count() > 0:
            await create_btn.click()
            await page.wait_for_timeout(2000)

        await page.screenshot(path="verify_project_create.png")
        body_text = await page.locator('body').inner_text()
        results.append(f"Body text after create click:\n{body_text[:3000]}")

        # 5. Directly check the API for templates
        results.append("\n=== 5. API Check ===")
        # Try to get the template from state
        state = await page.context.storage_state()
        results.append(f"Cookies count: {len(state.get('cookies', []))}")

        await browser.close()

    # Write results
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(results))
    print(f"Results written to {OUTPUT}")

asyncio.run(main())
