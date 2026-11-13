"""断言校验函数注册表(批二十 M1,EAI-CUSTOM 2026-11-13)——无通用 DSL(spec §8
裁决):每条断言一个 Python 校验函数按 assertion_id 注册,yaml expr 注=实现验收
基准。签名 ``fn(ctx, adef) -> Outcome``;上下文键缺失 raise CtxMissing(key)
(runner 转 ERROR E-CTX-MISSING,不得静默)。委托条(如 SK-AI-009)不注册——
runner 从委托目标镜像结果(单实现律)。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.extensions.bid_write.executor.models import AssertionDef, CtxMissing, Outcome

ValidatorFn = Callable[[dict, AssertionDef], Outcome]

REGISTRY: dict[str, ValidatorFn] = {}


def register(assertion_id: str) -> Callable[[ValidatorFn], ValidatorFn]:
    """按 assertion_id 注册;重复注册=编程错误直接炸(assert 在导入期触发)。"""

    def deco(fn: ValidatorFn) -> ValidatorFn:
        if assertion_id in REGISTRY:
            raise AssertionError(f"校验函数重复注册: {assertion_id}")
        REGISTRY[assertion_id] = fn
        return fn

    return deco


def need(mapping: Any, key: str) -> Any:
    """键取值;宿主非 dict / 键缺失 / 值为 None → CtxMissing(诚实失败不静默)。"""
    if not isinstance(mapping, dict) or key not in mapping or mapping[key] is None:
        raise CtxMissing(key)
    return mapping[key]


def opt(mapping: Any, key: str, default: Any = None) -> Any:
    return mapping.get(key, default) if isinstance(mapping, dict) else default


def norm_text(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def resolve_entity_refs(refs, entities: dict) -> tuple[list[str], int]:
    """实体引用解析(CMN-003/RT-007 共用):refs=引用 id 列表(str),
    entities=material.entities 映射。返回 (未解析 id 列表, 总数)。"""
    ids = [str(r).strip() for r in refs or []]
    unresolved = [r for r in ids if r not in (entities or {})]
    return unresolved, len(ids)


# 导入即注册(各技能模块自注册;新技能文件在此追加一行)
from app.extensions.bid_write.executor.validators import ai, bl, cmn, ps, rt  # noqa: E402, F401
