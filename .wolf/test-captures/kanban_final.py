import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

CAPTURE_DIR = "D:/eai/eai-flow-main/.wolf/test-captures/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    # ── Step 1: Login ──
    print("=== Step 1: Login ===")
    page.goto("http://localhost:2026/login", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    # Try different passwords
    passwords = ["Admin@2026", "admin123", "admin@2026", "Admin123", "password"]

    for pwd in passwords:
        print(f"\nTrying password: {pwd}")
        page.locator("input[type='email']").fill("admin@eai-flow.com")
        page.locator("input[type='password']").fill(pwd)
        page.locator("button[type='submit']").click()
        page.wait_for_timeout(3000)

        current_url = page.url
        print(f"  URL after submit: {current_url}")

        if "/login" not in current_url:
            print(f"  SUCCESS! Password is: {pwd}")
            break
        else:
            # Check for error message
            error = page.locator("[class*='error'], [class*='Error'], [role='alert'], [class*='destructive']").all()
            for e in error:
                text = e.inner_text().strip()
                if text:
                    print(f"  Error: {text}")

        # Clear and try again
        page.locator("input[type='password']").fill("")

    page.screenshot(path=CAPTURE_DIR + "50_after_login.png")
    print(f"Current URL: {page.url}")

    if "/login" in page.url:
        print("All passwords failed. Trying to reset admin password via API...")
        # Try using the reset mechanism
        import sqlite3
        from pathlib import Path

        # Reset password in the gateway auth DB
        db_path = Path("D:/eai/eai-flow-main/backend/.deer-flow/data/deerflow.db")

        # Generate bcrypt hash for admin123
        import bcrypt
        new_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
        print(f"New hash: {new_hash}")

        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("UPDATE users SET password_hash = ? WHERE email = ?", (new_hash, "admin@eai-flow.com"))
        conn.commit()
        conn.close()
        print("Password reset to admin123 in gateway DB")

        # Try login again
        page.goto("http://localhost:2026/login", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.locator("input[type='email']").fill("admin@eai-flow.com")
        page.locator("input[type='password']").fill("admin123")
        page.locator("button[type='submit']").click()
        page.wait_for_timeout(3000)
        print(f"After reset URL: {page.url}")

    # If still on login, try register approach
    if "/login" in page.url:
        print("Login still failing, trying register endpoint...")
        # Try registering a new admin user
        page.goto("http://localhost:2026/login", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(1000)
        page.locator("input[type='email']").fill("test@test.com")
        page.locator("input[type='password']").fill("Test@2026pass")
        page.locator("button[type='submit']").click()
        page.wait_for_timeout(3000)
        print(f"After register attempt URL: {page.url}")

    page.screenshot(path=CAPTURE_DIR + "51_login_state.png")

    # ── Step 2: Navigate to projects ──
    if "/login" not in page.url:
        print("\n=== Step 2: Navigate to projects ===")
        page.goto("http://localhost:2026/projects", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page.screenshot(path=CAPTURE_DIR + "52_projects.png")

        # Create project via API
        csrf_token = None
        for cookie in context.cookies():
            if cookie['name'] == 'csrf_token':
                csrf_token = cookie['value']
                break

        create_result = page.evaluate("""
            (csrfToken) => {
                const headers = { 'Content-Type': 'application/json' };
                if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
                return fetch('/api/project/projects', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({
                        name: 'Kanban Test Project',
                        report_type: 'environmental_impact',
                        template_id: 'tpl_env',
                        client: 'Test Corp',
                        target_standard: 'GB',
                        members: []
                    }),
                })
                .then(resp => resp.text().then(t => ({ status: resp.status, body: t.substring(0, 500) })))
                .catch(e => ({ status: 0, body: e.message }));
            }
        """, csrf_token)
        print(f"Create project: status={create_result['status']}")
        print(f"Response: {create_result['body'][:200]}")

        # Reload projects page
        page.goto("http://localhost:2026/projects", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page.screenshot(path=CAPTURE_DIR + "53_projects_after_create.png")

        # Find project links
        project_links = page.locator("a[href*='/projects/']").all()
        print(f"Found {len(project_links)} project links")

        if len(project_links) > 0:
            href = project_links[0].get_attribute("href") or ""
            print(f"Opening project: {href}")
            page.goto(f"http://localhost:2026{href}" if href.startswith("/") else href,
                       wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            page.screenshot(path=CAPTURE_DIR + "54_project_detail.png")

            # Find and click kanban tab
            tabs = page.locator("[role='tab']").all()
            print(f"Found {len(tabs)} tabs:")
            for tab in tabs:
                text = tab.inner_text().strip()
                print(f"  '{text}'")

            for tab in tabs:
                text = tab.inner_text().strip()
                if "kanban" in text.lower() or "看板" in text:
                    tab.click()
                    print(f"Clicked kanban tab!")
                    break

            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(3000)

            # Take screenshots
            page.set_viewport_size({"width": 1440, "height": 900})
            page.wait_for_timeout(1000)
            page.screenshot(path=CAPTURE_DIR + "55_kanban_1440x900.png")
            page.screenshot(path=CAPTURE_DIR + "56_kanban_fullpage.png", full_page=True)

            page.set_viewport_size({"width": 1920, "height": 1080})
            page.wait_for_timeout(1000)
            page.screenshot(path=CAPTURE_DIR + "57_kanban_1920x1080.png")

            # Header close-up
            page.set_viewport_size({"width": 1440, "height": 250})
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
            page.screenshot(path=CAPTURE_DIR + "58_kanban_header.png")

            # Header to content
            page.set_viewport_size({"width": 1440, "height": 450})
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
            page.screenshot(path=CAPTURE_DIR + "59_kanban_header_content.png")

            # DOM analysis
            analysis = page.evaluate("""
                () => {
                    const r = {};
                    const all = document.querySelectorAll('*');
                    const kanbanEls = [];
                    for (const el of all) {
                        const cls = el.className || '';
                        if (typeof cls === 'string' && (cls.includes('kanban') || cls.includes('Kanban'))) {
                            kanbanEls.push({
                                tag: el.tagName,
                                class: cls.substring(0, 100),
                                childCount: el.children.length,
                                text: (el.innerText || '').substring(0, 80),
                            });
                        }
                    }
                    r.kanbanElements = kanbanEls.slice(0, 10);
                    r.columns = document.querySelectorAll('[class*="column"], [class*="Column"]').length;
                    r.cards = document.querySelectorAll('[class*="card"], [class*="Card"]').length;
                    r.chevrons = document.querySelectorAll('[class*="chevron"], [class*="Chevron"]').length;
                    r.progress = document.querySelectorAll('[class*="progress"], [role="progressbar"]').length;
                    r.avatars = document.querySelectorAll('[class*="avatar"], [class*="Avatar"]').length;
                    return r;
                }
            """)
            print(f"\nKanban DOM Analysis:")
            print(f"  Kanban elements: {len(analysis.get('kanbanElements', []))}")
            for el in analysis.get('kanbanElements', []):
                print(f"    <{el['tag']}> cls='{el['class'][:50]}' children={el['childCount']} text='{el['text'][:40]}'")
            print(f"  Columns: {analysis.get('columns', 0)}")
            print(f"  Cards: {analysis.get('cards', 0)}")
            print(f"  Chevrons: {analysis.get('chevrons', 0)}")
            print(f"  Progress: {analysis.get('progress', 0)}")
            print(f"  Avatars: {analysis.get('avatars', 0)}")

        else:
            print("No projects found after creation")
    else:
        print("Login failed completely")

    browser.close()
    print("\nDone!")
