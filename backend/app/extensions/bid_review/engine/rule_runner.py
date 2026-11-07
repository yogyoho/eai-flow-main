"""规则包加载 + det 执行(canonical;技能内 eval_det.py 为其无量词子集副本)。
加载期白名单校验(未知算子/函数/非零 tolerance → RulePackError 拒载);
执行期缺字段 → need_human,precondition 不成立 → [],判定失败 → violation + _tpl 渲染。
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.extensions.bid_review.engine.anchors import anchor_rule_paths
from app.extensions.bid_review.engine.attachments import match_attachments, normalize_name
from app.extensions.bid_review.engine.expr import ExprError, RulePackError, eval_expr, fields_used, validate_expr

_OPS = {"lte": operator.le, "gte": operator.ge, "eq": operator.eq}
_KNOWN_OPS = {*_OPS, "and", "or", "all", "set_eq", "att_check", "att_count", "att_missing_rows"}  # steps 形态无 op 键,单独判;att_* = L2 P1 附件核对(spec 2026-11-02 §3)+L2-023 指纹通道(spec 2026-11-04 §2.1);or = check-op 层析取(P1-β批二)
_UNIT_CN = {"day": "天", "month": "个月", "week": "周", "percent": "%"}


@dataclass
class Rule:
    id: str
    name: str
    layer: str
    type: str
    applies_to: list
    inputs: list
    check: dict
    severity: str
    evidence: list
    message_tpl: str
    fix_tpl: str
    confidence_gate: float
    enabled: bool


@dataclass
class RulePack:
    name: str
    version: str
    conventions: dict
    rules: list[Rule]


def _collect_exprs(chk: dict) -> list[str]:
    out = [str(chk[k]) for k in ("precondition", "left", "right", "target", "cond") if k in chk]
    for key in ("steps", "all", "any", "values"):  # any = or-op 表达式列表(P1-β批二),校验语义与 all 一致
        out += [str(e) for e in chk.get(key, [])]
    return out


def load_rulepack(path: str | Path) -> RulePack:
    """加载规则包;逐条 validate_expr 白名单校验,语法/函数/算子/tolerance 不合规 → RulePackError(拒载)。"""
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rules: list[Rule] = []
    for raw in data.get("rules", []):
        rid = str(raw.get("id", "?"))
        chk = raw.get("check") or {}
        op = chk.get("op")
        if op is not None and op not in _KNOWN_OPS:
            raise RulePackError(f"规则 {rid} 未知算子 {op}(白名单外,拒载)")
        if "steps" not in chk and op is None:
            raise RulePackError(f"规则 {rid} check 缺少 op/steps(形态不识别,拒载)")
        if "tolerance" in chk and float(chk["tolerance"]) != 0.0:
            raise RulePackError(f"规则 {rid} tolerance 仅接受 0.00(求值器不容差)")
        for e in _collect_exprs(chk):
            try:
                validate_expr(e)
            except ExprError as exc:
                raise RulePackError(f"规则 {rid} 表达式不合法 {e!r}: {exc}") from exc
        rules.append(
            Rule(
                id=rid,
                name=str(raw.get("name", "")),
                layer=str(raw.get("layer", "")),
                type=str(raw.get("type", "")),
                applies_to=list(raw.get("applies_to", ["*"])),
                inputs=list(raw.get("inputs", [])),
                check=chk,
                severity=str(raw.get("severity", "")),
                evidence=list(raw.get("evidence", [])),
                message_tpl=str(raw.get("message_tpl", "")),
                fix_tpl=str(raw.get("fix_tpl", "")),
                confidence_gate=float(raw.get("confidence_gate", 1.0)),
                enabled=bool(raw.get("enabled", True)),
            )
        )
    # 语义 lint(EAI-CUSTOM 2026-11-05 R1,spec §2.2):evidence 锚已注册/severity 层
    # 白名单/inputs 点路径——违规拒载(bug-3985:未注册锚曾静默丢证据区)。
    from app.extensions.bid_review.engine.registry import lint_rules

    problems = lint_rules(rules)
    if problems:
        raise RulePackError("规则包语义校验失败(拒载):\n" + "\n".join(problems))
    return RulePack(name=p.parent.name, version=p.stem, conventions=dict(data.get("conventions", {})), rules=rules)


def _fmt(v, spec=""):
    if spec == "money":
        return f"¥{float(v):,.2f}"
    if isinstance(v, list):  # 非标量渲染(评审修正 A6):L1-011 missing/extra 列表
        return "、".join(str(x) for x in v)
    if isinstance(v, dict) and "value" in v and "unit" in v:  # 工期 {value,unit} 结构(A6):L3-005
        unit = _UNIT_CN.get(str(v["unit"]).lower(), str(v["unit"]))
        return f"{v['value']}{unit}"
    return str(v)


def _resolve(name: str, fields: dict, env: dict):
    """与 expr._eval field 节点同序(评审修正 A7):全点平键 fields 优先 → 裸量词 var → 头段命中 env 属性链下钻 → KeyError。"""
    if name in fields:
        return fields[name]
    if name in env:
        return env[name]
    if "." in name:
        head, _, rest = name.partition(".")
        if head in env:
            cur = env[head]
            for seg in rest.split("."):
                if not isinstance(cur, dict) or seg not in cur:
                    raise KeyError(name)
                cur = cur[seg]
            return cur
    raise KeyError(name)


def _tpl(tpl: str, fields: dict, env: dict | None = None) -> str:
    env = env or {}

    def sub(m):
        path, spec = m.group(1), m.group(2) or ""
        try:
            v = _resolve(path, fields, env)
            if v is None:
                return ""  # None 不渲染 "None" 字面量(评审修正 A11a(2),与副本 eval_det.py 同规;空串按原文传递)
            return _fmt(v, spec)
        except Exception:
            return m.group(0)  # 解析失败保留占位(缺陷可见);测试以"无残留 {...} 占位"把关

    return re.sub(r"\{([\w.]+)(?::(\w+))?\}", sub, tpl)


def _val(x, fields: dict):
    if isinstance(x, str):
        return fields[x] if x in fields else eval_expr(x, fields)
    return x


def _issue(rule: Rule, fields: dict, extra: dict, env: dict | None = None) -> dict:
    msg = _tpl(rule.message_tpl, {**fields, **extra}, env)
    return {
        "rule_id": rule.id,
        "layer": rule.layer,
        "severity": rule.severity,
        "verdict": "violation",
        "need_human": False,
        "matched_expected": False,
        "message": msg,
        "fix": rule.fix_tpl,
        "evidence": [],
        "entity_keys": [],
        "source": "engine",
        "dedup_key": f"{rule.id}|-|{msg[:40]}",
    }


def _need_human(rule: Rule, msg: str) -> dict:
    return {
        "rule_id": rule.id,
        "layer": rule.layer,
        "severity": rule.severity,
        "verdict": "need_human",
        "need_human": True,
        "matched_expected": False,
        "message": msg,
        "fix": rule.fix_tpl,
        "evidence": [],
        "entity_keys": [],
        "source": "engine",
        "dedup_key": f"{rule.id}|-|missing",
    }


# C-11 附件要求行 src→severity 覆盖(整合版(D:\knowbase\技术知识库\投标方案审查_整合版.md)C-11 节,EAI-CUSTOM P1-β批一;裁决 A-β1-③:
# regulation 二义按保守侧 fatal;多行合并 issue 取映射最严档;未知/空 src 行不参与覆盖
# ——缺省=规则默认,golden 存量夹具(无 src)零回归;_need_human 产物不覆盖)。
_SRC_SEVERITY = {"tender_mandatory": "fatal", "tender_required": "major", "regulation": "fatal", "internal_template": "minor", "logical_necessary": "major"}
_SEVERITY_ORDER = ["info", "minor", "major", "fatal"]


def _src_severity(rows, default: str) -> str:
    mapped = [_SRC_SEVERITY[str(r.get("src") or "").strip()] for r in rows or [] if str(r.get("src") or "").strip() in _SRC_SEVERITY]
    return max(mapped, key=_SEVERITY_ORDER.index) if mapped else default


def _entity_key(req: dict) -> str:
    """附件实体键(L2 P2 D6):no 优先,无 no 用归一名称通道——跨层去重的归并依据。"""
    no = str(req.get("no") or "").strip()
    return f"attachment:{no}" if no else f"attachment:name:{normalize_name(req.get('name'))}"


def attach_evidence(issues: list[dict], rule: Rule, provenance: dict | None = None) -> list[dict]:
    """证据回填(EAI-CUSTOM 2026-10-30,spec D7/D9):抽取层 provenance ∩ 取数路径 →
    issue.evidence([{doc_id, page, section_path, text:quote}]),run_det_rule 保持纯函数
    不动;dedup_key 只由 rule_id+message 构成,证据不参与——补证据不会让旧问题重发。
    EAI-CUSTOM(2026-10-30 二期 spec §三):取数路径 = inputs ∪ 锚点映射路径
    (anchors.anchor_rule_paths)——det issue 证据 chips 更丰满;未注册锚名静默跳过。
    provenance 缺失/路径未命中 → 维持 [](前端回退「依据字段」chips;docx 无页码时
    page=null,定位走 quote 片段窗口——D8 诚实降级,不造假页码)。"""
    prov = provenance or {}
    if not prov:
        return issues
    paths = anchor_rule_paths(rule.evidence, rule.inputs)
    for issue in issues:
        ev = [{"doc_id": str(p["doc_id"]), "page": p.get("page"), "section_path": path, "text": str(p.get("quote") or "")} for path in paths if (p := prov.get(path))]
        if ev:
            issue["evidence"] = ev
    return issues


def run_det_rule(rule: Rule, fields: dict) -> list[dict]:
    """单条 det 规则执行:缺字段 → need_human;precondition 不成立 → [];判定失败 → violation。"""
    exprs = _collect_exprs(rule.check)
    missing = sorted({p for e in exprs for p in fields_used(e) if p not in fields})
    if not missing:
        missing = sorted(p for p in rule.inputs if p not in fields)
    if missing:
        return [_need_human(rule, f"字段缺失无法判定:{', '.join(missing)}(on_missing_input=need_human)")]
    issues: list[dict] = []
    chk = rule.check
    try:
        if "precondition" in chk and not eval_expr(str(chk["precondition"]), fields):
            return []  # 前置不成立=不适用,非问题
        if "steps" in chk:
            if not all(eval_expr(str(st), fields) for st in chk["steps"]):
                issues.append(_issue(rule, fields, {}))
        elif chk["op"] == "and":
            if not all(eval_expr(str(e), fields) for e in chk["all"]):
                issues.append(_issue(rule, fields, {}))
        elif chk["op"] == "or":  # check-op 层析取(P1-β批二):任一支成立即过;全支不成立=violation
            if not any(eval_expr(str(e), fields) for e in chk["any"]):
                issues.append(_issue(rule, fields, {}))
        elif chk["op"] == "all":  # 结构级全称量词(A7):行 dict 以 var 名并入 env,复用同一字段解析语义
            var = str(chk["var"])
            for row in _val(chk["target"], fields) or []:
                if not eval_expr(str(chk["cond"]), fields, {var: row}):
                    issues.append(_issue(rule, fields, {}, {var: row}))
        elif chk["op"] == "set_eq":
            lhs, rhs = set(_val(chk["left"], fields) or []), set(_val(chk["right"], fields) or [])
            miss, extra = sorted(rhs - lhs, key=str), sorted(lhs - rhs, key=str)
            if miss or extra:
                issues.append(_issue(rule, fields, {"missing": miss, "extra": extra}))
        elif chk["op"] in ("att_check", "att_count", "att_missing_rows"):  # L2 P1 附件核对(spec 2026-11-02 §3);P2:UNKNOWN→need_human+实体键(§7);L2-023 粗筛(spec 2026-11-04 §2.1)
            reqs, prov = _val(chk["left"], fields), _val(chk["right"], fields)
            if not isinstance(reqs, list) or not isinstance(prov, list):
                issues.append(_need_human(rule, "附件字段缺失或类型非法(need_human)"))
            else:
                out = match_attachments(reqs, prov)

                def _label(r: dict) -> str:
                    no = str(r.get("no") or "").strip()
                    return f"{no} {r.get('name')}" if no else str(r.get("name") or "")

                if chk["op"] == "att_check":
                    miss = [r for r in out["per_req"] if r["status"] == "MISSING"]
                    unknown = [r for r in out["per_req"] if r["status"] == "UNKNOWN"]
                    if miss:
                        iss = _issue(rule, fields, {"missing": [_label(r["req"]) for r in miss]})
                        iss["entity_keys"] = [_entity_key(r["req"]) for r in miss]
                        iss["severity"] = _src_severity([r["req"] for r in miss], rule.severity)  # C-11 行源覆盖(A-β1-③)
                        issues.append(iss)
                    for r in unknown:  # UNKNOWN 降 need_human,禁强行 PARTIAL/MISSING(spec §7)
                        # P3/P3.2 成因分流(spec 2026-11-03 §2,EAI-CUSTOM):行种类异构
                        # (平件/复合/grouping 三形态,键随形态有无)+引擎演进防漂移,消费一律 .get();
                        # 子行近似→逐子行 need_human 点名父件+子件+候选,grouping 孤儿另发,
                        # 两因不互吞;平件/grouping 措辞与 P3 逐字节一致(golden contains 回归面)。
                        subs_nm = [s for s in (r.get("sub_results") or []) if s.get("unknown_reason") == "near_miss"]
                        if subs_nm:
                            for s in subs_nm:
                                cands = (s.get("negative_evidence") or {}).get("closest") or []
                                c0 = cands[0] if cands else {}
                                cand_txt = f"{c0.get('no', '')} {c0.get('name', '')}".strip() or "无近似候选记录"
                                sim_txt = f"(相似度 {c0['sim']:.2f})" if c0.get("sim") is not None else ""
                                nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件「{_label(s)}」未精确命中,近似候选「{cand_txt}」{sim_txt},需人工核对")
                                nh["entity_keys"] = [_entity_key(s)]
                                nh["dedup_key"] = f"{rule.id}|-|{_entity_key(s)}"  # 按子行实体键派生(I-1 同规)
                                issues.append(nh)
                            # L2 混合态子件枚举(spec 2026-11-03 §1,EAI-CUSTOM):混合成因
                            # 父行(子近似+子真缺失)的真缺失子件逐个独立 need_human——
                            # P3.2 起仅近似子件成话,真缺失子件 issue 面零可见;与近似
                            # 子件同构点名,dedup 按子行实体键。纯增量,既有消息零改。
                            for s in r.get("sub_results") or []:
                                if s.get("status") != "MISSING":
                                    continue
                                nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件「{_label(s)}」缺失,需人工核对")
                                nh["entity_keys"] = [_entity_key(s)]
                                nh["dedup_key"] = f"{rule.id}|-|{_entity_key(s)}"  # 按子行实体键派生(I-1/P3.2 同规)
                                issues.append(nh)
                            if r.get("unknown_reason") == "grouping":  # 孤儿+子近似并存:两因各自成话
                                nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件无法自动分组,需人工核对")
                                nh["entity_keys"] = [_entity_key(r["req"])]
                                nh["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"
                                issues.append(nh)
                        elif r.get("unknown_reason") == "near_miss":
                            cands = (r.get("negative_evidence") or {}).get("closest") or []
                            c0 = cands[0] if cands else {}
                            cand_txt = f"{c0.get('no', '')} {c0.get('name', '')}".strip() or "无近似候选记录"
                            sim_txt = f"(相似度 {c0['sim']:.2f})" if c0.get("sim") is not None else ""
                            nh = _need_human(rule, f"附件「{_label(r['req'])}」未精确命中,近似候选「{cand_txt}」{sim_txt},需人工核对")
                            nh["entity_keys"] = [_entity_key(r["req"])]
                            nh["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"
                            issues.append(nh)
                        else:
                            nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件无法自动分组,需人工核对")
                            nh["entity_keys"] = [_entity_key(r["req"])]
                            nh["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"
                            issues.append(nh)
                elif chk["op"] == "att_missing_rows":
                    # L2-023 指纹通道粗筛(spec 2026-11-04 §2.1,EAI-CUSTOM):MISSING 行逐行
                    # violation 候选,交 hyb 规则卡模型确认(永不自动 MATCHED);UNKNOWN 行零
                    # 发声——近似行已有 L2-020 need_human 面,双规则重复=噪音。candidate_tpl
                    # 与 message_tpl 分离:候选消息用 {missing} 行标签,sem 侧终稿消息用
                    # {clause_id}/{reason}(两相渲染各用各的)。
                    cand_tpl = str(chk.get("candidate_tpl") or "附件「{missing}」未见于投标提供清单")
                    for r in out["per_req"]:
                        if r["status"] != "MISSING":
                            continue
                        label = _label(r["req"])
                        iss = _issue(rule, fields, {"missing": label})
                        iss["message"] = _tpl(cand_tpl, {**fields, "missing": label})
                        iss["dedup_key"] = f"{rule.id}|-|{iss['message'][:40]}"
                        iss["entity_keys"] = [_entity_key(r["req"])]
                        iss["severity"] = _src_severity([r["req"]], rule.severity)  # C-11 单行源覆盖(A-β1-③)
                        issues.append(iss)
                else:
                    partial = [r for r in out["per_req"] if r["status"] == "PARTIAL"]
                    if partial:
                        iss = _issue(
                            rule,
                            fields,
                            {"insufficient": [f"{_label(r['req'])}: 要求{r['req'].get('min_count')}份/提供{r['found']}份" for r in partial]},
                        )
                        iss["entity_keys"] = [_entity_key(r["req"]) for r in partial]
                        iss["severity"] = _src_severity([r["req"] for r in partial], rule.severity)  # C-11 行源覆盖(A-β1-③)
                        issues.append(iss)
        elif chk["op"] in _OPS:
            lhs, rhs = _val(chk["left"], fields), _val(chk["right"], fields)
            if not _OPS[chk["op"]](lhs, rhs):
                issues.append(_issue(rule, fields, {}))
        else:
            raise RulePackError(f"规则 {rule.id} 使用未支持算子 {chk['op']}")
    except KeyError as e:
        return [_need_human(rule, f"求值期字段缺失 {e}(need_human)")]
    return issues
