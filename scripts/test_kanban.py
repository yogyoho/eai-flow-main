"""Test Kanban board with correctly mocked API."""
from playwright.sync_api import sync_playwright
import os, json

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", ".wolf", "test-captures")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

MOCK_PROJECT = {
    "id": "test-proj-001",
    "name": "2025年度AI行业研究报告",
    "report_type": "industry_report",
    "status": "writing",
    "current_stage": 4,
    "template_id": None,
    "template_name": None,
    "chapter_count": 12,
    "member_count": 4,
    "created_by": "admin",
    "chapters": [
        {
            "id": "ch-1", "project_id": "test-proj-001", "parent_id": None,
            "title": "第一章 行业概述", "level": 1, "sort_order": 1,
            "status": "completed", "content": None,
            "assigned_to": "u1", "assigned_name": "张明",
            "word_count_target": 8000, "word_count_current": 8200,
            "purpose": "概述AI行业整体情况", "generation_hint": None,
            "created_at": "2025-05-01T10:00:00Z", "updated_at": "2025-05-20T14:00:00Z",
            "children": [
                {"id": "ch-1-1", "project_id": "test-proj-001", "parent_id": "ch-1",
                 "title": "1.1 行业定义与范围", "level": 2, "sort_order": 1,
                 "status": "completed", "content": None,
                 "assigned_to": "u1", "assigned_name": "张明",
                 "word_count_target": 3000, "word_count_current": 3100,
                 "purpose": None, "generation_hint": None,
                 "created_at": None, "updated_at": None, "children": []},
                {"id": "ch-1-2", "project_id": "test-proj-001", "parent_id": "ch-1",
                 "title": "1.2 发展历程回顾", "level": 2, "sort_order": 2,
                 "status": "completed", "content": None,
                 "assigned_to": "u2", "assigned_name": "李华",
                 "word_count_target": 5000, "word_count_current": 5100,
                 "purpose": None, "generation_hint": None,
                 "created_at": None, "updated_at": None, "children": []}
            ]
        },
        {
            "id": "ch-2", "project_id": "test-proj-001", "parent_id": None,
            "title": "第二章 市场规模与格局", "level": 1, "sort_order": 2,
            "status": "writing", "content": None,
            "assigned_to": "u2", "assigned_name": "李华",
            "word_count_target": 10000, "word_count_current": 4500,
            "purpose": None, "generation_hint": None,
            "created_at": None, "updated_at": None,
            "children": [
                {"id": "ch-2-1", "project_id": "test-proj-001", "parent_id": "ch-2",
                 "title": "2.1 全球市场规模", "level": 2, "sort_order": 1,
                 "status": "writing", "content": None,
                 "assigned_to": "u2", "assigned_name": "李华",
                 "word_count_target": 5000, "word_count_current": 3200,
                 "purpose": None, "generation_hint": None,
                 "created_at": None, "updated_at": None, "children": []},
                {"id": "ch-2-2", "project_id": "test-proj-001", "parent_id": "ch-2",
                 "title": "2.2 中国市场分析", "level": 2, "sort_order": 2,
                 "status": "not_started", "content": None,
                 "assigned_to": None, "assigned_name": None,
                 "word_count_target": 5000, "word_count_current": 1300,
                 "purpose": None, "generation_hint": None,
                 "created_at": None, "updated_at": None, "children": []}
            ]
        },
        {
            "id": "ch-3", "project_id": "test-proj-001", "parent_id": None,
            "title": "第三章 技术发展分析", "level": 1, "sort_order": 3,
            "status": "pending_review", "content": None,
            "assigned_to": "u3", "assigned_name": "王芳",
            "word_count_target": 12000, "word_count_current": 6000,
            "purpose": None, "generation_hint": None,
            "created_at": None, "updated_at": None,
            "children": [
                {"id": "ch-3-1", "project_id": "test-proj-001", "parent_id": "ch-3",
                 "title": "3.1 大语言模型", "level": 2, "sort_order": 1,
                 "status": "pending_review", "content": None,
                 "assigned_to": "u3", "assigned_name": "王芳",
                 "word_count_target": 6000, "word_count_current": 4000,
                 "purpose": None, "generation_hint": None,
                 "created_at": None, "updated_at": None, "children": []},
                {"id": "ch-3-2", "project_id": "test-proj-001", "parent_id": "ch-3",
                 "title": "3.2 多模态AI", "level": 2, "sort_order": 2,
                 "status": "rejected", "content": None,
                 "assigned_to": "u1", "assigned_name": "张明",
                 "word_count_target": 6000, "word_count_current": 5800,
                 "purpose": None, "generation_hint": None,
                 "created_at": None, "updated_at": None, "children": []}
            ]
        },
        {
            "id": "ch-4", "project_id": "test-proj-001", "parent_id": None,
            "title": "第四章 应用场景与案例", "level": 1, "sort_order": 4,
            "status": "not_started", "content": None,
            "assigned_to": None, "assigned_name": None,
            "word_count_target": 10000, "word_count_current": 0,
            "purpose": None, "generation_hint": None,
            "created_at": None, "updated_at": None,
            "children": [
                {"id": "ch-4-1", "project_id": "test-proj-001", "parent_id": "ch-4",
                 "title": "4.1 智能客服", "level": 2, "sort_order": 1,
                 "status": "not_started", "content": None,
                 "assigned_to": None, "assigned_name": None,
                 "word_count_target": 5000, "word_count_current": 0,
                 "purpose": None, "generation_hint": None,
                 "created_at": None, "updated_at": None, "children": []},
                {"id": "ch-4-2", "project_id": "test-proj-001", "parent_id": "ch-4",
                 "title": "4.2 自动驾驶", "level": 2, "sort_order": 2,
                 "status": "not_started", "content": None,
                 "assigned_to": "u4", "assigned_name": "赵磊",
                 "word_count_target": 5000, "word_count_current": 0,
                 "purpose": None, "generation_hint": None,
                 "created_at": None, "updated_at": None, "children": []}
            ]
        },
        {
            "id": "ch-5", "project_id": "test-proj-001", "parent_id": None,
            "title": "第五章 趋势展望与建议", "level": 1, "sort_order": 5,
            "status": "approved", "content": None,
            "assigned_to": "u1", "assigned_name": "张明",
            "word_count_target": 6000, "word_count_current": 6200,
            "purpose": None, "generation_hint": None,
            "created_at": None, "updated_at": None, "children": []
        }
    ]
}

