#!/usr/bin/env python3
"""投标样例台账种子灌入（EAI-CUSTOM: bug-3109 v4 投标资料管理 样例台账 MVP）。

读 bank_compile 产出的 registration.json，经 SampleBulkImportRequest 校验（与
POST /samples/bulk 同一契约：file_hash 恰 64 字符、1-500 条上限、未知键忽略）后走
SampleService.bulk 按 file_hash 幂等入库 bid_samples 表：已存在=skipped，新=created，
重复运行零副作用。

会话获取方式镜像 scripts/eia_seed_samples.py：
init_engine() → get_db_context() → close_db()。

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

from app.extensions.bid_materials.schemas import SampleBulkImportRequest
from app.extensions.bid_materials.service import SampleService
from app.extensions.database import close_db, get_db_context, init_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bid-seed-samples")


async def seed(registration_path: str) -> dict:
    payload = SampleBulkImportRequest.model_validate(json.loads(Path(registration_path).read_text(encoding="utf-8")))
    async with get_db_context() as db:  # bulk 只 flush，commit 归 get_db_context（本扩展路由层同约定；eia 先例为 service 内 commit）
        result = await SampleService(db).bulk([item.model_dump() for item in payload.items])
    # 输出对齐 SampleBulkImportResponse 三元组（updated 恒 0: 幂等语义只分新/跳过）+ skipped 供人读
    return {**result, "updated": 0, "total": len(payload.items)}


async def _main(registration_path: str) -> None:
    await init_engine()
    try:
        result = await seed(registration_path)
        logger.info(
            "bid_samples seed done: created=%d skipped=%d updated=%d total=%d",
            result["created"],
            result["skipped"],
            result["updated"],
            result["total"],
        )
        print(json.dumps({"script": "bid_seed_samples", **result}, ensure_ascii=False))
    finally:
        await close_db()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="投标样例台账种子: registration.json → bid_samples 幂等入库")
    ap.add_argument("--registration", required=True, help="bank_compile 产出的 registration.json 路径")
    args = ap.parse_args()
    asyncio.run(_main(args.registration))
