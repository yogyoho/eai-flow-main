"""learnings importer 测试 — 正典账本格式解析契约(纯函数).

格式漂移在此先失败(importer 是 P0->P1 硬切换的唯一通道, D15).
"""

from app.extensions.learnings.scripts.import_ledger import parse_ledger

_LEDGER_SAMPLE = """---
name: learnings-ledger
description: "User lessons ledger [learn:2]. Read /mnt/skills/learnings-ledger/SKILL.md before non-trivial tasks."
---

# Learnings Ledger

<!-- LEDGER-START -->

### L-014 | error | deps.module-not-found | status:pending | count:2
summary: pnpm install 缺 node-gyp
evidence: '''ERR! 404'''
first: 2026-09-12 | last: 2026-09-14 | threads: t1,t2
action: 基础镜像预装 build-essential

### L-015 | correction | output.volume-unit | status:resolved | count:1
summary: 体积单位用 m³
evidence: '''用户纠正'''
first: 2026-09-13 | last: 2026-09-13 | threads: t9
action: 输出体积一律 m³
skill: output-format-rules

<!-- LEDGER-END -->

## Resolved archive
- [L-001] runtime.failure ×1 已归档 @2026-09-10
"""


def test_parses_canonical_entries():
    entries = parse_ledger(_LEDGER_SAMPLE)
    assert len(entries) == 2
    first = entries[0]
    assert first["legacy_id"] == "L-014"
    assert first["kind"] == "error"
    assert first["pattern_key"] == "deps.module-not-found"
    assert first["status"] == "pending"
    assert first["count"] == 2
    assert first["summary"] == "pnpm install 缺 node-gyp"
    assert first["threads"] == ["t1", "t2"]
    assert first["suggested_action"] == "基础镜像预装 build-essential"


def test_parses_promoted_skill_backlink():
    entries = parse_ledger(_LEDGER_SAMPLE)
    assert entries[1]["status"] == "resolved"
    assert entries[1]["promoted_skill"] == "output-format-rules"


def test_archive_one_liners_are_not_entries():
    """归档行(- [L-xxx] ...)不是条目, 不参与导入."""
    entries = parse_ledger(_LEDGER_SAMPLE)
    assert all(e["legacy_id"] != "L-001" for e in entries)


def test_format_drift_returns_empty():
    """字段改名/格式漂移 -> 0 条 -> importer 显式报错退出(importer main 契约)."""
    drifted = _LEDGER_SAMPLE.replace("status:", "state:")
    assert parse_ledger(drifted) == []
