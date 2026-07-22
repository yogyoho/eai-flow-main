"""Investigate why report type dropdown is not selectable."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:2026"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Capture console errors
    console_errors = []
    page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
    page.on("pageerror", lambda err: console_errors.append(f"[PAGE ERROR] {err}"))

    # Login
    print("=== Login ===")
    page.goto(f"{BASE_URL}/workspace")
    page.wait_for_timeout(2000)
    page.locator('input[type="email"]').fill("admin@eai-flow.com")
    page.locator('input[type="password"]').fill("Admin@2026")
    page.locator('button[type="submit"]').click()
    page.wait_for_timeout(3000)
    print(f"Logged in: {'晚上好' in page.content() or 'Administrator' in page.content()}")

    # Navigate to project creation wizard
    print("\n=== Navigate to /projects/new ===")
    page.goto(f"{BASE_URL}/projects/new")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)

    # Take screenshot
    page.screenshot(path="D:/eai/eai-flow-main/.wolf/debug-wizard-step1.png", full_page=True)
    print("Screenshot saved to .wolf/debug-wizard-step1.png")

    # Check page content
    content = page.content()
    print(f"\nPage has '新建项目': {'新建项目' in content}")
    print(f"Page has '报告类型': {'报告类型' in content}")
    print(f"Page has '请选择报告类型': {'请选择报告类型' in content}")

    # Try to find the select/dropdown element
    selects = page.locator('[role="combobox"], button[aria-haspopup="listbox"]')
    select_count = selects.count()
    print(f"\nCombobox/dropdown elements found: {select_count}")

    for i in range(select_count):
        el = selects.nth(i)
        text = el.text_content() or ""
        aria = el.get_attribute("aria-expanded")
        disabled = el.get_attribute("disabled")
        print(f"  [{i}] text='{text[:60]}' aria-expanded={aria} disabled={disabled}")

    # Try clicking the first dropdown to see if it opens
    if select_count > 0:
        print("\n=== Click first dropdown ===")
        selects.nth(0).click()
        page.wait_for_timeout(1000)
        # Check if listbox appeared
        listbox = page.locator('[role="listbox"], [role="option"]')
        lb_count = listbox.count()
        print(f"Listbox/option elements after click: {lb_count}")
        for i in range(min(lb_count, 10)):
            el = listbox.nth(i)
            print(f"  [{i}] text='{(el.text_content() or '')[:60]}'")

    # Check the API directly via fetch
    print("\n=== Test API directly ===")
    result = page.evaluate("""async () => {
        try {
            const resp = await fetch('/api/extensions/knowledge-factory/dict-items?category=report_type&limit=200');
            const data = await resp.json();
            return { status: resp.status, items: data.items?.length, sample: data.items?.slice(0,3) };
        } catch(e) {
            return { error: e.message };
        }
    }""")
    print(f"API response: {json.dumps(result, indent=2, ensure_ascii=False, default=str)}")

    # Also try the kf API
    result2 = page.evaluate("""async () => {
        try {
            const resp = await fetch('/api/extensions/kf/dict-items?category=report_type&limit=200');
            const data = await resp.json();
            return { status: resp.status, items: data.items?.length, sample: data.items?.slice(0,3) };
        } catch(e) {
            return { error: e.message };
        }
    }""")
    print(f"kf API response: {json.dumps(result2, indent=2, ensure_ascii=False, default=str)}")

    # Print console errors
    print(f"\n=== Console errors ({len(console_errors)}) ===")
    for e in console_errors[:20]:
        print(f"  {e[:200]}")

    browser.close()
