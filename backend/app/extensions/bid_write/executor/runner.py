"""断言执行核(批二十 M1,EAI-CUSTOM 2026-11-13)——纯函数 ctx→RunReport,零 IO
零时钟(20× 字节级一致验收面)。执行语义 spec §8 逐条兑现:

- 排序:执行序=(level_rank, assertion_id) 字典序,D0 先跑(短路语义前置);委托条
  (delegates_to)不进执行序,全量跑完后镜像委托目标结果(单实现律,不重复执行)。
- 短路:D0 的**业务判定面** FAIL 或 ERROR(CtxMissing 计 ERROR)短路同技能未执行
  断言(SKIPPED 注明「因 SK-XX 失败跳过」),其他技能继续;CMN 共享层恒执行
  (export 级全扫描,不受 skills 裁剪)。E-VALIDATOR-MISSING / E-VALIDATOR-RAISED
  为基建完备面,非业务判定——逐条独立 ERROR 报告、**不**触发短路(信息量更大,
  分批注册中期态不误伤已注册面)。
- 上下文缺失:校验函数 raise CtxMissing → ERROR ``E-CTX-MISSING: <key>``,视为
  失败面,不得静默通过(诚实伪零同律)。
- 注册完备性运行时兜底:REGISTRY 缺函数 → ERROR E-VALIDATOR-MISSING(CI pin 之外
  的第二道);校验函数自身异常 → ERROR E-VALIDATOR-RAISED(与业务 FAIL 区分,
  永不静默)。
- blocks_export 由 levels 行为表 blk 列按 final 级分派(词级升级 D0 即阻断)。"""

from __future__ import annotations

from app.extensions.bid_write.executor.loader import load_registry
from app.extensions.bid_write.executor.models import (
    LEVEL_RANK,
    SKIP_NO_SIGNAL,
    SKIP_SHORT_CIRCUIT,
    ST_ERROR,
    ST_FAIL,
    ST_PASS,
    ST_SKIPPED,
    AssertionDef,
    AssertionResult,
    CtxMissing,
    Outcome,
    RunReport,
)
from app.extensions.bid_write.executor.validators import REGISTRY

_FAIL_STATES = (ST_FAIL, ST_ERROR)


def _base(adef: AssertionDef) -> dict:
    return {
        "assertion_id": adef.id,
        "skill": adef.skill,
        "name": adef.name,
        "human_action": adef.human_action,
        "rule_ref": adef.rule_ref,
    }


def _err(adef: AssertionDef, message: str) -> AssertionResult:
    return AssertionResult(**_base(adef), status=ST_ERROR, level=adef.level, blocks_export=adef.blocks_export, deterministic=True, message=message)


def run_assertions(ctx: dict, skills: tuple[str, ...] | list[str] | None = None) -> RunReport:
    """执行断言集。skills=None 全量;给定产品技能子集时 CMN 共享层仍恒执行。"""
    snap = load_registry()
    requested = tuple(sorted(skills)) if skills else None
    scope = [d for d in snap.assertions if d.skill == "CMN" or requested is None or d.skill in requested]
    delegate_ids = {d.id for d in scope if d.delegates_to}
    exec_list = sorted((d for d in scope if d.id not in delegate_ids), key=lambda d: (LEVEL_RANK[d.level], d.id))

    results: dict[str, AssertionResult] = {}
    short_circuit_by: dict[str, str] = {}  # skill → 触发短路的 D0 断言 id

    for adef in exec_list:
        killer = short_circuit_by.get(adef.skill)
        if killer:
            results[adef.id] = AssertionResult(
                **_base(adef),
                status=ST_SKIPPED,
                level=adef.level,
                blocks_export=False,
                deterministic=True,
                message=f"因 {killer} 失败跳过(不代表通过)",
                skipped_reason=SKIP_SHORT_CIRCUIT,
            )
            continue
        fn = REGISTRY.get(adef.id)
        if fn is None:
            res = _err(adef, f"E-VALIDATOR-MISSING: {adef.id} 未注册校验函数")
        else:
            try:
                out: Outcome = fn(ctx, adef)
            except CtxMissing as exc:
                res = _err(adef, f"E-CTX-MISSING: {exc.key}")
                if adef.level == "D0":
                    short_circuit_by[adef.skill] = adef.id
            except Exception as exc:  # noqa: BLE001 — 校验器缺陷转 ERROR 面不静默(不触发短路:基建面)
                res = _err(adef, f"E-VALIDATOR-RAISED: {type(exc).__name__}: {exc}")
            else:
                final = out.level or adef.level
                res = AssertionResult(
                    **_base(adef),
                    status=out.status,
                    level=final,
                    blocks_export=bool(snap.levels[final].get("blk")),
                    deterministic=True if out.deterministic is None else out.deterministic,
                    message=out.message,
                    note=out.note,
                    skipped_reason=SKIP_NO_SIGNAL if out.status == ST_SKIPPED else None,
                )
                if final == "D0" and out.status in _FAIL_STATES:
                    short_circuit_by[adef.skill] = adef.id
        results[adef.id] = res

    # 委托镜像(单实现律:目标已跑,本条只登记技能级 ID/错误码)
    by_id = snap.by_id()
    for did in sorted(delegate_ids):
        d = by_id[did]
        src = results.get(d.delegates_to)
        if src is None:
            results[did] = _err(d, f"E-DELEGATE-TARGET-MISSING: {d.delegates_to} 不在本次运行范围")
        else:
            results[did] = AssertionResult(
                **_base(d),
                status=src.status,
                level=src.level,
                blocks_export=src.blocks_export,
                deterministic=src.deterministic,
                message=src.message or f"同 {d.delegates_to} 口径",
                note=src.note,
                skipped_reason=src.skipped_reason,
                source_id=src.assertion_id,
            )

    ordered = sorted(results.values(), key=lambda r: (LEVEL_RANK[r.level], r.assertion_id))
    return RunReport(schema_version=snap.schema_version, skills=requested, results=ordered)


# 状态词汇 re-export(调用方/测试统一自 runner 取)
__all__ = ["run_assertions", "ST_PASS", "ST_FAIL", "ST_ERROR", "ST_SKIPPED"]
