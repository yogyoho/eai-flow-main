"""cpa v3 M3: `_resolve_ocr_args` 优先级/掩码/回退(spec §3.3,镜像 llm_injection 测试模式)。

外部服务注册表存 system_config KV `ocr_services`;cpa config.json `ocr_provider`
选择;子进程 argv 注入 --ocr-*;失效回退内建(=[] 零行为变化)。
"""

import json

import pytest

from app.extensions.contract_price import service


def _svc(name="paddleocr-vl", base="http://192.168.2.38:8111/v1", key="sk-1", model="paddleocr-vl-1.6"):
    return {"name": name, "base_url": base, "api_key": key, "model": model}


def _write_cfg(tmp_path, monkeypatch, data):
    import app.extensions.contract_price.crud as crud

    path = tmp_path / "config.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(crud, "_config_path", lambda: str(path))


@pytest.fixture
def registry(monkeypatch):
    """SystemConfigService.get_all → 可控注册表。"""
    holder: dict = {"services": []}

    class FakeSvc:
        @staticmethod
        async def get_all(db):
            return (
                {"ocr_services": json.dumps(holder["services"], ensure_ascii=False)}
                if holder["services"]
                else {}
            )

    monkeypatch.setattr(
        "app.extensions.settings.service.SystemConfigService", FakeSvc
    )
    return holder


@pytest.mark.asyncio
async def test_no_provider_no_flags(tmp_path, monkeypatch, registry):
    _write_cfg(tmp_path, monkeypatch, {"ocr_provider": None})
    assert await service._resolve_ocr_args(None) == []


@pytest.mark.asyncio
async def test_builtin_explicit_no_flags(tmp_path, monkeypatch, registry):
    _write_cfg(tmp_path, monkeypatch, {"ocr_provider": "builtin"})
    registry["services"] = [_svc()]
    assert await service._resolve_ocr_args(None) == []


@pytest.mark.asyncio
async def test_provider_injected_as_argv(tmp_path, monkeypatch, registry):
    _write_cfg(tmp_path, monkeypatch, {"ocr_provider": "paddleocr-vl"})
    registry["services"] = [_svc()]
    assert await service._resolve_ocr_args(None) == [
        "--ocr-provider", "paddleocr-vl",
        "--ocr-backend", "openai-vision",
        "--ocr-base-url", "http://192.168.2.38:8111/v1",
        "--ocr-key", "sk-1",
        "--ocr-model", "paddleocr-vl-1.6",
    ]


@pytest.mark.asyncio
async def test_unknown_provider_falls_back(tmp_path, monkeypatch, registry):
    _write_cfg(tmp_path, monkeypatch, {"ocr_provider": "ghost"})
    registry["services"] = [_svc()]
    assert await service._resolve_ocr_args(None) == []


@pytest.mark.asyncio
async def test_masked_key_falls_back(tmp_path, monkeypatch, registry):
    # settings 侧只回掩码;gateway 读到掩码 = 未解析真值 → 回退内建
    _write_cfg(tmp_path, monkeypatch, {"ocr_provider": "paddleocr-vl"})
    registry["services"] = [_svc(key="********")]
    assert await service._resolve_ocr_args(None) == []


@pytest.mark.asyncio
async def test_override_wins_over_config(tmp_path, monkeypatch, registry):
    # 单文档重解析: 显式 override 优先于 config.json
    _write_cfg(tmp_path, monkeypatch, {"ocr_provider": None})
    registry["services"] = [_svc()]
    args = await service._resolve_ocr_args(None, "paddleocr-vl")
    assert args[0:2] == ["--ocr-provider", "paddleocr-vl"]


@pytest.mark.asyncio
async def test_registry_unreadable_falls_back(tmp_path, monkeypatch):
    async def boom(db):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "app.extensions.settings.service.SystemConfigService.get_all", boom
    )
    _write_cfg(tmp_path, monkeypatch, {"ocr_provider": "paddleocr-vl"})
    assert await service._resolve_ocr_args(None) == []
