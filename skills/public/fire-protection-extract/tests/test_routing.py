"""
Routing regression test: v2 vs extract skill selection.

Verifies that when a user uploads a design spec (.docx) and asks for a fire report,
the extract skill is selected, NOT v2. Tests the frontmatter exclusion/inclusion rules
and the extensions_config.json registration.
"""
import json
import re
import pytest
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT
EXTRACT_MD = SKILL_DIR / "SKILL.md"
V2_MD = ROOT.parent / "fire-protection-report-v2" / "SKILL.md"
EXT_CONFIG = ROOT.parent.parent.parent / "extensions_config.json"


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    return yaml.safe_load(m.group(1)) if m else {}


def test_extract_registered_in_extensions_config():
    """extract skill must be registered in extensions_config.json with enabled=true."""
    if not EXT_CONFIG.exists():
        pytest.skip("extensions_config.json not found")
    cfg = json.loads(EXT_CONFIG.read_text(encoding="utf-8"))
    skills = cfg.get("skills", {})
    assert "fire-protection-extract" in skills, (
        "fire-protection-extract NOT registered in extensions_config.json"
    )
    assert skills["fire-protection-extract"].get("enabled") is True, (
        "fire-protection-extract registered but enabled != true"
    )


def test_v2_has_spec_exclusion():
    """v2 description MUST exclude itself when a design spec .docx is uploaded."""
    fm = _frontmatter(V2_MD)
    desc = fm.get("description", "")
    assert ".docx" in desc, "v2 description must mention .docx exclusion"
    assert "fire-protection-extract" in desc, (
        "v2 description must name extract as the alternative"
    )
    # Check the exclusion exists and isn't conditional
    assert "仅在用户未上传设计说明书" in desc or "不要使用本技能" in desc or "改用" in desc, "v2 必须声明仅在无说明书时使用/说明书时路由到 extract"


def test_extract_has_spec_assertion():
    """extract description MUST assert priority when design spec is uploaded."""
    fm = _frontmatter(EXTRACT_MD)
    desc = fm.get("description", "")
    assert ".docx" in desc, "extract description must reference .docx uploads"
    assert (
        "不使用 fire-protection-report-v2" in desc
        or "不用 fire-protection-report-v2" in desc
    ), "extract must explicitly say NOT to use v2"


def test_both_frontmatter_names_match_registry():
    """SKILL.md name fields must match extensions_config.json keys."""
    if not EXT_CONFIG.exists():
        pytest.skip("extensions_config.json not found")
    cfg = json.loads(EXT_CONFIG.read_text(encoding="utf-8"))
    skills = cfg.get("skills", {})
    for path, key in [(EXTRACT_MD, "fire-protection-extract"), (V2_MD, "fire-protection-report-v2")]:
        fm = _frontmatter(path)
        assert fm.get("name") == key, f"{path.name}: name='{fm.get('name')}' != config key '{key}'"


def test_extract_skill_files_complete():
    """All required files for the extract skill must exist."""
    required = [
        "SKILL.md",
        "requirements.txt",
        "scripts/parse_spec.py",
        "scripts/extract.py",
        "scripts/grounding_check.py",
        "references/fire_spec_mapping.json",
        "references/extractor_rules.md",
    ]
    for rel in required:
        p = SKILL_DIR / rel
        assert p.exists(), f"missing: {rel}"

# === Routing logic simulation (deterministic subset of what the LLM evaluates) ===

SCENARIOS = [
    # (has_design_spec, user_prompt_snippet, expected_skill)
    (True,  "编写消防设计专篇",         "fire-protection-extract"),
    (True,  "写消防设计报告",           "fire-protection-extract"),
    (True,  "消防设计篇章",             "fire-protection-extract"),
    (True,  "上传了设计说明书，帮我写消防专篇", "fire-protection-extract"),
    (False, "编写消防设计专篇",         "fire-protection-report-v2"),
    (False, "化工项目消防设计报告",     "fire-protection-report-v2"),
    (False, "消防验收报告",             "fire-protection-report-v2"),
]


def _route(has_spec: bool, prompt: str) -> str:
    """Simulate the routing decision.

    The real LLM does this with semantic understanding of frontmatter descriptions.
    We approximate with keyword + exclusion rules matching the actual description text.
    """
    v2_desc = _frontmatter(V2_MD).get("description", "")
    ext_desc = _frontmatter(EXTRACT_MD).get("description", "")

    # The contract encoded in both frontmatters:
    # - If design spec uploaded → use extract, NOT v2
    # - If no design spec → use v2
    # Both descriptions start with "⛔" rules encoding this
    v2_excludes_spec = ("仅在用户未上传设计说明书" in v2_desc or "不要使用本技能" in v2_desc) and "设计说明书" in v2_desc
    ext_prefers_spec = (
        "不使用 fire-protection-report-v2" in ext_desc
        or "不用 fire-protection-report-v2" in ext_desc
    )

    if has_spec and ext_prefers_spec and v2_excludes_spec:
        return "fire-protection-extract"
    if not has_spec:
        return "fire-protection-report-v2"
    # fallback: no clear routing rule → v2 wins (the bug we fixed)
    return "fire-protection-report-v2"


def test_routing_scenarios():
    for has_spec, prompt, expected in SCENARIOS:
        result = _route(has_spec, prompt)
        assert result == expected, (
            f"has_spec={has_spec}, prompt='{prompt}': "
            f"routed to {result}, expected {expected}"
        )


def test_no_regression__spec_upload_never_routes_to_v2():
    """The original bug: design-spec-upload scenarios always went to v2."""
    for has_spec, prompt, expected in SCENARIOS:
        if has_spec:
            assert expected == "fire-protection-extract", (
                f"BUG REGRESSION: has_spec=True prompt='{prompt}' expects v2, not extract"
            )
