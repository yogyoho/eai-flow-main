"""共享规则分派核(金标准评测集 spec §4,EAI-CUSTOM 2026-11-03):worker._run_review_stage
与 golden 评测器共用同一段分派逻辑——det/sem 分派、None 字段剥离、逐规则异常隔离降级
need_human。金标准尺子量的必须是生产同一段代码,评测器禁复制分派循环(复制=两把尺子,
必然漂移说谎)。bug 编号:无;升级注意:改分派语义须同步跑 tests/test_bid_review_eval_core.py
与金标准全库。本模块无 DB、无状态:worker 侧进度上报(crud.set_status)与条目落库
(crud.add_issue)由调用方以 on_progress 回调 + 返回值自行承担。
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from types import SimpleNamespace

from app.extensions.bid_review.engine.llm_runner import run_sem_rule
from app.extensions.bid_review.engine.rule_runner import Rule, RulePack, _need_human, attach_evidence, run_det_rule

logger = logging.getLogger(__name__)


# ── 模型接线包装(自 worker._wrap_model_fn/_content_to_str 原样迁入,金标准重构;
#    worker 侧留 _wrap_model_fn 兼容别名;engine._call_model 不改)────────────────


def _content_to_str(content) -> str:
    """response.content 归一为 str:LangChain 分块 list 形态(list 时拼接各 text 部件;
    str 项直取,dict 项取 text 键)——不归一则 check_schema 两试皆败→整规则静默空产出。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                parts.append(chunk["text"])
        return "".join(parts)
    return str(content) if content is not None else ""


def wrap_model_fn(model_fn):
    """模型接线包装层:调注入的 raw model_fn(同步/异步 callable 均可),把
    response.content 归一为 str 后以带 .content 的轻量响应对象回交引擎(契约与
    llm_runner._call_model 的 getattr(response, "content") 对齐)。"""

    async def _wrapped(messages):
        response = model_fn(messages)
        if inspect.isawaitable(response):
            response = await response
        raw = getattr(response, "content", response)
        return SimpleNamespace(content=_content_to_str(raw))

    return _wrapped


ProgressCB = Callable[[int, int, Rule], Awaitable[None]]


async def evaluate_fields(
    pack: RulePack,
    fields: dict,
    *,
    model_fn,
    materials: str = "",
    docs_text: str = "",
    provenance: dict | None = None,
    on_progress: ProgressCB | None = None,
) -> list[dict]:
    """字段 → issues(无 DB、无状态)。model_fn 为已包装形态(wrap_model_fn 产物)。
    与 worker._run_review_stage 分派语义逐字一致(None 剥离/类型分派/逐规则隔离):
    None 值字段先剥离——det 求值器不容 None(比较算子会 TypeError),剥离后两通路统一走
    need_human 约定(on_missing_input=need_human);sem 侧同口径(None 字段=缺字段)。
    逐规则隔离:单规则异常——含模型不可用/接线失败(ModelNotConfigured)——降级
    need_human 条目,兄弟规则照常,禁整批崩。"""
    det_fields = {k: v for k, v in fields.items() if v is not None}
    rules = [r for r in pack.rules if r.enabled]
    total = max(len(rules), 1)
    out: list[dict] = []
    for i, rule in enumerate(rules, start=1):
        if on_progress is not None:
            await on_progress(i, total, rule)
        try:
            if rule.type == "deterministic":
                issues = attach_evidence(run_det_rule(rule, det_fields), rule, provenance)
            else:  # semantic|hybrid
                issues = await run_sem_rule(rule, det_fields, materials, model_fn, docs_text)
        except Exception as exc:  # noqa: BLE001
            # 逐规则异常隔离(worker 同款语义):run_det_rule 只把 KeyError 转 need_human;
            # 求值意外与模型侧故障在此统一降级 need_human,不外溢单规则异常。
            logger.warning("bid_review rule %s crashed, downgraded to need_human: %r", rule.id, exc)
            issues = [_need_human(rule, f"规则执行异常 {exc!r}(逐规则隔离降级 need_human)")]
        out.extend(issues)
    return out
