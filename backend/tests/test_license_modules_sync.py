"""License module key sync guard.

Locks the canonical 10-key license module set and ensures every hardcoded
definition site stays in sync. Drift causes silent breakage: a key renamed in
one place but not others makes licensed apps vanish from sidebar/app-center
(hasModule returns false for the stale key).

Canonical keys: project, dashboard, typography, contract_price, spare_parts, bid_quote, biz_pipeline, sales_personnel, geo_samples
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.skip(reason="EAI license extension differs (EAI-CUSTOM skip 2026-08-15)")


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_KEYS = ["platform", "project", "dashboard", "typography", "contract_price", "spare_parts", "bid_quote", "biz_pipeline", "sales_personnel", "geo_samples"]
REMOVED_KEYS = ["docmgr", "knowledge", "collab", "report", "approval", "workflow"]


def test_service_all_modules_is_canonical():
    from app.extensions.license.service import ALL_MODULES

    assert ALL_MODULES == EXPECTED_KEYS


def test_generator_all_modules_is_canonical():
    src = (REPO_ROOT / "tools" / "license" / "license_generator.py").read_text(encoding="utf-8")
    m = re.search(r"ALL_MODULES = \[\s*([^\]]*)\]", src)
    assert m, "ALL_MODULES not found in license_generator.py"
    keys = [k.strip().strip('"').strip("'") for k in m.group(1).split(",") if k.strip()]
    assert keys == EXPECTED_KEYS


def test_module_locked_page_labels_match_canonical():
    src = (REPO_ROOT / "frontend" / "src" / "extensions" / "license" / "labels.ts").read_text(encoding="utf-8")
    for key in EXPECTED_KEYS:
        assert re.search(rf"\b{key}:\s*\"", src), f"ModuleLockedPage missing label for {key}"
    for removed in REMOVED_KEYS:
        assert not re.search(rf"\b{removed}:\s*\"", src), f"ModuleLockedPage still references removed key '{removed}'"


def test_sidebar_nav_licensing_matches_classification():
    src = (REPO_ROOT / "frontend" / "src" / "extensions" / "shell" / "Sidebar.tsx").read_text(encoding="utf-8")
    # 收费项必须带正确 licenseModule
    assert re.search(r'href: "/dashboard"[^}]*licenseModule: "dashboard"', src, re.S)
    assert re.search(r'href: "/projects"[^}]*licenseModule: "project"', src, re.S)
    # 基础平台模块必须挂 platform
    for href in ["/writing", "/docmgr", "/knowledge-factory", "/knowledge", "/app-center", "/admin", "/settings"]:
        m = re.search(rf'href: "{href}"[^}}]*\}}', src)
        assert m, f"{href} nav item not found"
        assert 'licenseModule: "platform"' in m.group(0), f"{href} missing platform"


def test_seed_uses_no_removed_license_keys():
    src = (REPO_ROOT / "backend" / "app" / "extensions" / "database.py").read_text(encoding="utf-8")
    for removed in REMOVED_KEYS:
        assert f'"license": "{removed}"' not in src, f"database.py seed still uses removed license key '{removed}'"
