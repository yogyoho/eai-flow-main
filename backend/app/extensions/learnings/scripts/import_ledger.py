"""P0 markdown 账本 -> P1 SQL 一次性导入(D15 硬切换用; 幂等).

用法(容器内):
    cd /app/backend && .venv/bin/python -m app.extensions.learnings.scripts.import_ledger \
        --user-id <uuid> --ledger <path/to/learnings-ledger SKILL.md> [--dry-run]

- 解析正典条目格式(`### L-xxx | kind | key | status:... | count:N` 块)
- (user_id, pattern_key) 已存在且 count >= 账本 count -> 跳过(幂等重跑安全)
- resolved 条目按账本状态落库, 不触发晋升
兼作 P0 条目格式的解析契约测试样本(格式漂移在此先失败)。
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_ENTRY_RE = re.compile(
    r"^### (?P<id>L-\d+) \| (?P<kind>\w+) \| (?P<key>[a-z0-9.-]+) \| status:(?P<status>[\w]+) \| count:(?P<count>\d+)\s*$",
    re.MULTILINE,
)
_FIELD_RE = re.compile(r"^(summary|evidence|first|last|threads|action|skill):\s*(.*)$")


def parse_ledger(text: str) -> list[dict]:
    """正典格式解析(纯函数, 测试可直接调用)."""
    entries: list[dict] = []
    matches = list(_ENTRY_RE.finditer(text))
    for i, m in enumerate(matches):
        body = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        fields: dict[str, str] = {}
        for line in body.splitlines():
            # 组合行支持: first/last/threads 共写一行, 用 " | " 分段逐段匹配
            for segment in line.strip().split("|"):
                fm = _FIELD_RE.match(segment.strip())
                if fm:
                    fields[fm.group(1)] = fm.group(2).strip()
        first = _parse_date(fields.get("first"))
        last = _parse_date(fields.get("last")) or first
        entries.append(
            {
                "legacy_id": m.group("id"),
                "kind": m.group("kind"),
                "pattern_key": m.group("key"),
                "status": m.group("status"),
                "count": int(m.group("count")),
                "summary": fields.get("summary", "")[:200],
                "details": fields.get("evidence", "")[:2000],
                "suggested_action": fields.get("action", "")[:1000],
                "threads": [t for t in re.split(r"[,\s]+", fields.get("threads", "")) if t],
                "first": first,
                "last": last,
                "promoted_skill": fields.get("skill"),
            }
        )
    return entries


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw.strip()[:19], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


async def import_entries(user_id: str, entries: list[dict], dry_run: bool = False) -> dict:
    from sqlalchemy import select

    from app.extensions.database import get_db_context
    from app.extensions.learnings.models import AgentLearning
    from app.extensions.learnings.service import ensure_ready

    await ensure_ready()
    inserted = skipped = 0
    async with get_db_context() as db:
        existing = (
            await db.execute(select(AgentLearning).where(AgentLearning.user_id == user_id))
        ).scalars().all()
        by_key = {row.pattern_key: row for row in existing}
        for e in entries:
            row = by_key.get(e["pattern_key"])
            if row is not None and row.recurrence_count >= e["count"]:
                skipped += 1
                continue
            if dry_run:
                inserted += 1
                continue
            area, _, symptom = e["pattern_key"].partition(".")
            threads = [t[:16] for t in e["threads"]] or []
            if row is not None:
                # 账本 count 更高 -> 以账本为准(单向升级, 不降级)
                row.recurrence_count = max(row.recurrence_count, e["count"])
                row.status = e["status"] if row.status == "pending" else row.status
                continue
            db.add(
                AgentLearning(
                    user_id=user_id,
                    kind=e["kind"] if e["kind"] in ("error", "correction", "knowledge_gap", "best_practice", "feature_request") else "error",
                    area=area or "runtime",
                    symptom=symptom or "failure",
                    pattern_key=e["pattern_key"],
                    summary=e["summary"] or e["legacy_id"],
                    details=e["details"],
                    suggested_action=e["suggested_action"],
                    status=e["status"] if e["status"] in ("pending", "resolved", "dismissed", "promoted_to_skill") else "pending",
                    recurrence_count=max(1, e["count"]),
                    first_seen_at=e["first"] or datetime.now(UTC),
                    last_seen_at=e["last"] or datetime.now(UTC),
                    distinct_thread_count=max(1, len(set(threads))),
                    source_thread_ids=",".join(threads)[:1000],
                    source="agent",
                    promoted_skill=e["promoted_skill"],
                )
            )
            inserted += 1
        if not dry_run:
            await db.commit()
    return {"inserted": inserted, "skipped": skipped, "parsed": len(entries)}


def main() -> int:
    parser = argparse.ArgumentParser(description="P0 ledger -> P1 SQL importer (idempotent)")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--ledger", required=True, help="learnings-ledger SKILL.md 路径")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    text = Path(args.ledger).read_text(encoding="utf-8")
    entries = parse_ledger(text)
    if not entries:
        print("no entries parsed — 格式可能漂移(正典 schema 见设计文档)", file=sys.stderr)
        return 1
    result = asyncio.run(import_entries(args.user_id, entries, dry_run=args.dry_run))
    print(f"parsed={result['parsed']} inserted={result['inserted']} skipped={result['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
