#!/usr/bin/env python3
"""投标样例台账种子灌入（EAI-CUSTOM: bug-3109 v4 投标资料管理 样例台账 MVP）。

读 bank_compile 产出的 registration.json（{"items": [{title, source_path, file_hash,
industry?, project_category?, ...}]}），经 SampleService.bulk 按 file_hash 幂等入库
bid_samples 表：已存在=skipped，新=created，重复运行零副作用。

会话获取方式与 commit 语义逐字镜像 scripts/eia_seed_samples.py：
init_engine() → get_db_context()（正常退出即 commit）→ close_db()。

Run（host 或 gateway 容器内）:
    cd backend && PYTHONPATH=. uv run python scripts/bid_seed_samples.py --registration <path>
    docker exec deer-flow-gateway python /app/backend/scripts/bid_seed_samples.py --registration <path>
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extensions.bid_materials.service import SampleService
from app.extensions.database import close_db, get_db_context, init_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bid-seed-samples")


async def seed(registration_path: str) -> dict:
    items = json.loads(Path(registration_path).read_text(encoding="utf-8"))["items"]
    async with get_db_context() as db:  # commit 归 get_db_context（eia_seed_samples 先例）
        result = await SampleService(db).bulk(items)
    return result


async def _main(registration_path: str) -> None:
    await init_engine()
    try:
        result = await seed(registration_path)
        logger.info("bid_samples seed done: created=%d skipped=%d", result["created"], result["skipped"])
        print(json.dumps({"command": "bid_seed_samples", **result}, ensure_ascii=False))
    finally:
        await close_db()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="投标样例台账种子: registration.json → bid_samples 幂等入库")
    ap.add_argument("--registration", required=True, help="bank_compile 产出的 registration.json 路径")
    args = ap.parse_args()
    asyncio.run(_main(args.registration))
