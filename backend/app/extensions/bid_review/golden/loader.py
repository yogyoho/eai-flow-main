"""题库 YAML 载入+校验(EAI-CUSTOM 2026-11-03)。fail-fast:schema 不合法/字段越界/
规则 id 引用不完整/sem 断言缺 script 一律加载期报错,不带病进跑批(spec §11)。"""

import re
from pathlib import Path

import yaml

from app.extensions.bid_review.engine.rule_runner import load_rulepack
from app.extensions.bid_review.golden.schema import ChecklistExpect, Expectation, GoldenCase

RULEPACK_PATH = str(Path(__file__).resolve().parent.parent / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml")
# 投影端点消费但非规则 inputs 的字段(spec §5 白名单并集)
PROJECTION_PATHS = {"tender.attachment_requirements", "bid.attachment_index", "tender.scoring_items"}

_NAME_RE = re.compile(r"^[A-Z0-9]+-[0-9]+-[a-z0-9-]+$")


def known_field_paths(pack=None) -> set[str]:
    pack = pack or load_rulepack(RULEPACK_PATH)
    paths: set[str] = set(PROJECTION_PATHS)
    for r in pack.rules:
        paths.update(r.inputs or [])
    return paths


def load_case(path: str | Path, pack=None) -> GoldenCase:
    fname = Path(path).name
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"题库 YAML 顶层须为映射(top-level mapping): {fname}")
    case = str(data.get("case") or "")
    pack = pack or load_rulepack(RULEPACK_PATH)
    types = {r.id: r.type for r in pack.rules}
    ids = set(types)
    allowed = known_field_paths(pack)
    bad = [k for k in (data.get("fields") or {}) if k not in allowed]
    if bad:
        raise ValueError(f"未知字段路径(rulepack inputs ∪ 投影路径之外): {bad}(file: {fname})")
    expects = [
        Expectation(
            rule_id=str(e["rule_id"]),
            severity=str(e.get("severity") or ""),
            contains=[str(x) for x in (e.get("contains") or [])],
            verdict=str(e.get("verdict") or "violation"),
            entity=str(e.get("entity") or ""),
            acceptable_rule_ids=[str(x) for x in (e.get("acceptable_rule_ids") or [])],
        )
        for e in (data.get("expect_issues") or [])
    ]
    script = {str(k): str(v) for k, v in (data.get("model_script") or {}).items()}
    for e in expects:
        rid_type = types.get(e.rule_id)
        if rid_type is None:
            raise ValueError(f"expect_issues 引用不存在的规则 {e.rule_id}(file: {fname})")
        if rid_type in ("semantic", "hybrid") and e.rule_id not in script:
            # 引擎从不产出 verdict "full"(full 条目在建 issue 前被跳过),故无豁免分支:sem/hyb 断言必须配 script
            raise ValueError(f"expect_issues 引用 sem/hyb 规则 {e.rule_id} 但缺 model_script(默认安静应答只会回 full)(file: {fname})")
        unknown_acc = [x for x in e.acceptable_rule_ids if x not in ids]
        if unknown_acc:
            raise ValueError(f"acceptable_rule_ids 引用不存在的规则 {unknown_acc}(file: {fname})")
    absent = [str(x) for x in (data.get("expect_absent") or [])]
    unknown_absent = [x for x in absent if x not in ids]
    if unknown_absent:
        # 拼错的抑制 id 会让 T3 的 absent 断言空转成假绿,加载期即拒
        raise ValueError(f"expect_absent 引用不存在的规则 {unknown_absent}(file: {fname})")
    cl = data.get("checklist")
    # 命名校验放在内容校验之后:synthetic 校验夹具允许非规范名,内容错误优先暴露(真实题库仍强制 {{rule_id}}-{{slug}} 命名)
    if not _NAME_RE.match(case) or case != Path(path).stem:
        raise ValueError(f"case 与文件名不一致或命名非法: {case} vs {Path(path).stem}(规则 {{rule_id}}-{{slug}})(file: {fname})")
    return GoldenCase(
        case=case,
        desc=str(data.get("desc") or ""),
        fields=dict(data.get("fields") or {}),
        expect_issues=expects,
        expect_absent=absent,
        strict=bool(data.get("strict") or False),
        checklist=ChecklistExpect(**cl) if cl else None,
        model_script=script,
        source_path=str(path),
    )


def load_cases(directory: str | Path = None) -> list[GoldenCase]:
    directory = Path(directory) if directory else Path(__file__).resolve().parent / "cases"
    pack = load_rulepack(RULEPACK_PATH)  # 整批共享一次 rulepack 解析(逐 case 重解析 34 规则 ≈51ms/次)
    return [load_case(p, pack=pack) for p in sorted(directory.glob("*.yaml"))]
