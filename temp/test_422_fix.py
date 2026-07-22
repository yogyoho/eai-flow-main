"""Quick verification that project creation accepts DB-driven report_type values."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:2026"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Login
    page.goto(f"{BASE_URL}/workspace")
    page.wait_for_timeout(2000)
    page.locator('input[type="email"]').fill("admin@eai-flow.com")
    page.locator('input[type="password"]').fill("Admin@2026")
    page.locator('button[type="submit"]').click()
    page.wait_for_timeout(3000)

    print(f"Logged in: {'晚上好' in page.content() or 'Administrator' in page.content()}")

    # Test: Create project with DB-driven report_type via API
    csrf = None
    for cookie in page.context.cookies():
        if cookie["name"] == "csrf_token":
            csrf = cookie["value"]
            break

    if not csrf:
        # Try reading from document.cookie
        csrf = page.evaluate("() => document.cookie.split('; ').find(c => c.startsWith('csrf_token='))?.split('=')[1] || ''")

    print(f"CSRF token: {csrf[:20] if csrf else 'NOT FOUND'}...")

    # Test with eia_report (DB value)
    result = page.evaluate("""async (csrf) => {
        const resp = await fetch('/api/extensions/project/projects', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf,
            },
            body: JSON.stringify({
                name: '422修复测试_' + Date.now(),
                report_type: 'eia_report',
            }),
        });
        return { status: resp.status, body: await resp.json() };
    }""", csrf)

    print(f"\nTest 1 - report_type='eia_report':")
    print(f"  Status: {result['status']}")
    if result['status'] == 201:
        print("  PASS: Project created successfully!")
    elif result['status'] == 422:
        print(f"  FAIL: 422 - {result['body']}")
    else:
        print(f"  INFO: {result['body']}")

    # Test with fire_protection_design (DB value)
    result2 = page.evaluate("""async (csrf) => {
        const resp = await fetch('/api/extensions/project/projects', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf,
            },
            body: JSON.stringify({
                name: '消防测试_' + Date.now(),
                report_type: 'fire_protection_design',
            }),
        });
        return { status: resp.status, body: await resp.json() };
    }""", csrf)

    print(f"\nTest 2 - report_type='fire_protection_design':")
    print(f"  Status: {result2['status']}")
    if result2['status'] == 201:
        print("  PASS: Project created successfully!")
    elif result2['status'] == 422:
        print(f"  FAIL: 422 - {result2['body']}")
    else:
        print(f"  INFO: {result2['body']}")

    browser.close()
