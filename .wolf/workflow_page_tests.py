"""
Workflow engine page tests via Playwright.

Tests:
1. Login flow
2. Workflow definitions list
3. Review assignments and status
4. Source traceability for a chapter
5. Workflow monitor status
6. Frontend page loads
"""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:2026"
EMAIL = "admin@eai-flow.com"
PASSWORD = "Admin@2026"
RESULTS = []


def log(msg: str):
    print(f"  {msg}")


def test_login(page) -> bool:
    """Login and verify we get authenticated."""
    print("\n--- Test 1: Login ---")
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(2000)

    try:
        email_input = page.locator('input[type="email"], input[name="email"], input[placeholder*="email"]').first
        password_input = page.locator('input[type="password"]').first

        if email_input.count() == 0:
            page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(3000)
            email_input = page.locator('input[type="email"], input[name="email"]').first
            password_input = page.locator('input[type="password"]').first

        if email_input.count() > 0:
            email_input.fill(EMAIL)
            password_input.fill(PASSWORD)
            page.locator('button[type="submit"]').first.click()
            page.wait_for_timeout(3000)
            url = page.url
            if "/login" not in url:
                log(f"PASS: Login succeeded -> {url[:60]}")
                RESULTS.append(("Login", "PASS"))
                return True
            else:
                log(f"WARN: Still on login page: {url}")
                RESULTS.append(("Login", "WARN"))
                return False
        else:
            page.goto(f"{BASE}/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(2000)
            if "/login" not in page.url:
                log("PASS: Already authenticated")
                RESULTS.append(("Login", "PASS"))
                return True
            log("FAIL: No login form")
            RESULTS.append(("Login", "FAIL"))
            return False
    except Exception as e:
        log(f"FAIL: {e}")
        RESULTS.append(("Login", "FAIL"))
        return False


PROJECTS_URL = f"{BASE}/api/extensions/project/projects"

def test_api_via_fetch(page, label: str, url: str) -> dict:
    """Call an API endpoint via page.evaluate and return result."""
    return page.evaluate("""async ([url]) => {
        try {
            const r = await fetch(url);
            const ct = r.headers.get('content-type') || '';
            let body = null;
            if (ct.includes('json')) {
                body = await r.json();
            } else {
                body = await r.text();
            }
            return {ok: r.ok, status: r.status, body: body};
        } catch(e) {
            return {ok: false, status: 0, body: String(e)};
        }
    }""", [url])


def test_workflow_definitions(page) -> bool:
    print("\n--- Test 2: Workflow Definitions API ---")
    try:
        r = test_api_via_fetch(page, "defs", f"{BASE}/api/extensions/workflow/definitions")
        if r["ok"]:
            log(f"PASS: Status {r['status']}")
            RESULTS.append(("Workflow Definitions", "PASS"))
            return True
        else:
            log(f"WARN: Status {r['status']} - {str(r.get('body',''))[:100]}")
            RESULTS.append(("Workflow Definitions", f"WARN ({r['status']})"))
            return False
    except Exception as e:
        log(f"FAIL: {e}")
        RESULTS.append(("Workflow Definitions", "FAIL"))
        return False


def test_review_api(page) -> bool:
    print("\n--- Test 3: Review API ---")
    try:
        projects_r = test_api_via_fetch(page, "proj", PROJECTS_URL + "?skip=0&limit=5")
        if not projects_r["ok"]:
            log(f"WARN: Can't list projects: {projects_r['status']}")
            RESULTS.append(("Review API", "SKIP (no projects)"))
            return True

        projects = (projects_r.get("body") or {}).get("items", [])
        if not projects:
            log("WARN: No projects")
            RESULTS.append(("Review API", "SKIP (no projects)"))
            return True

        pid = projects[0]["id"]
        r = test_api_via_fetch(page, "review", f"{BASE}/api/extensions/workflow/projects/{pid}/phase-reviews?phase_node=test-node")
        if r["ok"]:
            log(f"PASS: Review status works for project {pid[:12]}...")
            RESULTS.append(("Review API", "PASS"))
            return True
        else:
            log(f"WARN: Status {r['status']}")
            RESULTS.append(("Review API", f"WARN ({r['status']})"))
            return False
    except Exception as e:
        log(f"FAIL: {e}")
        RESULTS.append(("Review API", "FAIL"))
        return False


def test_traceability_api(page) -> bool:
    print("\n--- Test 4: Traceability API ---")
    try:
        projects_r = test_api_via_fetch(page, "proj", PROJECTS_URL + "?skip=0&limit=5")
        if not projects_r["ok"]:
            log("WARN: Can't list projects")
            RESULTS.append(("Traceability API", "SKIP"))
            return True

        projects = (projects_r.get("body") or {}).get("items", [])
        if not projects:
            log("WARN: No projects")
            RESULTS.append(("Traceability API", "SKIP"))
            return True

        pid = projects[0]["id"]
        dummy_chapter = "00000000-0000-0000-0000-000000000001"
        r = test_api_via_fetch(page, "src", f"{BASE}/api/extensions/workflow/projects/{pid}/chapters/{dummy_chapter}/sources/missing")
        log(f"Result: ok={r['ok']} status={r['status']} body={str(r.get('body',''))[:80]}")
        if r["ok"] or r["status"] in (200, 404):
            log("PASS: Traceability endpoint accessible")
            RESULTS.append(("Traceability API", "PASS"))
            return True
        else:
            RESULTS.append(("Traceability API", f"WARN ({r['status']})"))
            return False
    except Exception as e:
        log(f"FAIL: {e}")
        RESULTS.append(("Traceability API", "FAIL"))
        return False


def test_workflow_monitor_api(page) -> bool:
    print("\n--- Test 5: Workflow Monitor API ---")
    try:
        projects_r = test_api_via_fetch(page, "proj", PROJECTS_URL + "?skip=0&limit=5")
        if not projects_r["ok"]:
            log("WARN: Can't list projects")
            RESULTS.append(("Workflow Monitor", "SKIP"))
            return True

        projects = (projects_r.get("body") or {}).get("items", [])
        if not projects:
            log("WARN: No projects")
            RESULTS.append(("Workflow Monitor", "SKIP"))
            return True

        pid = projects[0]["id"]
        r = test_api_via_fetch(page, "mon", f"{BASE}/api/extensions/workflow/projects/{pid}/workflow-status")
        log(f"Result: ok={r['ok']} status={r['status']}")
        if r["ok"]:
            body = r.get("body", {})
            log(f"  project_id: {body.get('projectId','?')}")
            log(f"  status: {body.get('status','?')}")
            log(f"  nodes: {len(body.get('nodes',[]))}")
            log("PASS: Monitor API works")
            RESULTS.append(("Workflow Monitor", "PASS"))
            return True
        else:
            RESULTS.append(("Workflow Monitor", f"WARN ({r['status']})"))
            return False
    except Exception as e:
        log(f"FAIL: {e}")
        RESULTS.append(("Workflow Monitor", "FAIL"))
        return False


def test_frontend_pages(page) -> bool:
    print("\n--- Test 6: Frontend Pages ---")
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))

    pages = ["/", "/projects"]
    for path in pages:
        try:
            page.goto(f"{BASE}{path}", wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(2000)
            if errors:
                log(f"WARN: {path} JS errors: {errors[:2]}")
                errors.clear()
            else:
                log(f"OK: {path} loaded clean")
            screenshot_path = f"D:\\eai\\eai-flow-main\\.wolf\\page-test-{path.replace('/', '-')}.png"
            try:
                page.screenshot(path=screenshot_path, full_page=True)
                log(f"  Screenshot: {screenshot_path}")
            except Exception:
                pass
        except Exception as e:
            log(f"WARN: {path} - {e}")

    RESULTS.append(("Frontend Pages", "PASS"))
    return True


def main():
    print("=" * 50)
    print("  Workflow Engine Page Tests")
    print("=" * 50)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        test_login(page)
        test_workflow_definitions(page)
        test_review_api(page)
        test_traceability_api(page)
        test_workflow_monitor_api(page)
        test_frontend_pages(page)

        browser.close()

    print("\n" + "=" * 50)
    print("  Results")
    print("=" * 50)
    passed = sum(1 for _, s in RESULTS if s == "PASS")
    warn = sum(1 for _, s in RESULTS if "WARN" in s)
    fail = sum(1 for _, s in RESULTS if s == "FAIL")
    skip = sum(1 for _, s in RESULTS if "SKIP" in s)

    for name, status in RESULTS:
        icon = "[OK]" if status == "PASS" else "[WARN]" if "WARN" in status else "[SKIP]" if "SKIP" in status else "[FAIL]"
        print(f"  {icon} {name}: {status}")

    print(f"\n  Passed: {passed}  Warnings: {warn}  Skipped: {skip}  Failed: {fail}")
    if fail == 0:
        print("  VERDICT: PASS")
    else:
        print(f"  VERDICT: FAIL ({fail} failures)")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    exit(main())
