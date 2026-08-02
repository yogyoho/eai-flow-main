#!/usr/bin/env python3
"""Check import consistency across the backend.

Detects "partial upstream sync" residue: a synced .py file importing a module
whose file was not brought over (e.g. checkpointer_config.py referencing
deerflow.config.postgres_schema before that file was synced). Such gaps break
eager imports (tests / new gateway boots) while lazy imports still work — the
worst kind of breakage.

Run after every upstream sync batch:
    python scripts/check_import_consistency.py

Exit code 0 = all absolute imports resolve; 1 = broken imports found.

Only checks top-level ``app.*`` and ``deerflow.*`` modules (our two packages)
against the source tree. Third-party / stdlib / relative imports are skipped.
Dynamic imports (importlib) are not followed — this is a fast static guard,
not a proof.
"""

from __future__ import annotations

import ast
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Top-level package name → its source root on disk.
PACKAGE_ROOTS: dict[str, pathlib.Path] = {
    "app": REPO_ROOT / "backend" / "app",
    "deerflow": REPO_ROOT / "backend" / "packages" / "harness" / "deerflow",
}

SCAN_DIRS = (REPO_ROOT / "backend" / "app", REPO_ROOT / "backend" / "packages" / "harness" / "deerflow")


def module_exists(mod: str) -> bool:
    """Return True if a top-level dotted module (``app.x.y`` / ``deerflow.x.y``) resolves to a file."""
    parts = mod.split(".")
    top = parts[0]
    if top not in PACKAGE_ROOTS:
        return True  # third-party or stdlib — not our concern here
    rel = pathlib.Path(*parts[1:])
    base = PACKAGE_ROOTS[top]
    return (base / rel.with_suffix(".py")).exists() or (base / rel / "__init__.py").exists()


def find_broken_imports() -> list[tuple[str, int, str]]:
    """Return (file, lineno, module) for every absolute import that references a missing module file."""
    broken: list[tuple[str, int, str]] = []
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if not module_exists(alias.name):
                            broken.append((str(p), node.lineno, alias.name))
                elif isinstance(node, ast.ImportFrom):
                    # level == 0 = absolute import; relative intra-package imports are skipped.
                    if node.module and node.level == 0 and not module_exists(node.module):
                        broken.append((str(p), node.lineno, node.module))
    return broken


def main() -> int:
    broken = find_broken_imports()
    if not broken:
        print("IMPORT CONSISTENCY: OK — all absolute imports resolve.")
        return 0

    print(f"IMPORT CONSISTENCY: FAILED — {len(broken)} broken import(s):")
    # Group by missing module for a readable report.
    by_module: dict[str, list[tuple[str, int]]] = {}
    for file, lineno, mod in broken:
        by_module.setdefault(mod, []).append((file, lineno))
    for mod in sorted(by_module):
        sites = ", ".join(f"{f}:{ln}" for f, ln in by_module[mod][:3])
        more = f" (+{len(by_module[mod]) - 3} more)" if len(by_module[mod]) > 3 else ""
        print(f"  MISSING MODULE: {mod}\n    referenced at: {sites}{more}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
