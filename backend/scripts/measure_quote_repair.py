"""批卅 T3:真实任务摘录修复恢复率测量(用户规则④:先量后宣;EAI-CUSTOM 2026-11-18)。

用法(宿主机):
  1) docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -t -A -c \
       "select json_build_object('owner_id',owner_id,'task_id',id,'meta',engine_meta)::text \
        from bid_write_tasks where status='matrix_ready' and engine_meta::jsonb ? 'provenance' \
        order by created_at desc limit 1" > wt.json
  2) cd backend && PYTHONPATH=. uv run python scripts/measure_quote_repair.py <wt.json路径>
输出:遥测 stats + per-path(旧 verified→修复→新 verified)+ 矩阵 blocked 前后对比。
零 LLM、只读本地 raw 文件(parse.task_dir),不动 DB。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.extensions.bid_review import parse  # noqa: E402
from app.extensions.bid_review.engine.extract import verify_quotes  # noqa: E402
from app.extensions.bid_write.quote_repair import repair_quotes  # noqa: E402


def _blocked_count(fields: dict, fields_conf: dict, vmap: dict) -> int:
    """矩阵 _status_of 口径:not verified ∧ conf<0.6(含修复后矩阵行级联:列表路径整组)。"""
    n = 0
    for path, entry in fields_conf.items():
        if fields.get(path) is None:
            continue
        conf = entry.get("conf") if isinstance(entry, dict) else None
        if not vmap.get(path, False) and isinstance(conf, (int, float)) and conf < 0.6:
            n += 1
    return n


def main() -> None:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    meta = data["meta"]
    owner_id, task_id = data["owner_id"], data["task_id"]
    docs_meta = [e for e in (meta.get("docs") or []) if isinstance(e, dict)]
    docs = parse.docs_from_entries(owner_id, task_id, docs_meta)
    provenance = meta.get("provenance") or {}
    fields_conf = meta.get("fields_conf") or {}
    fields = meta.get("fields") or {}

    old_verified = verify_quotes(provenance, docs)
    stats = repair_quotes(provenance, docs)
    new_verified = verify_quotes(provenance, docs)

    print(f"task={task_id} docs={len(docs)} stats={stats}")
    fixed = 0
    unverified_total = 0
    for path in sorted(fields_conf):
        if path not in provenance:
            continue
        o, n = old_verified.get(path), new_verified.get(path)
        rep = bool((provenance.get(path) or {}).get("repaired"))
        if o is False:
            unverified_total += 1
        if o is False and n is True:
            fixed += 1
        mark = "FIXED" if rep else "    "
        print(f"{mark} {path}: {o} -> {n}")
    print(f"恢复率: {fixed}/{unverified_total} 条 unverified 被修复")
    print(
        f"矩阵 blocked(路径口径): "
        f"{_blocked_count(fields, fields_conf, old_verified)} -> "
        f"{_blocked_count(fields, fields_conf, new_verified)}"
    )


if __name__ == "__main__":
    main()
