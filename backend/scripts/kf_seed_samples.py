#!/usr/bin/env python3
"""样例库种子数据灌入（EAI-CUSTOM: coal-eia-report v2 BS3 样例库 MVP）。

把既有 52 文件台账的 25 独立作品 + 3 份露天 txt 增补 + 1 条加密片段
（共 29 条，data/kf_samples_seed.json）灌入 kf_samples 表。

幂等：按 file_hash upsert，重复运行只做覆盖更新，不产生重复行。
可重复执行（gateway 重启/换库后重灌即可恢复台账）。

Run（host 或 gateway 容器内）:
    cd backend && PYTHONPATH=. uv run python scripts/kf_seed_samples.py
    docker exec deer-flow-gateway python /app/backend/scripts/kf_seed_samples.py
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extensions.database import close_db, get_db_context, init_engine
from app.extensions.knowledge_factory.sample_service import SampleService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("kf-seed-samples")

SEED_PATH = Path(__file__).resolve().parent.parent / "app" / "extensions" / "knowledge_factory" / "data" / "kf_samples_seed.json"


async def seed() -> dict:
    payload = SampleService.make_bulk_payload(json.loads(SEED_PATH.read_text(encoding="utf-8"))["items"])
    async with get_db_context() as db:
        result = await SampleService.bulk_import(db, payload)
    return result


async def _main() -> None:
    await init_engine()
    try:
        result = await seed()
        logger.info("kf_samples seed done: created=%d updated=%d total=%d", result["created"], result["updated"], result["total"])
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(_main())
