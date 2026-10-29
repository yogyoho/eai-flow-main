#!/usr/bin/env python3
"""bid-review 注入集评测入口(Task 20)——golden 每案 × advance_task 全链 → 指标 → 门禁 → JSON 报告。

用法(backend/ 目录,`make eval-bid-review` 同款;设计文档 §7:分钟级,不进 make test 默认链,
CI 手动触发)::

    PYTHONPATH=. uv run python tests/eval/bid_review/run_eval.py
    PYTHONPATH=. uv run python tests/eval/bid_review/run_eval.py --manifest tests/eval/bid_review/golden/manifest.yaml

管线(零网络,不走真 LLM):case.yaml 的 field_snapshot(干净底盘,有 fields_clean.json 优先)
经 inject.py 的 MUTS 注册表按 case.yaml injections 逐条扰动(Task 19 注入算子唯一真源,缺席
即 SystemExit 不静默)→ 扰动后快照经 extract_fn 直灌 advance_task(plan Step 3)→
crud.list_issues 收集预测 → metrics.compute_metrics → gate_check → stdout JSON 报告,
任一门禁失败退出码 1(硬阻断)。

sem/hyb 与 fake-model:advance_task 支持 model_fn 入参时(Plan Task 14 已集成)注入确定性
fake-model(恒回 unclear 结论,过 check_schema 走七道 → need_human 条目存活出管线,即 A12
γ 路径的全链零网络验证;恒 stub 不伪造 violation,fake 造出的「违规」不构成可评测的模型质量);
worker 未集成 sem/hyb 时(det-only 版本)自动退化为 det-only,无需改此处。need_human/unclear
行按 metrics A12 分列口径不入 P/R 分母,单列统计。

确定性零漂移门禁:每案连跑 2 次,engine 产出字段(rule/layer/severity/verdict/message/fix/
evidence/dedup_key/confidence,按落库行序)序列化逐字节一致;漂移即 determinism<1.0 → 门禁挂。
首跑基线数字(Step 5)记录于 manifest 注释(授权面所限由编排方落稿,数字见交付回报 notes)。
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))  # metrics/inject 与本脚本平铺同目录(python 直跑时本就在 path,双保险)

import inject as inject_ops  # noqa: E402  Task 19 注入算子注册表(MUTS,缺席即报错约定)
from metrics import CaseEval, Issue, bootstrap_ci, compute_metrics, gate_check  # noqa: E402

from app.extensions.bid_review import crud, models  # noqa: E402
from app.extensions.bid_review.worker import RULEPACK_PATH, advance_task  # noqa: E402
from app.extensions.database import Base  # noqa: E402

_EVAL_OWNER = "bid-review-eval"
_CANON_FIELDS = ("rule_id", "layer", "severity", "verdict", "need_human", "message", "fix", "evidence", "dedup_key", "confidence")

_TABLES = [
    models.ReviewTask.__table__,
    models.ReviewIssue.__table__,
    models.BaselinePackage.__table__,
    models.RulePackMeta.__table__,
    models.ReviewFeedback.__table__,
]


def _load_manifest(manifest_path: Path) -> dict:
    man = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not man.get("cases"):
        raise SystemExit(f"manifest {manifest_path} 无 cases:金标准包为空,先按 Task 19 补案")
    return man


def _load_case(golden_root: Path, entry: dict) -> dict:
    """case.yaml + golden_issues.jsonl;field_snapshot 取扰动基底(cases/<id>/fields_clean.json
    优先,与 inject.py 契约一致;缺席用 case.yaml 内嵌 section——Task 19 的 fallback 约定)。"""
    cdir = golden_root / str(entry.get("dir") or f"cases/{entry['id']}")
    meta = yaml.safe_load((cdir / "case.yaml").read_text(encoding="utf-8")) or {}
    clean_file = cdir / "fields_clean.json"
    if clean_file.exists():
        meta["_base_snapshot"] = json.loads(clean_file.read_text(encoding="utf-8"))
    else:
        meta["_base_snapshot"] = dict(meta.get("field_snapshot") or {})
    golden: list[Issue] = []
    gf = cdir / "golden_issues.jsonl"
    if gf.exists():
        for line in gf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                golden.append(Issue.from_row(json.loads(line)))
    return {"id": str(entry["id"]), "meta": meta, "golden": golden, "dir": cdir}


def _mutated_snapshot(case: dict) -> dict:
    """干净底盘 → 逐条 case.yaml injections 应用 inject.MUTS 扰动(算子缺席即 SystemExit,
    plan Task 19 约定「录一个注册一个,缺席即报错不静默」)。"""
    snap = dict(case["meta"]["_base_snapshot"])
    for inj in case["meta"].get("injections") or []:
        mut = str(inj.get("mutator", ""))
        op = inject_ops.MUTS.get(mut)
        if op is None:
            raise SystemExit(f"case {case['id']}: {mut} 未转录,按设计文档 §7 MUT 目录补 inject.MUTS 条目(禁静默跳过)")
        snap = op(snap)
    return snap


class _FakeReply:
    """确定性 fake-model 回复:恒回 unclear 结论(过 check_schema,经七道 → need_human 存活)。"""

    content = json.dumps(
        {
            "verdicts": [
                {
                    "verdict": "unclear",
                    "confidence": 0.5,
                    "reason": "评测 fake-model:离线零网络确定性桩,不产正式违规判定(待人工)",
                    "evidence": [{"doc_id": "EVAL-FAKE", "page": 1, "text": "fake-model stub"}],
                }
            ]
        },
        ensure_ascii=False,
    )


def _fake_model_fn(_messages):
    return _FakeReply()


def _case_docs(case: dict) -> list[dict]:
    """advance_task 的 docs 入参(评测直灌场景 text 内容不参与求值,仅 role 决定基线行拆分)。"""
    docs = []
    for d in case["meta"].get("documents") or []:
        doc_id = str(d.get("doc_id", ""))
        docs.append({"doc_id": doc_id, "role": "tender" if "TENDER" in doc_id.upper() else "bid", "text": str(d.get("name", doc_id))})
    return docs


def _canon(issues: list[Issue]) -> bytes:
    """det 输出规范化字节串(排除 id/时间戳等行元数据;字段序即落库行序,不排序——排序会掩盖产出顺序漂移)。"""
    payload = [{k: getattr(i, k) for k in _CANON_FIELDS} for i in issues]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


async def _run_case_once(factory, case: dict, supports_model_fn: bool) -> list[Issue]:
    """advance_task 全链单跑(parsing→extracting→基线→running→review→done),收集落库预测行。"""
    snapshot = _mutated_snapshot(case)
    async with factory() as db:
        t = await crud.create_task(db, owner_id=_EVAL_OWNER)
        extract = lambda docs, paths: {p: snapshot.get(p) for p in paths}  # noqa: E731  扰动后 field_snapshot 直灌(plan Step 3)
        kwargs = {"model_fn": _fake_model_fn} if supports_model_fn else {}
        task = await advance_task(db, t.id, owner_id=_EVAL_OWNER, docs=_case_docs(case), extract_fn=extract, wait_confirm=False, **kwargs)
        if task.status != "done":
            raise SystemExit(f"case {case['id']} advance_task 终态 {task.status}(!=done):评测管线上游断裂,先修链路再谈指标")
        rows = await crud.list_issues(db, task_id=t.id, owner_id=_EVAL_OWNER)
        return [Issue.from_row(r) for r in rows]


def _worker_supports_model_fn() -> bool:
    """worker advance_task 是否已支持 model_fn(Plan Task 14 集成判据):并发过渡期对
    det-only 旧签名与 sem/hyb 新签名都可用,不与未落稿的 worker 改动强耦合。"""
    try:
        return "model_fn" in inspect.signature(advance_task).parameters
    except (TypeError, ValueError):
        return False


async def eval_all(manifest_path: Path) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    man = _load_manifest(manifest_path)
    golden_root = manifest_path.parent
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    cases: list[CaseEval] = []
    case_reports: list[dict] = []
    drifts_passed = 0
    supports_model_fn = _worker_supports_model_fn()
    try:
        for entry in man["cases"]:
            case = _load_case(golden_root, entry if isinstance(entry, dict) else {"id": str(entry)})
            run1 = await _run_case_once(factory, case, supports_model_fn)
            run2 = await _run_case_once(factory, case, supports_model_fn)  # 确定性零漂移:同案第 2 跑
            drift_ok = _canon(run1) == _canon(run2)
            drifts_passed += int(drift_ok)
            cases.append(CaseEval(case_id=case["id"], golden=case["golden"], predictions=run1))
            formal = [i for i in run1 if i.is_formal]
            need_human = len(run1) - len(formal)
            case_reports.append(
                {
                    "case_id": case["id"],
                    "golden": len(case["golden"]),
                    "predicted_formal": len(formal),
                    "predicted_need_human": need_human,
                    "matched_rule_ids": sorted({g.rule_id for g in case["golden"]} & {p.rule_id for p in formal}),
                    "golden_rule_ids": sorted({g.rule_id for g in case["golden"]}),
                    "predicted_rule_ids": sorted({p.rule_id for p in formal}),
                    "drift_ok": drift_ok,
                }
            )
    finally:
        await engine.dispose()

    determinism = drifts_passed / len(man["cases"])
    metrics_dict = compute_metrics(cases, determinism=determinism)
    ci = bootstrap_ci(cases)
    ok, failures = gate_check(metrics_dict)
    return {
        "manifest": {"name": man.get("name"), "version": str(man.get("version")), "rulepack": str(man.get("rulepack")), "rulepack_path": str(RULEPACK_PATH)},
        "pipeline": {"sem_hyb_fake_model": supports_model_fn, "note": "true=advance_task 已接 model_fn(Plan Task 14),fake-model 恒回 unclear 走七道;false=det-only 旧签名"},
        "cases": case_reports,
        "determinism": {"cases": len(man["cases"]), "passed": drifts_passed, "rate": determinism},
        "need_human": {"predicted_total": metrics_dict["need_human_predicted"], "note": "A12 分列口径:待人工/unclear 不入 P/R 分母,单独人审队列"},
        "metrics": metrics_dict,
        "bootstrap_ci": ci,
        "gate": {"ok": ok, "failures": failures},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="bid-review 注入集评测门禁(Task 20)")
    ap.add_argument("--manifest", default=str(EVAL_DIR / "golden" / "manifest.yaml"))
    args = ap.parse_args()
    report = asyncio.run(eval_all(Path(args.manifest)))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["gate"]["ok"]:
        print(f"\nGATE FAIL: {'; '.join(report['gate']['failures'])}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
