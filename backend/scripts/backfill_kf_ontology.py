"""回填 kf_samples.outline_json.ontology——B2 (b') 产物消费路径的存量使能器.

EAI-CUSTOM(2026-10-01): 设计 docs/designs/2026-10-01-ontostudio-ux-governance.md §B2。
背景：存量样例的 outline 由旧版提取流水线产出，无 ontology key（实测 29 样例 0 命中）——
ontostudio 抽取任务 API 消费 outline_json.ontology，无它则全部 422。
本脚本对每个有 outline 的样例：读源文本 → extract_ontology（确定性正则，与
eia-batch 生产线同函数）→ jsonb 合并回 outline_json。已在 gateway 容器验证。

运行（gateway 容器内）:
  docker cp backend/scripts/backfill_kf_ontology.py deer-flow-gateway:/tmp/
  docker exec deer-flow-gateway sh -c 'PYTHONPATH=/app/backend /app/backend/.venv/bin/python /tmp/backfill_kf_ontology.py'
可选 --force 覆盖已有 ontology；--limit N 限量试跑。
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.extensions.database import get_session_factory, init_engine
from app.extensions.eia_samples.extract import extract_ontology, read_source_text
from app.extensions.eia_samples.models import KFSample


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="覆盖已有 ontology")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    await init_engine()  # 脚本直跑不走 gateway lifespan，工厂需显式初始化
    sf = get_session_factory()
    ok = skip = empty = err = 0
    async with sf() as db:
        rows = (
            (await db.execute(select(KFSample).where(KFSample.outline_json.is_not(None)).order_by(KFSample.created_at)))
            .scalars()
            .all()
        )
        if args.limit:
            rows = rows[: args.limit]
        print(f"候选 {len(rows)} 份样例")
        for s in rows:
            onto = (s.outline_json or {}).get("ontology")
            if onto and onto.get("entities") and not args.force:
                skip += 1
                continue
            try:
                text, _kind = read_source_text(s.source_path)
                result = extract_ontology(text)
            except Exception as e:  # noqa: BLE001——单样例失败不阻断批量
                print(f"ERR  {str(s.id)[:8]} {s.title[:28]}: {e}")
                err += 1
                continue
            if not result.get("entities"):
                print(f"EMPTY {str(s.id)[:8]} {s.title[:28]}: 正则零命中")
                empty += 1
                continue
            s.outline_json = {**(s.outline_json or {}), "ontology": result}
            await db.commit()
            ok += 1
            print(f"OK   {str(s.id)[:8]} {s.title[:28]} entities={len(result['entities'])} relations={len(result.get('relations', []))}")
    print(f"\n回填完成: ok={ok} skip={skip} empty={empty} err={err}")
    return 0


if __name__ == "__main__":
    asyncio.run(main())
