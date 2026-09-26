"""learnings 扩展 — pattern-key 匹配器 + 证据洗数据管线(纯逻辑, 零 IO).

EAI-CUSTOM: 自进化循环 P1(设计 docs/designs/self-improving-loop-port.md D8/D12)。
- ERROR_PATTERNS: ordered specific→generic 字面量表, 首匹配生效
  (ModuleNotFoundError 必须先于 Error: 命中, 顺序即语义, 测试钉死)
- sanitize_evidence 固定顺序: 脱敏 → fence 转义 → 截断(顺序不变量, 测试钉死)
"""

from __future__ import annotations

import re

# --- 枚举(service 校验与 MCP inputSchema 共用) -------------------------------

KINDS = ("error", "correction", "knowledge_gap", "best_practice", "feature_request")
AREAS = (
    "deps", "fs", "net", "shell", "vcs", "runtime", "api",
    "auth", "build", "config", "tools", "mcp", "skill", "data",
    "backend", "frontend", "infra", "tests", "docs",
)
STATUSES = ("pending", "resolved", "dismissed", "promoted_to_skill")
MAX_EVIDENCE_CHARS = 200

# --- ordered 字面量表(specific → generic, 首匹配生效) -------------------------

ERROR_PATTERNS: tuple[tuple[str, str, str], ...] = (
    # (literal, area, symptom)
    ("ModuleNotFoundError", "deps", "module-not-found"),
    ("ImportError", "deps", "module-not-found"),
    ("npm ERR!", "deps", "npm-error"),
    ("pnpm install failed", "deps", "npm-error"),
    ("No such file", "fs", "no-such-file"),
    ("ENOENT", "fs", "no-such-file"),
    ("Permission denied", "fs", "permission-denied"),
    ("EACCES", "fs", "permission-denied"),
    ("command not found", "shell", "command-not-found"),
    ("is not recognized as", "shell", "command-not-found"),
    ("non-zero exit", "shell", "nonzero-exit"),
    ("exit code", "shell", "nonzero-exit"),
    ("Connection refused", "net", "connection-refused"),
    ("getaddrinfo failed", "net", "dns-failure"),
    ("Connection timed out", "net", "timeout"),
    ("fatal:", "vcs", "fatal-error"),
    ("CONFLICT", "vcs", "merge-conflict"),
    ("Traceback (most recent call last)", "runtime", "python-exception"),
    ("SyntaxError", "runtime", "syntax-error"),
    ("TypeError", "runtime", "type-error"),
    ("error:", "runtime", "error"),
    ("Error:", "runtime", "error"),
    ("ERROR:", "runtime", "error"),
    ("Exception", "runtime", "exception"),
    ("failed", "runtime", "failure"),
    ("FAILED", "runtime", "failure"),
)


def match_pattern_key(text: str) -> tuple[str, str]:
    """首匹配 specific→generic; 无命中落 runtime.failure(=未分类, triage 再细化)."""
    for literal, area, symptom in ERROR_PATTERNS:
        if literal in text:
            return area, symptom
    return "runtime", "failure"


# --- 脱敏(7 类 secret) --------------------------------------------------------

_REDACTION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # specific -> generic: 令牌形态规则在前, key=value 通配在后(否则通配先吃掉值)
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer <REDACTED>"),
    (re.compile(r"\beyJ[A-Za-z0-9._\-]{20,}"), "eyJ<REDACTED-JWT>"),
    (re.compile(r"\bsk-[A-Za-z0-9\-]{16,}"), "sk-<REDACTED>"),
    (re.compile(r"\bgh[posr]_[A-Za-z0-9]{16,}"), "gh_<REDACTED>"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), "xox<REDACTED>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}"), "AKIA<REDACTED>"),
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization|credential)\s*[=:]\s*\S+"), r"\1=<REDACTED>"),
)


def redact(text: str) -> str:
    for pattern, replacement in _REDACTION_RULES:
        text = pattern.sub(replacement, text)
    return text


def sanitize_evidence(text: str, max_chars: int = MAX_EVIDENCE_CHARS) -> str:
    """固定顺序(不可换, 测试钉死): 脱敏 → fence 转义 → 截断.

    fence 转义(``` → ''')防截断后的 markdown 越狱; 截断永远在最后,
    保证产物长度上界不含未脱敏内容。
    """
    cleaned = redact(text)
    cleaned = cleaned.replace("```", "'''")
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "…"
    return cleaned.replace("\n", " ").strip()


def canonical_symptom(symptom: str) -> str:
    """服务端 canonicalize(D6: agent 不能自造 key 形状)."""
    cleaned = re.sub(r"[^a-z0-9-]+", "-", (symptom or "").strip().lower()).strip("-")
    return re.sub(r"-{2,}", "-", cleaned)


def canonical_pattern_key(area: str, symptom: str) -> str:
    return f"{(area or 'runtime').strip().lower()}.{canonical_symptom(symptom)}"
