"""bid_review 引擎可调参数(EAI-CUSTOM,L2 调参外置 spec 2026-11-03 §1):

engine/dicts/tuning.yaml 覆盖默认值;文件缺失/坏 yaml/键值类型错/超范围 →
逐键回落默认,行为零变。mtime 缓存:每次读取 stat 文件,变更才重读
(bind-mount 热编辑生效,命中零盘 IO)。同文件 synonyms: 节留给同义词外置切片。
"""

from __future__ import annotations

import threading
from pathlib import Path

import yaml

_FILE = Path(__file__).parent / "dicts" / "tuning.yaml"

DEFAULTS: dict[str, float | int] = {
    "near_miss_gate": 0.75,
    "evidence_min_sim": 0.30,
    "evidence_top_k": 3,
}

_RANGE: dict[str, tuple[float, float]] = {
    "near_miss_gate": (0.0, 1.0),
    "evidence_min_sim": (0.0, 1.0),
    "evidence_top_k": (1.0, 10.0),
}

_lock = threading.Lock()
_cache: tuple[float, dict[str, float | int]] | None = None  # (mtime, merged)


def _load() -> dict[str, float | int]:
    global _cache
    try:
        mtime = _FILE.stat().st_mtime
    except OSError:
        with _lock:
            _cache = (0.0, dict(DEFAULTS))
        return _cache[1]
    with _lock:
        if _cache is not None and _cache[0] == mtime:
            return _cache[1]
        merged: dict[str, float | int] = dict(DEFAULTS)
        try:
            data = yaml.safe_load(_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, dv in DEFAULTS.items():
                    v = data.get(key)
                    lo, hi = _RANGE[key]
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= float(v) <= hi:
                        merged[key] = dv.__class__(v)
        except (OSError, yaml.YAMLError, ValueError):
            pass  # 坏文件 → 全量默认兜底
        _cache = (mtime, merged)
        return merged


def get(key: str) -> float | int:
    return _load()[key]
