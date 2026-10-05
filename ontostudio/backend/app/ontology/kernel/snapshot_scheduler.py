"""每日快照调度（G1/B6）——lifespan 挂后台任务, 服务重启/停机自愈.

- 每日 06:00（业务时区 Asia/Shanghai +08:00，与 ingest.py _CST 同约定）自动 TriG
  全图快照（含派生）；启动/整点自醒时若当日尚无快照则立即补一次（重启/停机跨过
  06:00 不丢当日快照）。
- 保留 30 天滚动清理（pre-restore-* 回滚点不受清理影响）。
- 全程异常自吞只留日志——快照失败次日再试, 绝不拖垮服务。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.ontology.kernel.service import get_kernel

logger = logging.getLogger("uvicorn.error")  # uvicorn 配置了 handler, 模块 INFO 才可见

_SNAPSHOT_HOUR = 6  # 业务时区（+08:00）小时
_RETENTION_DAYS = 30
_CST = timezone(timedelta(hours=8))


def _cst_now() -> datetime:
    return datetime.now(_CST)


async def snapshot_daily_loop() -> None:
    """每小时醒一次：业务日 06:00 后当日尚无快照即补（幂等），顺带滚动清理。"""
    logger.info("每日快照调度启动（每日 %02d:00 +08:00, 保留 %d 天）", _SNAPSHOT_HOUR, _RETENTION_DAYS)
    while True:
        try:
            kernel = get_kernel()
            snaps = kernel.list_snapshots()
            today = _cst_now().strftime("%Y%m%d")
            has_today = any(today in s["file"] for s in snaps)
            now = _cst_now()
            if now.hour >= _SNAPSHOT_HOUR and not has_today:
                kernel.create_snapshot()
                removed = kernel.prune_snapshots(keep_days=_RETENTION_DAYS)
                logger.info("每日快照完成（清理 %s 个过期）", removed.get("removed", 0))
        except Exception as exc:  # noqa: BLE001 - 快照失败只留日志, 绝不拖垮服务
            logger.warning("每日快照失败（下次整点后重试）: %s", exc)
        now = datetime.now(_CST)
        nxt = (now + timedelta(hours=1)).replace(minute=1, second=0, microsecond=0)
        await asyncio.sleep(max(1.0, (nxt - now).total_seconds()))
