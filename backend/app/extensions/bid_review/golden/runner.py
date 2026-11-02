"""金标准评测核(EAI-CUSTOM 2026-11-03,spec §6/§7):case → evaluate_fields(共享
分派核,禁复制循环)→ 期望对表 → CaseResult。判定顺序:expect_issues 按 rule_id
分桶逐条消化(verdict 分桶,severity+contains 全对才算命中)→ expect_absent 查违例
→ strict 只数期望外 verdict=violation。scripted model_fn:按规则卡「规则:<id>」
路由 model_script;缺省回安静 full 应答(零条目;hyb 候选被 full 驳回→零产出)。"""

import json
from pathlib import Path

import yaml

from app.extensions.bid_review.engine.attachments import build_checklist
from app.extensions.bid_review.engine.eval_core import evaluate_fields, wrap_model_fn
from app.extensions.bid_review.engine.rule_runner import RulePack, load_rulepack
from app.extensions.bid_review.golden.loader import RULEPACK_PATH
from app.extensions.bid_review.golden.schema import CaseResult, GoldenCase

_QUIET = json.dumps(
    {"verdicts": [{"clause_id": "golden-quiet", "verdict": "full", "confidence": 1.0, "reason": "golden 默认安静应答", "evidence": [{"doc_id": "golden", "page": 1}]}]},
    ensure_ascii=False,
)


def _scripted_model(case: GoldenCase):
    table = case.model_script

    def model(messages):
        card = messages[0]["content"] if isinstance(messages, list) else str(messages)
        for rid, resp in table.items():
            if f"规则:{rid}" in card:
                return resp
        return _QUIET

    return model


def _rule_pool(expect, issues: list[dict]) -> list[dict]:
    ids = {expect.rule_id, *expect.acceptable_rule_ids}
    return [i for i in issues if i["rule_id"] in ids]


def _entity_ok(expect, i: dict) -> bool:
    """entity 子串对 entity_keys+message(spec §1.5);空 entity 恒过。"""
    return not expect.entity or expect.entity in " ".join([*(i.get("entity_keys") or []), str(i.get("message") or "")])


def _issue_matches(expect, i: dict) -> bool:
    """entity + severity + contains 全对才算命中(spec §1.5)。"""
    if not _entity_ok(expect, i):
        return False
    if expect.severity and i.get("severity") != expect.severity:
        return False
    return all(kw in str(i.get("message") or "") for kw in expect.contains)


def _status_for(expect, issues: list[dict]) -> str:
    """命中 | verdict | entity | severity | contains | missing——判定梯度:每级只差一个维度,
    diff 行直接指出错的是哪个维度(verdict 不符=state mismatch 单列可见,spec §1.5)。"""
    pool = _rule_pool(expect, issues)
    ok = [i for i in pool if i.get("verdict") == expect.verdict]
    if any(_issue_matches(expect, i) for i in ok):
        return "命中"
    if any(_issue_matches(expect, i) for i in pool):
        return "verdict"  # 规则/实体/关键词全对但态判错(state mismatch)
    if any(i.get("verdict") == expect.verdict and (not expect.severity or i.get("severity") == expect.severity) and all(kw in str(i.get("message") or "") for kw in expect.contains) and not _entity_ok(expect, i) for i in pool):
        return "entity"  # 仅实体不符(verdict/severity/关键词全对,质量审查 F2:不得误报「关键词未命中」)
    if any(i.get("verdict") == expect.verdict and expect.severity and i.get("severity") == expect.severity for i in pool):
        return "contains"
    if any(i.get("verdict") == expect.verdict for i in pool):
        return "severity"
    return "missing"


