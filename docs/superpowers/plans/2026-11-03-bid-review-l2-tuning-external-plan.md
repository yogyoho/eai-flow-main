# L2 引擎调参外置 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans（本切片控制器 inline 执行,429 配额裁决见 spec §6）。步骤用 `- [ ]` 勾选。
> spec: `docs/superpowers/specs/2026-11-03-bid-review-l2-tuning-external-design.md`

**Goal:** bid_review 引擎三调参（near_miss_gate/evidence_min_sim/evidence_top_k）外置 `engine/dicts/tuning.yaml`,mtime 缓存 loader,缺文件/坏值逐键回落默认,行为零变。

**Architecture:** `engine/tuning.py`（DEFAULTS+范围表+mtime 缓存）→ attachments.py 三读点接线,模块常量 NEAR_MISS_GATE 退役。

**Tech Stack:** Python 3.12/PyYAML/pytest。

---

### Task 1: 文档（spec+plan 本 commit）

- [x] spec + plan 落盘提交。

### Task 2: loader + yaml + 接线 + 测试(TDD)

**Files:**
- Create: `backend/app/extensions/bid_review/engine/dicts/tuning.yaml`
- Create: `backend/app/extensions/bid_review/engine/tuning.py`
- Create: `backend/tests/test_bid_review_tuning.py`
- Modify: `backend/app/extensions/bid_review/engine/attachments.py`(:40 常量退役/:60 两参/:76/:171 门)
- Modify: `backend/tests/test_bid_review_attachments.py`(:346 seam 迁移)

- [x] **Step 2.1: 先写测试** `backend/tests/test_bid_review_tuning.py`

```python
"""tuning loader 单测(L2 调参外置 spec 2026-11-03 §4)。seam=monkeypatch _FILE+_cache。"""

from pathlib import Path

import pytest

from app.extensions.bid_review.engine import tuning as tun


@pytest.fixture()
def isolated_tuning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """指向不存在路径 + 清缓存 → 每测全默认起点。"""
    monkeypatch.setattr(tun, "_FILE", tmp_path / "tuning.yaml")
    monkeypatch.setattr(tun, "_cache", None)
    return tmp_path / "tuning.yaml"


def test_defaults_when_file_missing(isolated_tuning: Path) -> None:
    assert tun.get("near_miss_gate") == 0.75
    assert tun.get("evidence_min_sim") == 0.30
    assert tun.get("evidence_top_k") == 3


def test_override_applied(isolated_tuning: Path) -> None:
    isolated_tuning.write_text(
        "near_miss_gate: 0.9\nevidence_min_sim: 0.5\nevidence_top_k: 5\n",
        encoding="utf-8",
    )
    assert tun.get("near_miss_gate") == 0.9
    assert tun.get("evidence_min_sim") == 0.5
    assert tun.get("evidence_top_k") == 5  # int 键收 int


def test_invalid_values_fall_back_per_key(isolated_tuning: Path) -> None:
    isolated_tuning.write_text(
        'near_miss_gate: "high"\nevidence_min_sim: 7.0\nevidence_top_k: 0\n',
        encoding="utf-8",
    )
    assert tun.get("near_miss_gate") == 0.75  # 类型错
    assert tun.get("evidence_min_sim") == 0.30  # 超上界
    assert tun.get("evidence_top_k") == 3  # 超下界


def test_bad_yaml_falls_back(isolated_tuning: Path) -> None:
    isolated_tuning.write_text("{oops", encoding="utf-8")
    assert tun.get("near_miss_gate") == 0.75
    assert tun.get("evidence_top_k") == 3


def test_bool_rejected(isolated_tuning: Path) -> None:
    isolated_tuning.write_text("evidence_top_k: true\n", encoding="utf-8")
    assert tun.get("evidence_top_k") == 3  # bool 是 int 子类,显式拒
```

- [x] **Step 2.2: 实现 loader** `backend/app/extensions/bid_review/engine/tuning.py`

```python
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
                    if (
                        isinstance(v, (int, float))
                        and not isinstance(v, bool)
                        and lo <= float(v) <= hi
                    ):
                        merged[key] = dv.__class__(v)
        except (OSError, yaml.YAMLError, ValueError):
            pass  # 坏文件 → 全量默认兜底
        _cache = (mtime, merged)
        return merged


def get(key: str) -> float | int:
    return _load()[key]
```

- [x] **Step 2.3: 验红→验绿** 先跑测试(模块不存在收集失败=红)→落 loader→`PYTHONPATH=. uv run pytest tests/test_bid_review_tuning.py -v` 5 passed。

