"""附件类型指纹字典(EAI-CUSTOM,L2 指纹通道 spec 2026-11-04 §2.2):

engine/dicts/fingerprints.yaml:类型名 → 内容自证性特征关键词组。文件缺/坏/空 →
`{}`(卡片无关键词提示,模型纯语义判定——退化为弱而非坏);坏条目逐个丢弃。
mtime 缓存仿 tuning.py:每次读取 stat 文件,变更才重读(运维即改,热生效)。
"""

from __future__ import annotations

import threading
from pathlib import Path

import yaml

_FILE = Path(__file__).parent / "dicts" / "fingerprints.yaml"

_lock = threading.Lock()
_cache: tuple[float, dict[str, list[str]]] | None = None  # (mtime, 指纹表)


def _norm_table(data: object) -> dict[str, list[str]]:
    """校验:顶层 dict,键=非空字符串(strip),值=非空字符串列表;组内任一条目坏 → 整组
    丢弃(tuning._norm_groups 同规——半组静默保留会误导运维以为指纹完整);空组丢弃。"""
    if not isinstance(data, dict):
        return {}
    table: dict[str, list[str]] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if not isinstance(v, list) or not v:
            continue
        if not all(isinstance(s, str) and s.strip() for s in v):
            continue
        table[k.strip()] = [s.strip() for s in v]
    return table


def load() -> dict[str, list[str]]:
    global _cache
    try:
        mtime = _FILE.stat().st_mtime
    except OSError:
        with _lock:
            _cache = (0.0, {})
        return {}
    with _lock:
        if _cache is not None and _cache[0] == mtime:
            return _cache[1]
        table: dict[str, list[str]] = {}
        try:
            table = _norm_table(yaml.safe_load(_FILE.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError):
            pass  # 坏文件 → {} 兜底
        _cache = (mtime, table)
        return table