async def run_case(case: GoldenCase, pack: RulePack | None = None) -> CaseResult:
    pack = pack or load_rulepack(RULEPACK_PATH)
    issues = await evaluate_fields(pack, case.fields, model_fn=wrap_model_fn(_scripted_model(case)))
    missing: list[str] = []
    consumed: set[int] = set()
    hits: dict[str, int] = {}
    for e in case.expect_issues:
        st = _status_for(e, issues)
        if st == "命中":
            for idx, i in enumerate(issues):
                if idx not in consumed and i["rule_id"] in {e.rule_id, *e.acceptable_rule_ids} and _issue_matches(e, i) and i.get("verdict") == e.verdict:
                    consumed.add(idx)
                    hits[e.rule_id] = hits.get(e.rule_id, 0) + 1
                    break
            else:
                # 质量审查 F1:_status_for 在 pool 上判「命中」不区分已消化实例;无未被消费的同特征
                # 条目=重复期望假绿,必须补 diff 行(首方括号 token=rule_id,T5 fn 解析依赖该格式)
                missing.append(f"期望未命中[{e.rule_id} {e.severity} {e.verdict}] 命中数不足(无未被消化的同特征条目): contains={e.contains}")
            continue
        tag = {"missing": "未命中", "verdict": "verdict 不符(state mismatch)", "entity": "entity 不符(实体不匹配)", "severity": "severity 不符", "contains": "关键词未命中"}[st]
        missing.append(f"期望未命中[{e.rule_id} {e.severity} {e.verdict}] {tag}: contains={e.contains}")
    absent = [f"不应报而报[{rid}](expect_absent): {next((i['message'][:60] for i in issues if i['rule_id'] == rid), '')}" for rid in case.expect_absent if any(i["rule_id"] == rid and i.get("verdict") == "violation" for i in issues)]
    unexpected: list[str] = []
    if case.strict:
        for idx, i in enumerate(issues):
            if idx in consumed or i.get("verdict") != "violation":
                continue
            unexpected.append(f"期望外 violation[{i['rule_id']} {i['severity']}]: {str(i.get('message'))[:80]}")
    cl_diff: list[str] = []
    if case.checklist is not None:
        cl = build_checklist(case.fields.get("tender.attachment_requirements"), case.fields.get("bid.attachment_index"))
        got_unknown = int((cl.get("counts") or {}).get("unknown") or 0)
        if got_unknown != case.checklist.unknown_count:
            cl_diff.append(f"checklist.counts.unknown 实际 {got_unknown} ≠ 期望 {case.checklist.unknown_count}")
        for no, want in case.checklist.status_by_no.items():
            got = next((r.get("status") for r in cl.get("items") or [] if str(r.get("no") or "") == no), None)  # EAI-CUSTOM:build_checklist items 为平铺行{no,status,...},无嵌套 req 键(计划代码按嵌套形态写,据实际契约改平铺取键)
            if got != want:
                cl_diff.append(f"checklist[{no}].status 实际 {got} ≠ 期望 {want}")
    ok = not (missing or unexpected or absent or cl_diff)
    return CaseResult(case=case.case, desc=case.desc, strict=case.strict, ok=ok, missing=missing, unexpected=unexpected, absent_violations=absent, checklist_diff=cl_diff, hits=hits, n_issues=len(issues))


async def run_all(cases: list[GoldenCase], pack: RulePack | None = None) -> list[CaseResult]:
    pack = pack or load_rulepack(RULEPACK_PATH)
    return [await run_case(c, pack) for c in cases]


def _fields_from_stub(smoke_dir):
    """冒烟题字段构造(EAI-CUSTOM 2026-11-03 spec §8):docs 目录 md 文件 → docs 列表;
    extract_stub.yaml 平映射充当 extract_fn(docs, field_paths)——stub 过滤到「请求路径∩stub 键」
    钉住抽取层接线(build_baseline 只收已知路径,其余显式 null);LLM 不进 CI 门。"""
    from app.extensions.bid_review.engine.extract import build_baseline

    d = Path(smoke_dir)
    docs = []
    for name, role in (("tender.md", "tender"), ("bid.md", "bid")):
        p = d / "docs" / name
        if p.exists():
            docs.append({"doc_id": name, "role": role, "text": p.read_text(encoding="utf-8")})
    stub = yaml.safe_load((d / "extract_stub.yaml").read_text(encoding="utf-8"))
    payload = build_baseline(docs, lambda _docs, _paths: {k: v for k, v in stub.items() if k in set(_paths)})
    return payload["fields"]


async def run_smoke_dir(smoke_dir, pack: RulePack | None = None) -> CaseResult:
    """冒烟题 = build_baseline(extract_stub) 产字段 → 复用 run_case 同一断言核(spec §8:
    钉 docs→抽取→规则全管线接线;题文件名=case id 同名,loader stem 校验的既定契约)。"""
    from app.extensions.bid_review.golden.loader import load_case

    pack = pack or load_rulepack(RULEPACK_PATH)
    case = load_case(Path(smoke_dir) / "L1-009-smoke-basic.yaml", pack)
    case.fields = _fields_from_stub(smoke_dir)
    return await run_case(case, pack)
