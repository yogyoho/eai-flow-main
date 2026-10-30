"""公共 OCR 引擎解析(EAI-CUSTOM 2026-10-30): resolve_ocr_entry / resolve_default_ocr_entry。

镜像 test_contract_price_ocr_provider 模式——cpa `_resolve_ocr_args` 抽公共版后,
bid_review 解析层与 cpa 同源;三态(命中/builtin/失效回退)+ 系统默认读取。
"""

import json

import pytest

from app.extensions import ocr_resolve


def _svc(name="paddleocr-vl", base="http://192.168.2.38:8111/v1", key="sk-1", model="paddleocr-vl-1.6"):
    return {"name": name, "base_url": base, "api_key": key, "model": model}


@pytest.fixture
def registry(monkeypatch):
    """SystemConfigService.get_all → 可控 {ocr_services, default_ocr_engine}。"""
    holder: dict = {"services": [], "default": ""}

    class FakeSvc:
        @staticmethod
        async def get_all(db):
            out: dict = {}
            if holder["services"]:
                out["ocr_services"] = json.dumps(holder["services"], ensure_ascii=False)
            if holder["default"]:
                out["default_ocr_engine"] = holder["default"]
            return out

    monkeypatch.setattr(
        "app.extensions.settings.service.SystemConfigService", FakeSvc
    )
    return holder


@pytest.mark.asyncio
async def test_entry_hit(registry):
    registry["services"] = [_svc()]
    entry = await ocr_resolve.resolve_ocr_entry(None, "paddleocr-vl")
    assert entry == _svc()


@pytest.mark.asyncio
async def test_builtin_and_empty_are_silent_none(registry):
    registry["services"] = [_svc()]
    assert await ocr_resolve.resolve_ocr_entry(None, "builtin") is None
    assert await ocr_resolve.resolve_ocr_entry(None, "") is None
    assert await ocr_resolve.resolve_ocr_entry(None, None) is None


@pytest.mark.asyncio
async def test_unknown_and_masked_and_incomplete_fall_back(registry):
    registry["services"] = [_svc()]
    assert await ocr_resolve.resolve_ocr_entry(None, "ghost") is None
    registry["services"] = [_svc(key="********")]
    assert await ocr_resolve.resolve_ocr_entry(None, "paddleocr-vl") is None
    registry["services"] = [_svc(model="")]
    assert await ocr_resolve.resolve_ocr_entry(None, "paddleocr-vl") is None


@pytest.mark.asyncio
async def test_registry_unreadable_falls_back(monkeypatch):
    async def boom(db):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "app.extensions.settings.service.SystemConfigService.get_all", boom
    )
    assert await ocr_resolve.resolve_ocr_entry(None, "paddleocr-vl") is None
    assert await ocr_resolve.resolve_default_ocr_entry(None) is None


@pytest.mark.asyncio
async def test_default_engine_resolution(registry):
    # 系统默认 = builtin → None(内建);= 注册表名 → 条目
    registry["services"] = [_svc()]
    registry["default"] = "builtin"
    assert await ocr_resolve.resolve_default_ocr_entry(None) is None
    registry["default"] = "paddleocr-vl"
    assert (await ocr_resolve.resolve_default_ocr_entry(None))["name"] == "paddleocr-vl"


@pytest.mark.asyncio
async def test_default_unset_falls_back_to_builtin(registry):
    # 未设置 default_ocr_engine(存量库)→ 内建,零行为变化
    registry["services"] = [_svc()]
    assert await ocr_resolve.resolve_default_ocr_entry(None) is None
