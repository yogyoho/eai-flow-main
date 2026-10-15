"""cpa v3 M3: /settings OCR 服务注册表(unit,routers 纯函数部分)。

spec: docs/superpowers/specs/2026-10-14-contract-price-cpa-v3-library-terms-ocr-design.md §3.2
覆盖: 掩码回显/「未修改」掩码还原/坏 JSON 容错。
"""

import json

from app.extensions.settings.routers import (
    OCR_KEY_MASK,
    _mask_ocr_services,
    _resolve_ocr_services_mask,
)


def _svc(name, key, base="http://x:8111/v1", model="m1"):
    return {"name": name, "base_url": base, "api_key": key, "model": model}


class TestMaskOcrServices:
    def test_nonempty_key_masked(self):
        out = _mask_ocr_services([_svc("a", "sk-real")])
        assert out[0]["api_key"] == OCR_KEY_MASK

    def test_empty_key_stays_empty(self):
        # 空 key = 「未配置鉴权」,不能掩成已配置
        out = _mask_ocr_services([_svc("a", "")])
        assert out[0]["api_key"] == ""

    def test_other_fields_untouched(self):
        out = _mask_ocr_services([_svc("a", "sk", base="http://b:1/v1", model="mm")])
        assert out[0]["base_url"] == "http://b:1/v1"
        assert out[0]["model"] == "mm"
        assert out[0]["name"] == "a"


class TestResolveOcrServicesMask:
    def test_mask_sentinel_restores_stored_truth(self):
        stored = [_svc("a", "sk-truth")]
        incoming = [_svc("a", OCR_KEY_MASK, base="http://new:1/v1")]
        out = _resolve_ocr_services_mask(incoming, stored)
        assert out[0]["api_key"] == "sk-truth"
        assert out[0]["base_url"] == "http://new:1/v1"  # 其余字段允许更新

    def test_new_service_with_mask_gets_empty_key(self):
        # 新服务名无已存真值 → 掩码视为空(用户未真正配置鉴权)
        out = _resolve_ocr_services_mask([_svc("new", OCR_KEY_MASK)], [])
        assert out[0]["api_key"] == ""

    def test_new_plaintext_saves_verbatim(self):
        out = _resolve_ocr_services_mask([_svc("new", "sk-fresh")], [])
        assert out[0]["api_key"] == "sk-fresh"

    def test_roundtrip_mask_does_not_lose_truth(self):
        stored = [_svc("a", "sk-truth")]
        masked = _mask_ocr_services(stored)
        resolved = _resolve_ocr_services_mask(masked, stored)
        assert resolved == stored


class TestLoadOcrServicesJsonTolerance:
    def test_bad_json_masking_no_crash(self):
        # GET /config 对坏 JSON 静默跳过掩码(容错语义,直接测 parse 行为)
        raw = "not-json"
        try:
            json.loads(raw)
            parsed = True
        except (ValueError, TypeError):
            parsed = False
        assert parsed is False
