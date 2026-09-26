"""learnings patterns 纯逻辑测试 — 匹配顺序 + 洗数据顺序不变量(eng-review D8/D12)."""

from app.extensions.learnings.patterns import (
    match_pattern_key,
    redact,
    sanitize_evidence,
)


def test_specific_beats_generic():
    """ModuleNotFoundError 必须命中 deps.module-not-found, 而非兜底 runtime.*."""
    text = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'yaml'\nError: exit"
    assert match_pattern_key(text) == ("deps", "module-not-found")


def test_command_not_found():
    assert match_pattern_key("/bin/bash: line 1: systemctl: command not found") == ("shell", "command-not-found")


def test_fallback_is_runtime_failure():
    assert match_pattern_key("something totally unknown happened") == ("runtime", "failure")


def test_redaction_covers_all_seven_rule_classes():
    """安全不变量 = 原 secret 材料不存活(双脱敏无害, 不断言文本美容)."""
    samples = [
        ("api_key=sk123secretvalue", ["sk123secretvalue"]),
        ("Authorization: Bearer abc.def.ghi", ["abc.def.ghi"]),
        ("token sk-live-1234567890abcdef1234 leaked", ["sk-live-1234567890abcdef1234"]),
        ("token ghp_1234567890abcdefghijklmnop leaked", ["ghp_1234567890abcdefghijklmnop"]),
        ("slack xoxb-123-456-abcdef webhook", ["xoxb-123-456-abcdef"]),
        ("aws key AKIAIOSFODNN7EXAMPLE in config", ["AKIAIOSFODNN7EXAMPLE"]),
        ("jwt eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig end", ["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"]),
    ]
    for raw, secrets in samples:
        out = redact(raw)
        for secret in secrets:
            assert secret not in out, f"{raw} -> {out}"
        assert "<REDACTED" in out, raw


def test_sanitize_order_redact_before_truncate():
    """截断永远在脱敏之后: 截断窗口内的 secret 已被替换(顺序不变量)."""
    long_with_secret = "prefix api_key=supersecretvalue123 " + "x" * 300
    out = sanitize_evidence(long_with_secret)
    assert len(out) <= 201
    assert "supersecretvalue123" not in out
    assert "<REDACTED" in out


def test_sanitize_fence_escape_prevents_breakout():
    out = sanitize_evidence("```python\nsecret_block()\n```")
    assert "```" not in out
    assert "'''" in out


def test_sanitize_truncates_with_ellipsis():
    out = sanitize_evidence("a" * 500)
    assert len(out) == 201 and out.endswith("…")


def test_canonical_pattern_key_normalizes():
    from app.extensions.learnings.patterns import canonical_pattern_key

    assert canonical_pattern_key("Deps", "Module Not Found!!") == "deps.module-not-found"
    assert canonical_pattern_key("runtime", "") == "runtime."
