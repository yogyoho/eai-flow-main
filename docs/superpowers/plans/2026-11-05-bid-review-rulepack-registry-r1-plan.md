# bid-review 规则包注册表 R1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行)。步骤用 `- [x]` 勾选。
> spec: `docs/superpowers/specs/2026-11-05-bid-review-rulepack-registry-r1-design.md`

**Goal:** 规则包注册表底座——跨源字段宇宙+consumed_by 反查+加载期语义 lint+FIELD_DICTIONARY 退役,零行为变化。

**Architecture:** registry.py(python 索引层,依赖仅 anchors)持有 PROJECTION_FIELDS/SEVERITY_BY_LAYER/RULEPACK_DIR,提供 universe()/consumed_by()/lint_rules();extract.FIELD_DICTIONARY 改为 universe 派生别名;rule_runner.load_rulepack 收尾加 lint 硬拒载;anchors.py 补 A-BID-DOC 注册。

**Tech Stack:** Python 3.12/pytest/yaml。

**依赖方向(防环)**: `extract → registry → anchors`;`rule_runner → registry`(registry 不 import rule_runner/extract)。

---

### Task 1: 文档预提交

- [x] spec + plan 落盘 `git add -f`(显式路径)commit。

### Task 2: registry.py + 测试 TDD

**Files:**
- Create: `backend/app/extensions/bid_review/engine/registry.py`
- Create: `backend/tests/test_bid_review_registry.py`

- [x] **Step 2.1 先写测试**(红): 宇宙锚定(71 路径硬编码列表=改造前 collect_field_paths 输出)+与 collect_field_paths 相等+consumed_by 抽查+A-BID-DOC 回归+severity 白名单正反例+CONTRACTS/shape 集合 ⊆ 宇宙+投影字段声明齐+load 拒载(未知锚/越层 severity/非点路径 input)。
- [x] **Step 2.2 实现** `registry.py`:

```python
"""规则包注册表——跨源索引+lint(EAI-CUSTOM 2026-11-05 R1,spec 裁决②③修正版)。

单一事实源各居其位:字段 inputs=规则包 yaml;锚点=anchors.ANCHOR_REGISTRY(代码单源);
形状契约=extract.FIELD_TYPE_CONTRACTS。本模块只做三件事,不复制任何账本:
1. universe():抽取请求字段宇宙 = 包 inputs ∪ 锚点路径 ∪ 投影字段
2. consumed_by():字段→消费者反查(改字段前先查炸谁)
3. lint_rules():包语义校验(load_rulepack 硬拒载 + pytest 全量 lint)
依赖方向: extract → registry → anchors;rule_runner → registry。禁止反向。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.extensions.bid_review.engine.anchors import ANCHOR_REGISTRY

RULEPACK_DIR = Path(__file__).parent / "rulepacks" / "bid-review-core"

# 投影字段(spec §0 病灶③):被 worker/routers 消费但无规则声明处的 3 条,此处即声明处。
PROJECTION_FIELDS: dict[str, str] = {
    "deviation.items": "B9 偏离表投影(routers.py)",
    "tender.scoring_items": "B4 评分办法投影(routers.py)",
    "tender.project_identity.lot_section": "task.lot_name 标段投影(worker.py)",
}

# severity 层白名单(spec §1 enums 收敛):L1 major=业绩达标特例;L3 禁 fatal(一致性层不否决)。
SEVERITY_BY_LAYER: dict[str, set[str]] = {
    "L1": {"fatal", "major"},
    "L2": {"fatal", "major"},
    "L3": {"major", "minor"},
}


def _pack_rules() -> list[dict]:
    out: list[dict] = []
    for p in sorted(RULEPACK_DIR.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out += data.get("rules") or []
    return out


def pack_inputs() -> set[str]:
    paths: set[str] = set()
    for r in _pack_rules():
        for p in r.get("inputs") or []:
            if isinstance(p, str):
                paths.add(p)
    return paths


def anchor_paths() -> set[str]:
    return {p for a in ANCHOR_REGISTRY.values() for p in a.get("paths", [])}


def universe() -> list[str]:
    """抽取请求字段宇宙(=改造前 collect_field_paths() 输出,逐位相等是零行为门)。"""
    return sorted(pack_inputs() | anchor_paths() | set(PROJECTION_FIELDS))


def consumed_by(path: str) -> dict[str, list[str]]:
    """字段→消费者反查索引(设计一 absorbed):改字段前先查炸谁。"""
    rules = sorted({str(r["id"]) for r in _pack_rules() if path in (r.get("inputs") or [])})
    anchors = sorted(k for k, a in ANCHOR_REGISTRY.items() if path in a.get("paths", []))
    projections = [PROJECTION_FIELDS[path]] if path in PROJECTION_FIELDS else []
    return {"rules": rules, "anchors": anchors, "projections": projections}


def lint_rules(rules) -> list[str]:
    """包语义 lint(load_rulepack 硬拒载);rules=Rule 列表(duck-typed,不 import rule_runner 防环)。"""
    problems: list[str] = []
    for r in rules:
        rid = getattr(r, "id", "?")
        for ev in getattr(r, "evidence", []) or []:
            if ev not in ANCHOR_REGISTRY:
                problems.append(f"规则 {rid}: evidence 锚 {ev} 未注册(ANCHOR_REGISTRY 无此名,运行时会静默丢)")
        whitelist = SEVERITY_BY_LAYER.get(getattr(r, "layer", ""))
        if whitelist is None:
            problems.append(f"规则 {rid}: 未知层 {getattr(r, 'layer', '')!r}")
        elif getattr(r, "severity", "") not in whitelist:
            problems.append(f"规则 {rid}: severity {getattr(r, 'severity', '')!r} 不在 {r.layer} 白名单 {sorted(whitelist)}")
        for p in getattr(r, "inputs", []) or []:
            if not isinstance(p, str) or not p.strip() or "." not in p:
                problems.append(f"规则 {rid}: input {p!r} 非点路径")
    return problems
```