- [x] **Step 2.4: yaml 默认文件** `engine/dicts/tuning.yaml`

```yaml
# bid_review 引擎调参(L2 调参外置 spec 2026-11-03 §2;默认值=引擎现状,改此文件即生效,
# gateway 进程 mtime 缓存热感知;非法值逐键回落默认)。synonyms: 节留给同义词外置切片。
near_miss_gate: 0.75      # 近似门:池内 sim≥此值 → UNKNOWN(near_miss)
evidence_min_sim: 0.30    # 负证据 closest 滤噪下限
evidence_top_k: 3         # closest 最多条数
```

- [x] **Step 2.5: attachments.py 接线**——import 块加 `from . import tuning`;:40 `NEAR_MISS_GATE = 0.75` 删除(常量退役);:60 滤噪+截断改:

```python
        "closest": [
            {"no": str(p.get("no") or ""), "name": str(p.get("name") or ""), "sim": round(s, 4)}
            for s, p in cands[: int(tuning.get("evidence_top_k"))]
            if s >= float(tuning.get("evidence_min_sim"))
        ],
```

:76 与 :171 门判定改 `if cands and cands[0][0] >= float(tuning.get("near_miss_gate")):`(:171 行尾注释「门判定用 raw ratio,与平件门同规」保留);:56/:162/:187 文档串中 NEAR_MISS_GATE 措辞改 `near_miss_gate(tuning)`;相关行加 EAI-CUSTOM 注释引用 spec 日期+§。

- [x] **Step 2.6: :346 seam 迁移** `backend/tests/test_bid_review_attachments.py`——原 `monkeypatch.setattr(att, "NEAR_MISS_GATE", 0.90)` 改:

```python
    tuning_yaml = tmp_path / "tuning.yaml"
    tuning_yaml.write_text("near_miss_gate: 0.90\n", encoding="utf-8")
    monkeypatch.setattr(tun, "_FILE", tuning_yaml)
    monkeypatch.setattr(tun, "_cache", None)
```

(测试文件头部补 `from app.extensions.bid_review.engine import tuning as tun`;docstring 同步措辞;若该测试函数无 tmp_path 参数则补 fixture 参数。)

- [x] **Step 2.7: 全绿** `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_tuning.py tests/test_bid_review_attachments.py tests/test_bid_review_rule_runner.py -v` 全过;tuning 5 新 + attachments 40(1 迁移)+ rule_runner 23。

- [x] **Step 2.8: golden CLI 零翻红** golden 跑批 52/52 exit 0(默认零翻红;命令同前切片)。

- [x] **Step 2.9: ruff + commit** `cd backend && uv run ruff check app/extensions/bid_review/engine/tuning.py app/extensions/bid_review/engine/attachments.py tests/test_bid_review_tuning.py tests/test_bid_review_attachments.py && uv run ruff format --check <同四文件>`;commit(显式路径):

```bash
git add backend/app/extensions/bid_review/engine/tuning.py backend/app/extensions/bid_review/engine/dicts/tuning.yaml backend/app/extensions/bid_review/engine/attachments.py backend/tests/test_bid_review_tuning.py backend/tests/test_bid_review_attachments.py
git commit -m "feat(bid-review): L2-tuning① 引擎调参外置——engine/dicts/tuning.yaml+near_miss_gate/evidence_min_sim/evidence_top_k 三键;mtime 缓存 loader(缺文件/坏yaml/超范围逐键回落默认,bool 显式拒);attachments 三读点接线 NEAR_MISS_GATE 常量退役;:346 seam 迁移真 loader 端到端;tuning 5 新测;默认零变(golden 52/52)"
```

### Task 3: 全量验证收尾

- [x] **Step 3.1**: bid_review 全家 pytest(基线 368 passed/6 skipped → +5=373/6)。
- [x] **Step 3.2**: 门移位演示数字记录(gate 0.90 时 sim0.83 候选不降级 MISSING 保留,负证据仍在)。
- [x] **Step 3.3**: spec 状态落定+plan 勾选 commit;controller push 重试至 `0\t0`。
- [x] **Step 3.4**: .wolf/memory+cerebrum、auto-memory、终报。

---

## 执行约束

1. 分支 main-dev-fork,inline 执行不 push 直到 Task 3。
2. 外来 WIP 禁碰(git status 全部修改文件);只碰上列五文件+两 docs。
3. 不碰 `.wolf/`(控制器收尾统一记)。
4. 中文一律 Write/Edit 工具。
5. 行号是快照,先读现场再改;与 spec 冲突以 spec 为准并报告。
6. 测试数字如实;golden 零翻红是铁律。
