"""P2 LLM 兜底: run_pipeline_subprocess 从扩展配置读 LLM 三元组注入子进程
argv(缺省不传 = 层关闭,管线行为零变化;spec 2026-09-19 §3,计划 Task 7)。"""

import json


def _write_cfg(tmp_path, monkeypatch, data):
    import app.extensions.contract_price.crud as crud

    path = tmp_path / "config.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(crud, "_config_path", lambda: str(path))


def test_no_llm_config_no_flags(tmp_path, monkeypatch):
    _write_cfg(tmp_path, monkeypatch, {})
    from app.extensions.contract_price.service import _resolve_llm_args

    assert _resolve_llm_args() == []


def test_full_triple_passed_as_argv_with_env_key(tmp_path, monkeypatch):
    """三元组齐备 → 按固定顺序注入 argv;$ENV 形式的 key 运行时解析。"""
    _write_cfg(
        tmp_path,
        monkeypatch,
        {
            "llm_base_url": "http://llm.internal/v1",
            "llm_key": "$CPA_TEST_LLM_KEY",
            "llm_model": "m1",
        },
    )
    monkeypatch.setenv("CPA_TEST_LLM_KEY", "sk-live")
    from app.extensions.contract_price.service import _resolve_llm_args

    assert _resolve_llm_args() == [
        "--llm-base-url",
        "http://llm.internal/v1",
        "--llm-key",
        "sk-live",
        "--llm-model",
        "m1",
    ]


def test_partial_triple_off(tmp_path, monkeypatch):
    """任一要素缺失 → 不传(层关闭),避免半配置态产生不可达调用。"""
    _write_cfg(tmp_path, monkeypatch, {"llm_base_url": "http://x", "llm_model": "m"})
    from app.extensions.contract_price.service import _resolve_llm_args

    assert _resolve_llm_args() == []


def test_unresolved_env_var_off(tmp_path, monkeypatch):
    """$ENV 未设置 → 视同缺失 → 不传(fail-closed,不传裸 $VAR 给子进程)。"""
    _write_cfg(
        tmp_path,
        monkeypatch,
        {"llm_base_url": "http://x", "llm_key": "$CPA_MISSING_KEY_XYZ", "llm_model": "m"},
    )
    monkeypatch.delenv("CPA_MISSING_KEY_XYZ", raising=False)
    from app.extensions.contract_price.service import _resolve_llm_args

    assert _resolve_llm_args() == []


def test_config_read_failure_off(tmp_path, monkeypatch):
    """配置读取异常 → 不传(绝不阻塞管线触发)。"""
    import app.extensions.contract_price.crud as crud

    def boom():
        raise RuntimeError("disk gone")

    monkeypatch.setattr(crud, "load_config", boom)
    from app.extensions.contract_price.service import _resolve_llm_args

    assert _resolve_llm_args() == []


def test_run_pipeline_subprocess_wires_llm_args():
    from app.extensions.contract_price import service

    src = __import__("inspect").getsource(service.run_pipeline_subprocess)
    assert "_resolve_llm_args" in src


def test_llm_fields_survive_config_roundtrip(tmp_path, monkeypatch):
    """ConfigOut 新字段经 GET(load)/PUT(save) 往返持久化,不丢不损。"""
    _write_cfg(
        tmp_path,
        monkeypatch,
        {"llm_base_url": "http://x/v1", "llm_key": "$K", "llm_model": "m"},
    )
    from app.extensions.contract_price.crud import load_config, save_config

    cfg = load_config()
    assert cfg.llm_base_url == "http://x/v1"
    assert cfg.llm_key == "$K"
    assert cfg.llm_model == "m"
    saved = save_config(cfg)
    assert (saved.llm_base_url, saved.llm_key, saved.llm_model) == ("http://x/v1", "$K", "m")
    reloaded = load_config()
    assert reloaded.llm_key == "$K"


# --- review fix 2026-09-20: llm_key write-only(GET 掩码回显,PUT 掩码还原) ----


def test_get_response_masks_plaintext_key(tmp_path, monkeypatch):
    """GET 边界: 明文 key 只回掩码;序列化产物里不出现真值;其余字段原样。"""
    _write_cfg(
        tmp_path,
        monkeypatch,
        {"llm_base_url": "http://x/v1", "llm_key": "sk-plaintext", "llm_model": "m"},
    )
    from app.extensions.contract_price.crud import load_config, mask_llm_key
    from app.extensions.contract_price.schemas import LLM_KEY_MASK

    out = mask_llm_key(load_config())
    assert out.llm_key == LLM_KEY_MASK
    assert "sk-plaintext" not in out.model_dump_json()
    assert (out.llm_base_url, out.llm_model) == ("http://x/v1", "m")
    # 掩码只作用于响应副本: 底层配置真值不动(service 子进程注入仍可用)
    assert load_config().llm_key == "sk-plaintext"