CLI(`__main__`,consumed_by 反查): 无参打全表,带参打单字段。

- [x] **Step 2.3 验绿**。

### Task 3: load_rulepack 硬校验 + A-BID-DOC 注册

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rule_runner.py`(load_rulepack 收尾)
- Modify: `backend/app/extensions/bid_review/engine/anchors.py`(ANCHOR_REGISTRY 增 A-BID-DOC)

- [x] **Step 3.1 测试先行**(Task 2.1 已含拒载三例+A-BID-DOC 回归,此处实现):

```python
# load_rulepack return 前追加:
    from app.extensions.bid_review.engine.registry import lint_rules

    problems = lint_rules(rules)
    if problems:
        raise RulePackError("规则包语义校验失败(拒载):\n" + "\n".join(problems))
```

anchors.py 投标侧区块加:

```python
    "A-BID-DOC": {
        # 投标文件附件区域(L2-021 唯一 evidence,2026-11-05 R1 补注册:此前未注册被
        # anchor_rule_paths 静默跳过=证据区悄悄丢;paths 与 L2-021 inputs 同域=零行为,
        # M1 附件实体落地后扩 paths)
        "label": "投标文件附件区域",
        "paths": ["tender.attachment_requirements", "bid.attachment_index"],
    },
```

- [x] **Step 3.2 验绿**: 新套件全绿+golden 55/55。

### Task 4: FIELD_DICTIONARY 退役

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py`

- [x] **Step 4.1**: 先 grep FIELD_DICTIONARY 全部消费面确认只有 collect_field_paths(若有其他消费面,逐个核对宇宙语义)。替换字面量为派生(字面量注释块整体删除,留退役说明):

```python
from app.extensions.bid_review.engine.registry import universe as _registry_universe

# 字段宇宙单一事实源=registry(EAI-CUSTOM 2026-11-05 R1 裁决②修正):旧 24 路径字面量退役,
# 改为 registry.universe 派生(包 inputs ∪ 锚点路径 ∪ 投影字段)——与 collect_field_paths()
# 同源,消除"字典说有/包说没有"漂移(取证:47/68 inputs 不在旧字典)。
FIELD_DICTIONARY: frozenset[str] = frozenset(_registry_universe())
```

`_RULEPACK_DIR` 删除(registry.RULEPACK_DIR 接管),collect_field_paths() 改 `return list(universe())` 一行委托(yaml import 若再无使用则删,ruff 把关)。
- [x] **Step 4.2 验绿**: test_bid_review_extract 全绿(prompt 骨架转录+materials_hash 零变化)+M0 快照 26/26。

### Task 5: 全量验证

- [x] golden 55/55 零翻红;全家 pytest 精确计数(422+新增)全绿;ruff 触碰文件;collect_field_paths() 逐位=71 路径(测试锚定)。

### Task 6: 收尾

- [x] spec 状态+plan 勾选 commit;push 重试至 `0\t0`;wolf(buglog A-BID-DOC 静默丢锚=id 3985/memory/cerebrum)+anatomy+auto-memory;终报。

---

## 执行约束

main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;golden 55/55 零翻红铁律;registry 不 import rule_runner/extract(防环,注释已写明)。