MOCK_LIST = {
    "items": [{
        "id": "test-proj-001",
        "name": "2025年度AI行业研究报告",
        "report_type": "industry_report",
        "status": "writing",
        "current_stage": 4,
        "template_id": None,
        "template_name": None,
        "chapter_count": 12,
        "member_count": 4,
        "created_by": "admin"
    }],
    "total": 1
}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Intercept the correct API path: /api/extensions/project/projects
    def handle_api(route):
        url = route.request.url
        if "/api/extensions/project/projects/test-proj-001" in url and "chapters" not in url:
            print(f"    [MOCK] project detail -> {url}")
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(MOCK_PROJECT))
        elif "/api/extensions/project/projects?" in url or url.endswith("/api/extensions/project/projects"):
            print(f"    [MOCK] project list -> {url}")
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(MOCK_LIST))
        else:
            route.continue_()

    page.route("**/api/extensions/project/**", handle_api)

    # ── Navigate to kanban tab ──
    print("[1] Navigating to kanban tab ...")
    page.goto("http://localhost:2026/projects/test-proj-001?tab=kanban",
              wait_until="networkidle", timeout=20000)
    page.wait_for_timeout(3000)

    # Debug: what rendered
    body_text = page.locator("body").inner_text()
    print(f"[2] Body text (first 800):\n{body_text[:800]}")
    print(f"    URL: {page.url}")

    # Take full desktop screenshot
    page.screenshot(path=os.path.join(SCREENSHOT_DIR, "10_kanban_desktop.png"), full_page=False)
    print("[3] Saved 10_kanban_desktop.png")

    # Scroll kanban right
    kanban = page.locator(".overflow-x-auto")
    if kanban.count() > 0:
        kanban.first.evaluate("el => el.scrollLeft = 600")
        page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "11_kanban_scrolled.png"))
        print("[4] Saved 11_kanban_scrolled.png")

    # Tablet view
    page.set_viewport_size({"width": 1024, "height": 768})
    page.wait_for_timeout(1000)
    page.screenshot(path=os.path.join(SCREENSHOT_DIR, "12_kanban_tablet.png"))
    print("[5] Saved 12_kanban_tablet.png")

    # Mobile view
    page.set_viewport_size({"width": 375, "height": 812})
    page.wait_for_timeout(1000)
    page.screenshot(path=os.path.join(SCREENSHOT_DIR, "13_kanban_mobile.png"))
    print("[6] Saved 13_kanban_mobile.png")

    # Restore desktop for header-gap screenshot
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto("http://localhost:2026/projects/test-proj-001?tab=kanban",
              wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(2500)
    page.screenshot(
        path=os.path.join(SCREENSHOT_DIR, "14_header_gap.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 200}
    )
    print("[7] Saved 14_header_gap.png")

    browser.close()
    print("\n[DONE] All screenshots saved to .wolf/test-captures/")
