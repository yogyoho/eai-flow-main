"""bid_review 引擎可调参数(EAI-CUSTOM,L2 调参外置 spec 2026-11-03 §1):

engine/dicts/tuning.yaml 覆盖默认值;数字键文件缺失/坏 yaml/类型错/超范围 →
逐键回落默认,行为零变;synonyms: 节(L2 同义词外置 spec 2026-11-03)逐组校验
丢弃坏组,节坏回落默认两组。mtime 缓存:每次读取 stat 文件,变更才重读
(bind-mount 热编辑生效,命中零盘 IO);一次解析产出数字键 dict + 同义词组双产物。
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

# 同义词组模块真源(L2 同义词外置 spec 2026-11-03 §3):缺文件/节坏=现状行为。
# 每组首元素=规范形;方向不明变体(副本/复印件/回执/正本)不入表——防静默升级。
_DEFAULT_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("营业执照", "企业法人营业执照"),
    ("审计报告", "年度审计报告"),
)

_RANGE: dict[str, tuple[float, float]] = {
    "near_miss_gate": (0.0, 1.0),
    "evidence_min_sim": (0.0, 1.0),
    "evidence_top_k": (1.0, 10.0),
}

_lock = threading.Lock()
_cache: tuple[float, dict[str, float | int], tuple[tuple[str, ...], ...]] | None = None  # (mtime, 数字键, 同义词组)


def _norm_groups(data: object) -> tuple[tuple[str, ...], ...] | None:
    """synonyms: 节校验(L2 同义词外置 spec 2026-11-03 §2):组=≥2 个非空字符串
    的列表(首=规范形,入组前 strip);坏组逐个丢弃;全坏/节非列表 → None(回落默认)。"""
    if not isinstance(data, list):
        return None
    groups: list[tuple[str, ...]] = []
    for g in data:
        if not isinstance(g, list) or len(g) < 2:
            continue
        if all(isinstance(s, str) and s.strip() for s in g):
            groups.append(tuple(s.strip() for s in g))
    return tuple(groups) if groups else None


def _load() -> tuple[dict[str, float | int], tuple[tuple[str, ...], ...]]:
    global _cache
    try:
        mtime = _FILE.stat().st_mtime
    except OSError:
        with _lock:
            _cache = (0.0, dict(DEFAULTS), _DEFAULT_SYNONYM_GROUPS)
        return _cache[1], _cache[2]
    with _lock:
        if _cache is not None and _cache[0] == mtime:
            return _cache[1], _cache[2]
        merged: dict[str, float | int] = dict(DEFAULTS)
        groups = _DEFAULT_SYNONYM_GROUPS
        try:
            data = yaml.safe_load(_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, dv in DEFAULTS.items():
                    v = data.get(key)
                    lo, hi = _RANGE[key]
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= float(v) <= hi:
                        merged[key] = dv.__class__(v)
                raw_syn = data.get("synonyms")
                if raw_syn is not None:
                    g = _norm_groups(raw_syn)
                    if g is not None:
                        groups = g
        except (OSError, yaml.YAMLError, ValueError):
            pass  # 坏文件 → 全量默认兜底
        _cache = (mtime, merged, groups)
        return merged, groups


def get(key: str) -> float | int:
    return _load()[0][key]


def synonym_groups() -> tuple[tuple[str, ...], ...]:
    return _load()[1]
