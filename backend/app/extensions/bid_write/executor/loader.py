"""断言注册表加载器(批二十 M1,EAI-CUSTOM 2026-11-13)——assertions/p0.yaml →
RegistrySnapshot。加载期静态校验=既有注册表 pin 的服务端复刻(spec §8):ID 唯一/
级别词汇/D0⇔blocks_export/schema_version==contracts.SCHEMA_VERSION/delegates 目标
存在/编号前缀与技能一致。rule_ref 悬空面=既有 test_bid_write_assertions pin(CI
时点)——运行时不重扫审查注册表(yaml 随仓走、CI 拒幽灵,运行时重扫零增益)。
registry 为静态内容(禁热改),module 级缓存;测试经 _load(临时 yaml) 走拒载分支。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.extensions.bid_write.contracts import (
    BLOCK_EXPORT_LEVELS,
    DEGRADE_LEVELS,
    SCHEMA_VERSION,
)
from app.extensions.bid_write.executor.models import AssertionDef, RegistrySnapshot

_YAML_PATH = Path(__file__).resolve().parent.parent / "assertions" / "p0.yaml"


class RegistryError(ValueError):
    """注册表加载期静态校验失败(拒载,与审查端 rulepack load 硬拒载同律)。"""


def _load(path: Path) -> RegistrySnapshot:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RegistryError(f"{path}: 注册表顶层须为 mapping")
    meta = raw.get("meta") or {}
    version = str(meta.get("schema_version", ""))
    if version != SCHEMA_VERSION:
        raise RegistryError(f"schema_version {version!r} != contracts.SCHEMA_VERSION {SCHEMA_VERSION!r}(幽灵/过期注册表拒载)")

    levels = raw.get("levels") or {}
    for lvl in DEGRADE_LEVELS:
        if lvl not in levels:
            raise RegistryError(f"levels 行为表缺 {lvl}(执行器按表分派,缺行拒载)")
    if not levels["D0"].get("blk"):
        raise RegistryError("levels 表 D0 行 blk 必须 true(导出阻断面真源)")
    for lvl in ("D1", "D2", "D3"):
        if levels[lvl].get("blk"):
            raise RegistryError(f"levels 表 {lvl} 行 blk 须 false")

    rows = raw.get("assertions") or []
    seen: set[str] = set()
    defs: list[AssertionDef] = []
    for row in rows:
        aid = str(row.get("id", ""))
        skill = str(row.get("skill", ""))
        if not aid.startswith(f"SK-{skill}-"):
            raise RegistryError(f"{aid}: id 前缀与 skill {skill!r} 不一致")
        if aid in seen:
            raise RegistryError(f"断言 ID 重复: {aid}")
        seen.add(aid)
        level = str(row.get("level", ""))
        if level not in DEGRADE_LEVELS:
            raise RegistryError(f"{aid}: 非法 level {level!r}(合法:{DEGRADE_LEVELS})")
        blocks_export = bool(row.get("blocks_export"))
        if (level in BLOCK_EXPORT_LEVELS) != blocks_export:
            raise RegistryError(f"{aid}: D0⇔blocks_export 一致性违例(level={level}, blocks_export={blocks_export})")
        refs = row.get("delegates_to")
        if refs is not None and not str(refs).startswith("SK-"):
            raise RegistryError(f"{aid}: delegates_to 须为 SK-* id,得 {refs!r}")
        defs.append(
            AssertionDef(
                id=aid,
                skill=skill,
                name=str(row.get("name", "")),
                level=level,
                blocks_export=blocks_export,
                rule_ref=row.get("rule_ref"),
                expr=str(row.get("expr", "")),
                human_action=row.get("human_action"),
                delegates_to=str(refs) if refs else None,
            )
        )

    by_id = {d.id: d for d in defs}
    for d in defs:
        if d.delegates_to is not None:
            target = by_id.get(d.delegates_to)
            if target is None:
                raise RegistryError(f"{d.id}: delegates_to {d.delegates_to} 不存在(悬空拒载)")
            if target.delegates_to is not None:
                raise RegistryError(f"{d.id}: delegates 链超一跳(→{target.delegates_to})")
            if target.skill != "CMN":
                raise RegistryError(f"{d.id}: 委托目标须为 CMN 共享层,得 {target.skill}")

    shared_layer = str(meta.get("shared_layer", "CMN"))
    for d in defs:
        if d.skill == shared_layer and not d.id.startswith(f"SK-{shared_layer}-"):
            raise RegistryError(f"共享层 {shared_layer} 混入异前缀断言 {d.id}")

    return RegistrySnapshot(assertions=tuple(defs), levels=dict(levels), schema_version=version)


@lru_cache(maxsize=1)
def load_registry() -> RegistrySnapshot:
    """生产入口(缓存;断言注册表为静态内容,变更走 CI+发版不走热载)。"""
    return _load(_YAML_PATH)
