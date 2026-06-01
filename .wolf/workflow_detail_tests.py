"""Detailed API response validation for workflow features."""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:2026"
EMAIL = "admin@eai-flow.com"
PASSWORD = "Admin@2026"
RESULTS = []


def log(msg):
    print(f"  {msg}")


def fetch(page, url, method="GET", body=None):
    """Call an API endpoint. body is a Python dict that Playwright serializes as JS object."""
    resp = page.evaluate("""async ({url, method, body}) => {
        const init = {method: method, headers: {"Content-Type": "application/json"}};
        if (body) init.body = JSON.stringify(body);
        const r = await fetch(url, init);
        const ct = r.headers.get('content-type') || '';
        if (ct.includes('json')) return {ok: r.ok, status: r.status, body: await r.json()};
        return {ok: r.ok, status: r.status, body: await r.text()};
    }""", {"url": url, "method": method, "body": body})
    return resp


def main():
    print("=" * 50)
    print("  Workflow Detail API Tests")
    print("=" * 50)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # Login
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.locator('input[type="password"]').first.fill(PASSWORD)
        page.locator('input:not([type="password"])').first.fill(EMAIL)
        page.locator('button[type="submit"]').first.click()
        page.wait_for_timeout(3000)

        if "/login" in page.url:
            print("FAIL: Could not login")
            browser.close()
            return 1
        print("OK: Logged in")

        # 1. Workflow Definitions
        print("\n--- API 1: GET /workflow/definitions ---")
        r = fetch(page, f"{BASE}/api/extensions/workflow/definitions")
        print(f"  Status: {r['status']}")
        items = r.get("body", {}).get("items", [])
        print(f"  Count: {len(items)}")
        if items:
            print(f"  First: {items[0].get('name', '?')} (type={items[0].get('reportType','?')})")
        RESULTS.append(("GET definitions", "PASS" if r['ok'] else "FAIL"))

        # 2. Get first project
        print("\n--- API 2: GET /project/projects ---")
        r = fetch(page, f"{BASE}/api/extensions/project/projects?skip=0&limit=5")
        proj_items = r.get("body", {}).get("items", [])
        print(f"  Projects found: {len(proj_items)}")
        if proj_items:
            pid = proj_items[0]["id"]
            print(f"  Project ID: {pid}")
            print(f"  Name: {proj_items[0].get('name', '?')}")
            print(f"  Status: {proj_items[0].get('status', '?')}")
            RESULTS.append(("GET projects", "PASS"))
        else:
            print("  WARN: No projects — skipping project-dependent tests")
            RESULTS.append(("GET projects", "SKIP"))
            pid = None

        # 3. Workflow Status (with real project)
        if pid:
            print("\n--- API 3: GET /projects/{id}/workflow-status ---")
            r = fetch(page, f"{BASE}/api/extensions/workflow/projects/{pid}/workflow-status")
            print(f"  Status: {r['status']}")
            body = r.get("body", {})
            print(f"  projectId: {body.get('projectId', '?')}")
            print(f"  workflowId: {body.get('workflowId', 'None')}")
            print(f"  temporalWorkflowId: {body.get('temporalWorkflowId', 'None')}")
            print(f"  status: {body.get('status', '?')}")
            print(f"  currentPhaseNode: {body.get('currentPhaseNode', 'None')}")
            print(f"  nodes count: {len(body.get('nodes', []))}")
            RESULTS.append(("GET workflow-status", "PASS" if r['ok'] else "FAIL"))

            # 4. Review Status
            print("\n--- API 4: GET /projects/{id}/phase-reviews ---")
            r = fetch(page, f"{BASE}/api/extensions/workflow/projects/{pid}/phase-reviews?phase_node=review-1")
            print(f"  Status: {r['status']}")
            body = r.get("body", {})
            print(f"  total: {body.get('total', '?')}")
            print(f"  approved: {body.get('approved', '?')}")
            print(f"  rejected: {body.get('rejected', '?')}")
            RESULTS.append(("GET phase-reviews", "PASS" if r['ok'] else "FAIL"))

            # 5. Workflow Signal endpoint
            print("\n--- API 5: POST /projects/{id}/workflow-signal ---")
            r = fetch(page, f"{BASE}/api/extensions/workflow/projects/{pid}/workflow-signal",
                      method="POST", body={"signal_name": "test_signal", "args": {"key": "val"}})
            print(f"  Status: {r['status']}")
            print(f"  Body: {r.get('body', '?')}")
            RESULTS.append(("POST workflow-signal", "PASS" if r['ok'] or r['status'] in (400, 422) else "FAIL"))

            # 6. Review assignment
            print("\n--- API 6: POST /projects/{id}/phase-reviews/assign ---")
            from uuid import uuid4
            test_reviewer = str(uuid4())
            r = fetch(page, f"{BASE}/api/extensions/workflow/projects/{pid}/phase-reviews/assign",
                      method="POST", body={
                          "project_id": pid,
                          "phase_node": "review-test",
                          "assignments": [{
                              "reviewer_id": test_reviewer,
                              "review_type": "chapter"
                          }]
                      })
            print(f"  Status: {r['status']}")
            body = r.get("body", [])
            if isinstance(body, list) and len(body) > 0:
                print(f"  Created {len(body)} review assignment(s)")
                review_id = body[0].get("id")
                review_status = body[0].get("status")
                print(f"  Review ID: {review_id}")
                print(f"  Status: {review_status}")

                # 7. Submit review action
                print(f"\n--- API 7: POST /projects/{pid}/phase-reviews/{review_id}/action ---")
                r2 = fetch(page, f"{BASE}/api/extensions/workflow/projects/{pid}/phase-reviews/{review_id}/action",
                           method="POST", body={"action": "approved", "comment": "LGTM"})
                print(f"  Status: {r2['status']}")
                if r2.get("body", {}).get("status") == "approved":
                    print("  Action: review marked as approved")
                RESULTS.append(("Review assign+action cycle", "PASS" if r2['ok'] else "FAIL"))
                RESULTS.append(("POST phase-reviews/assign", "PASS"))
            else:
                body_detail = body if isinstance(body, str) else str(body)[:100]
                print(f"  Response: {body_detail}")
                RESULTS.append(("POST phase-reviews/assign", "WARN" if r["ok"] else "FAIL"))

            # 8. Source traceability - parse endpoint
            print("\n--- API 8: POST /chapters/{id}/sources/parse ---")
            from uuid import uuid4 as uuid4v2
            dummy_ch = str(uuid4v2())
            r = fetch(page, f"{BASE}/api/extensions/workflow/projects/{pid}/chapters/{dummy_ch}/sources/parse",
                      method="POST")
            print(f"  Status: {r['status']}")
            print(f"  Body: {r.get('body', '?')}")
            # 404 for missing chapter is expected and fine
            RESULTS.append(("POST sources/parse", "PASS" if r['ok'] or r['status'] in (200, 404) else "FAIL"))

        # 9. Source marker parsing (inline test via API)
        print("\n--- API 9: GET /chapters/{id}/sources/missing ---")
        if pid:
            from uuid import uuid4 as uuid4v3
            dummy_ch = str(uuid4v3())
            r = fetch(page, f"{BASE}/api/extensions/workflow/projects/{pid}/chapters/{dummy_ch}/sources/missing")
            print(f"  Status: {r['status']}")
            print(f"  Body: {r.get('body', '?')}")
            RESULTS.append(("GET sources/missing", "PASS" if r['ok'] or r['status'] in (200, 404) else "FAIL"))

        browser.close()

    # Summary
    print("\n" + "=" * 50)
    print("  Detail Results")
    print("=" * 50)
    passed = 0
    for name, status in RESULTS:
        icon = "[OK]" if status == "PASS" else "[-]" if "WARN" in status else "[  ]" if "SKIP" in status else "[XX]"
        print(f"  {icon} {name}: {status}")
        if status == "PASS":
            passed += 1

    total = len(RESULTS)
    print(f"\n  {passed}/{total} passed  {total-passed} issues")
    print("  VERDICT: PASS" if total - passed == 0 else f"  VERDICT: {total-passed} issues to review")


if __name__ == "__main__":
    main()