def test_get_masks_env_form_too_and_unset_stays_unset(tmp_path, monkeypatch):
    """$ENV 形式同样视为敏感 → 掩码;未配置(None)保持 None 以区分未配置态。"""
    _write_cfg(tmp_path, monkeypatch, {"llm_base_url": "http://x/v1", "llm_key": "$SECRET_ENV", "llm_model": "m"})
    from app.extensions.contract_price.crud import load_config, mask_llm_key
    from app.extensions.contract_price.schemas import LLM_KEY_MASK

    assert mask_llm_key(load_config()).llm_key == LLM_KEY_MASK

    _write_cfg(tmp_path, monkeypatch, {})
    cfg = load_config()
    assert cfg.llm_key is None
    assert mask_llm_key(cfg).llm_key is None


def test_put_mask_sentinel_preserves_stored_key(tmp_path, monkeypatch):
    """PUT 边界: GET 的掩码被原样回传 = key 未修改,还原已存真值落盘。"""
    _write_cfg(
        tmp_path,
        monkeypatch,
        {"llm_base_url": "http://x/v1", "llm_key": "$REAL_ENV_KEY", "llm_model": "m"},
    )
    from app.extensions.contract_price.crud import load_config, resolve_llm_key_mask, save_config
    from app.extensions.contract_price.schemas import LLM_KEY_MASK, ConfigUpdate

    # 模拟前端: GET 掩码 → 整包回传 PUT
    body = ConfigUpdate(**{**load_config().model_dump(), "llm_key": LLM_KEY_MASK})
    saved = save_config(resolve_llm_key_mask(body))
    assert saved.llm_key == "$REAL_ENV_KEY"
    assert load_config().llm_key == "$REAL_ENV_KEY"  # 落盘不被掩码污染


def test_put_new_key_overrides_and_empty_clears(tmp_path, monkeypatch):
    """新明文/新 $ENV 直接写入;空串清除(≠掩码,不触发还原)。"""
    _write_cfg(tmp_path, monkeypatch, {"llm_key": "$OLD_KEY"})
    from app.extensions.contract_price.crud import load_config, resolve_llm_key_mask, save_config
    from app.extensions.contract_price.schemas import LLM_KEY_MASK, ConfigUpdate

    body = ConfigUpdate(**{**load_config().model_dump(), "llm_key": "sk-brand-new"})
    save_config(resolve_llm_key_mask(body))
    assert load_config().llm_key == "sk-brand-new"

    body2 = ConfigUpdate(**{**load_config().model_dump(), "llm_key": "$NEW_ENV"})
    save_config(resolve_llm_key_mask(body2))
    assert load_config().llm_key == "$NEW_ENV"

    body3 = ConfigUpdate(**{**load_config().model_dump(), "llm_key": ""})
    save_config(resolve_llm_key_mask(body3))
    assert load_config().llm_key == ""
    assert LLM_KEY_MASK != ""  # 掩码占位与清除语义不冲突


def test_put_response_masked_no_readback(tmp_path, monkeypatch):
    """PUT 响应同样 write-only: 掩码回传还原后若把真值吐回响应体,持 system:access
    的客户端 PUT 掩码即可读回明文 key(绕过 GET 掩码)。复验 2026-09-20 锁回归。"""
    _write_cfg(tmp_path, monkeypatch, {"llm_base_url": "http://x/v1", "llm_key": "sk-live-secret", "llm_model": "m"})
    from app.extensions.contract_price.crud import load_config, mask_llm_key, resolve_llm_key_mask, save_config
    from app.extensions.contract_price.schemas import LLM_KEY_MASK, ConfigUpdate

    put_body = ConfigUpdate(**mask_llm_key(load_config()).model_dump())
    response_cfg = mask_llm_key(save_config(resolve_llm_key_mask(put_body)))  # 复刻 update_config 返回路径
    assert response_cfg.llm_key == LLM_KEY_MASK
    assert "sk-live-secret" not in response_cfg.model_dump_json()


def test_config_routers_wire_mask_on_both_directions():
    """路由接线锚: GET 响应过 mask_llm_key;PUT 落盘前 resolve、响应同样过 mask。"""
    import inspect

    from app.extensions.contract_price import routers

    assert "mask_llm_key" in inspect.getsource(routers.get_config)
    put_src = inspect.getsource(routers.update_config)
    assert "resolve_llm_key_mask" in put_src
    assert "mask_llm_key" in put_src


def test_full_roundtrip_masked_get_then_put_keeps_secret(tmp_path, monkeypatch):
    """端到端: 存真值 → GET 掩码 → PUT 掩码 → 重新 load 仍是真值(往返不损)。"""
    _write_cfg(
        tmp_path,
        monkeypatch,
        {"llm_base_url": "http://llm.internal/v1", "llm_key": "sk-live-secret", "llm_model": "m1"},
    )
    from app.extensions.contract_price.crud import load_config, mask_llm_key, resolve_llm_key_mask, save_config
    from app.extensions.contract_price.schemas import ConfigUpdate

    masked_get = mask_llm_key(load_config())
    put_body = ConfigUpdate(**masked_get.model_dump())
    save_config(resolve_llm_key_mask(put_body))
    assert load_config().llm_key == "sk-live-secret"
    # 子进程注入仍解析真值(argv: --llm-base-url url --llm-key key --llm-model model)
    from app.extensions.contract_price.service import _resolve_llm_args

    args = _resolve_llm_args()
    assert args[args.index("--llm-key") + 1] == "sk-live-secret"
