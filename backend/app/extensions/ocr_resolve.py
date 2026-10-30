"""OCR 引擎公共解析(EAI-CUSTOM 2026-10-30,spec: bid-review evidence pipeline §3)。

cpa `_resolve_ocr_args` 的注册表解析段抽公共版:名字 → 注册表条目,
失效(builtin/空名/不在注册表/api_key 掩码/要素不全/注册表不可读)一律
回退 None(=内建)+ warning——「默认零变化 + 失败隔离」哲学与 cpa 逐字节同。
消费方:contract_price(经 argv 组装)、bid_review 解析层(直接用条目调服务)。
"""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 与 settings routers.OCR_KEY_MASK / contract_price._OCR_KEY_MASK 同值
OCR_KEY_MASK = "********"


async def load_ocr_services(db: AsyncSession) -> list[dict]:
    """system_config ocr_services KV → list[dict](空/坏 JSON → [],绝不抛)。"""
    try:
        from app.extensions.settings.service import SystemConfigService

        data = await SystemConfigService.get_all(db)
        raw = (data or {}).get("ocr_services") or ""
        parsed = json.loads(raw) if raw else []
        return parsed if isinstance(parsed, list) else []
    except Exception as exc:  # noqa: BLE001 — 注册表不可读时消费方回退内建
        logger.warning("OCR registry unreadable, fallback to builtin: %s", exc)
        return []


async def resolve_ocr_entry(db: AsyncSession, provider: str | None) -> dict | None:
    """注册表名 → 条目 {name, base_url, api_key, model};失效 → None(用内建)。

    builtin/空名 → None(静默,与 cpa 现行为一致);注册表无此名 / api_key 为
    掩码 / base_url|model 缺 → None + warning。
    """
    name = (provider or "").strip()
    if not name or name == "builtin":
        return None
    services = await load_ocr_services(db)
    entry = next(
        (s for s in services if isinstance(s, dict) and s.get("name") == name),
        None,
    )
    if not entry:
        logger.warning("OCR provider %r not in registry, fallback to builtin", name)
        return None
    base_url = str(entry.get("base_url") or "").strip()
    api_key = str(entry.get("api_key") or "").strip()
    model = str(entry.get("model") or "").strip()
    if not base_url or not model or api_key == OCR_KEY_MASK:
        logger.warning("OCR provider %r incomplete/masked key, fallback to builtin", name)
        return None
    return {"name": name, "base_url": base_url, "api_key": api_key, "model": model}


async def resolve_default_ocr_entry(db: AsyncSession) -> dict | None:
    """系统设置 default_ocr_engine → 注册表条目;空/解析失败 → None(内建)。

    bid_review 解析层的默认引擎选择入口(任务级 override 未来经参数传入)。
    """
    try:
        from app.extensions.settings.service import SystemConfigService

        data = await SystemConfigService.get_all(db)
        chosen = (data or {}).get("default_ocr_engine") or ""
    except Exception as exc:  # noqa: BLE001 — 设置不可读回退内建
        logger.warning("default_ocr_engine unreadable, fallback to builtin: %s", exc)
        return None
    return await resolve_ocr_entry(db, chosen)
