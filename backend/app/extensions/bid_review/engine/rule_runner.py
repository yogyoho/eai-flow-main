"""规则包加载 + det 执行(canonical;技能内 eval_det.py 为其无量词子集副本)。
加载期白名单校验(未知算子/函数/非零 tolerance → RulePackError 拒载);
执行期缺字段 → UNKNOWN,precondition 不成立 → [],判定失败 → FAIL(P1-β批三 五值域)+ _tpl 渲染。
"""

from __future__ import annotations

import hashlib
import json
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.extensions.bid_review.engine.anchors import anchor_rule_paths
from app.extensions.bid_review.engine.attachments import match_attachments, normalize_name
from app.extensions.bid_review.engine.expr import ExprError, RulePackError, eval_expr, fields_used, validate_expr
from app.extensions.bid_review.engine.verdicts import VERDICT_FAIL, VERDICT_UNKNOWN

_OPS = {"lte": operator.le, "gte": operator.ge, "eq": operator.eq}
# att_* = L2 P1 附件核对(spec 2026-11-02 §3)+L2-023 指纹通道(spec 2026-11-04 §2.1)+L2-052 年份连续性(P1-β批九 2026-11-08)
_KNOWN_OPS = {*_OPS, "and", "or", "all", "set_eq", "att_check", "att_count", "att_missing_rows", "att_year_span"}  # steps 形态无 op 键,单独判;or = check-op 层析取(P1-β批二)
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
    # EAI-CUSTOM 批十T1(A-β10-②③,2026-11-09):卡级 severity 偏离注记 {spec, reason}——
    # 声明生效 severity 偏离规格档 spec,载入期审计面(issue/payload 面零新增,引擎/LLM 消费
    # 零改动,已知偏离集反向钉=T2)。default None:不带键零扰动,既有全部构造点零影响。
    severity_override: dict | None = None


@dataclass
class RulePack:
    name: str
    version: str
    conventions: dict
    rules: list[Rule]
    # 包级 meta(A-续-⑥,P1-β批二续 T4):L4 包 counts_toward_bid_gate/max_issues_per_report/
    # gate_effect 的结构化消费契约;dataclass 默认字段须在尾部,core 包无 meta 键 → 空 dict
    # (现有单测构造 RulePack(...) 走默认值零破坏)。
    meta: dict = field(default_factory=dict)


def _collect_exprs(chk: dict) -> list[str]:
    out = [str(chk[k]) for k in ("precondition", "left", "right", "target", "cond") if k in chk]
    for key in ("steps", "all", "any", "values"):  # any = or-op 表达式列表(P1-β批二),校验语义与 all 一致
        for e in chk.get(key, []):
            if isinstance(e, dict):
                # EAI-CUSTOM 批六T4(A-β6-⑧,2026-11-08):steps dict 形态 {expr, precondition?,
                # optional?, message_tpl?, fix_tpl?, dedup_ent?}——expr/precondition 是表达式,
                # 入加载期校验+缺字段门;message_tpl/fix_tpl 是模板非表达式,不收集。
                # legacy 字符串 step 行为不变。
                # EAI-CUSTOM 批八T1(A-β8-③,2026-11-08):dict 分支收窄——dict 形态项仅 steps
                # 合法;all/any/values 的 dict 项由 _validate_list_items 载入期拒载(eval 面对三键
                # 只 str(e) 渲染垃圾串、values 无 op 消费),此处不再收集,静默收校验=校验面谎报覆盖。
                if key == "steps":
                    out += [str(e[k]) for k in ("precondition", "expr") if k in e]
            else:
                out.append(str(e))
    return out


_LIST_KEYS = ("steps", "all", "any", "values")


def _validate_list_items(chk: dict, rid: str) -> None:
    """EAI-CUSTOM 批七T3(A-β7-③)+批八T1(A-β8-③)载入期列表形态门(2026-11-08):
    - steps dict 形态项缺 expr 键 → 拒载(批七原门,文案逐字保留)。原态 load 静默放行,
      实评 run_det_rule str(st["expr"]) 才 KeyError → 伪装「求值期字段缺失 'expr'」
      need_human 错位降级,左移到 load,错误句式与既有载入门一致。
    - all/any/values 出现 dict 项 → 拒载(批八收窄):eval 面对三键列表只 str(e)
      (rule_runner :315 op:and / :318 op:or,dict 渲染垃圾串),values 更无任何 op 消费——
      静默放行=校验面谎报覆盖。文案含列表键名与规则 id。
    最小侵入:仅 load_rulepack 调用,执行路径零改动;存量包零触(现包四键全字符串项)。"""
    for key in _LIST_KEYS:
        for item in chk.get(key) or []:
            if not isinstance(item, dict):
                continue
            if key != "steps":
                raise RulePackError(f"规则 {rid} {key} 列表出现 dict 项(eval 面不消费 dict 形态,拒载)")
            if "expr" not in item:
                raise RulePackError(f"规则 {rid} steps dict 项缺少 expr(形态不合规,拒载)")


def _validate_severity_override(raw: dict, rid: str) -> None:
    """EAI-CUSTOM 批十T1(A-β10-②③,2026-11-09)载入期 severity_override 卡级注记形态门:
    注记语义=声明卡生效 severity 偏离规格档 spec;spec 是规格档注记,按全层并集校验、不按
    卡层收紧(层无关,A-β10-②)。左移律(bug-4260 同构,消息句式与 _validate_list_items
    同构):违规一律 load 期 RulePackError 拒载——非 dict 形态;spec 键缺失;spec 不在
    severity 域(域=registry.SEVERITY_BY_LAYER 全层并集复用,禁复制第二份字面集);reason
    缺失或剥空白后空;spec 与卡生效 severity 等值(等值注记=零信息噪声)。仅 load_rulepack
    调用,执行路径零改动;不带键 → None,存量包零触。registry 惰性导入镜像 lint_rules
    (依赖方向 rule_runner→registry 见 registry.py 头注,防环沿用既有惯例)。"""
    spec_note = raw.get("severity_override")
    if not isinstance(spec_note, dict):
        raise RulePackError(f"规则 {rid} severity_override 非 dict 形态(注记须 spec/reason,拒载)")
    from app.extensions.bid_review.engine.registry import SEVERITY_BY_LAYER

    domain = set().union(*SEVERITY_BY_LAYER.values())
    spec = spec_note.get("spec")
    if spec is None:
        raise RulePackError(f"规则 {rid} severity_override 缺少 spec 键(规格档缺失,拒载)")
    if str(spec) not in domain:
        raise RulePackError(f"规则 {rid} severity_override spec {spec!r} 不在 severity 域 {sorted(domain)}(域外值,拒载)")
    reason = spec_note.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise RulePackError(f"规则 {rid} severity_override reason 缺失或为空(空因注记不可审计,拒载)")
    if str(spec) == str(raw.get("severity", "")):
        raise RulePackError(f"规则 {rid} severity_override spec={spec!r} 与卡 severity 等值(等值注记为零信息噪声,拒载)")


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
        _validate_list_items(chk, rid)  # EAI-CUSTOM 批七T3+批八T1(A-β7-③/A-β8-③):steps dict 缺 expr、all/any/values dict 项左移到载入期拒载
        if "severity_override" in raw:
            # 批十T1(A-β10-②③):卡级注记载入门——带键即校验(显式 null 同按非 dict 拒),不带键零扰动
            _validate_severity_override(raw, rid)
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
                # 批十T1(A-β10-②③):浅拷贝防 yaml 锚别名跨卡共享同一注记对象
                severity_override=dict(raw["severity_override"]) if "severity_override" in raw else None,
            )
        )
    # 语义 lint(EAI-CUSTOM 2026-11-05 R1,spec §2.2):evidence 锚已注册/severity 层
    # 白名单/inputs 点路径——违规拒载(bug-3985:未注册锚曾静默丢证据区)。
    from app.extensions.bid_review.engine.registry import lint_rules

    problems = lint_rules(rules)
    if problems:
        raise RulePackError("规则包语义校验失败(拒载):\n" + "\n".join(problems))
    # meta 显式读(A-续-⑥):未知顶层键 load 期静默丢弃,meta 是激活任务的显式过滤契约锚,
    # 必须显式透传,不得依赖通用透传(没有)。
    return RulePack(name=p.parent.name, version=p.stem, conventions=dict(data.get("conventions", {})), rules=rules, meta=dict(data.get("meta") or {}))


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


def _dedup_key(rule: Rule, entity: dict | None) -> str:
    """A-β2-⑦(P1-β批二 2026-11-07;T4 质量轮 2026-11-07 canonical+有界):dedup_key 三层键
    ``{layer}|{rule_id}|{entity canonical json}``;entity=行 var 环境 env(op:all 时为
    {var: row}),无 env 用 "-"。canonical 序列化(sort_keys)保同内容不同键序跨 run 同键(I-2);
    有界截断:超 200 字符截断后接 ``#``+md5 前 12 位——models.dedup_key 为 String(256) 硬限,
    PG 不截断、超长直接 DataError 断整 run 持久化(I-1);200 预算 → 总长 ≈224 < 256,
    给 llm_runner "|confirm-failed" 组合留头寸;att_* 分支显式有界覆盖不受影响。仅正式
    FAIL(_issue)携带;_need_human 非正式违规不带键。消费方对键做不透明串比较
    (crud 查重/routers 版本 diff),换形不影响其逻辑。"""
    ent = json.dumps(entity, ensure_ascii=False, sort_keys=True, default=str) if entity else "-"
    if len(ent) > 200:
        ent = f"{ent[:200]}#{hashlib.md5(ent.encode('utf-8')).hexdigest()[:12]}"
    return f"{rule.layer}|{rule.id}|{ent}"


def _issue(rule: Rule, fields: dict, extra: dict, env: dict | None = None) -> dict:
    msg = _tpl(rule.message_tpl, {**fields, **extra}, env)
    return {
        "rule_id": rule.id,
        "layer": rule.layer,
        "severity": rule.severity,
        "verdict": VERDICT_FAIL,
        "need_human": False,
        "matched_expected": False,
        "message": msg,
        "fix": rule.fix_tpl,
        "evidence": [],
        "entity_keys": [],
        "source": "engine",
        "dedup_key": _dedup_key(rule, env),
    }


def _need_human(rule: Rule, msg: str, verdict: str = VERDICT_UNKNOWN) -> dict:
    return {
        "rule_id": rule.id,
        "layer": rule.layer,
        "severity": rule.severity,
        "verdict": verdict,
        "need_human": True,
        "matched_expected": False,
        "message": msg,
        "fix": rule.fix_tpl,
        "evidence": [],
        "entity_keys": [],
        "source": "engine",
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
    不动;dedup_key 为三层键(layer|rule_id|实体 canonical json,200 有界截断,见 _dedup_key),
    证据不参与——补证据不会让旧问题重发。
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
    """单条 det 规则执行:缺字段 → UNKNOWN,precondition 不成立 → [],判定失败 → FAIL(P1-β批三 五值域)。"""
    exprs = _collect_exprs(rule.check)
    # EAI-CUSTOM 批六T4(A-β6-⑧,2026-11-08):steps dict 声明的 optional 路径=可选域,缺席
    # 不咬 need_human 缺字段门(A-β6-⑧「夹具无新字段时行为不变」的唯一可达通路——门先于
    # precondition 执行,声明外的路径缺席仍照旧 need_human);实评缺席由 step 级 optional-skip
    # 关门,在场 None/[] 由 step 级 precondition 关门。未声明 optional 的规则两段门零变化。
    optional = {str(p) for st in rule.check.get("steps") or [] if isinstance(st, dict) for p in (st.get("optional") or [])}
    missing = sorted({p for e in exprs for p in fields_used(e) if p not in fields} - optional)
    if not missing:
        missing = sorted(p for p in rule.inputs if p not in fields and p not in optional)
    if missing:
        return [_need_human(rule, f"字段缺失无法判定:{', '.join(missing)}(on_missing_input=need_human)")]
    issues: list[dict] = []
    chk = rule.check
    try:
        if "precondition" in chk and not eval_expr(str(chk["precondition"]), fields):
            return []  # 前置不成立=不适用,非问题
        if "steps" in chk:
            # 字符串 step:既有单 issue 语义逐字节保留(任一失败→一条 rule 级 tpl,L1-008/L2-032 先例)
            str_steps = [str(st) for st in chk["steps"] if not isinstance(st, dict)]
            if str_steps and not all(eval_expr(e, fields) for e in str_steps):
                issues.append(_issue(rule, fields, {}))
            # EAI-CUSTOM 批六T4(A-β6-⑧,2026-11-08):dict step 形态——optional 路径缺席=不适用;
            # precondition 不成立=不适用(与 op 形态 precondition→[] 同语义);判定失败=FAIL,
            # per-step message_tpl/fix_tpl 独立成话(forms 判定独立消息,A-β6-⑧ 硬线「禁合并回
            # 单消息」);dedup_ent 声明独立实体键,双 step 同败时 dedup 键互异不互吞
            # (crud.upsert_issue 按 (task_id, dedup_key) 合并,同键第二条消息会被吞)。
            for st in chk["steps"]:
                if not isinstance(st, dict):
                    continue  # 字符串 step 已由上方 all() 判定
                if any(p not in fields for p in (st.get("optional") or [])):
                    continue  # 声明可选路径缺席 → step 不适用(旧夹具零扰动)
                pre = st.get("precondition")
                if pre is not None and not eval_expr(str(pre), fields):
                    continue  # 前置不成立=不适用,非问题
                if not eval_expr(str(st["expr"]), fields):
                    ent = st.get("dedup_ent")
                    iss = _issue(rule, fields, {}, {"step": str(ent)} if ent else None)
                    if st.get("message_tpl"):
                        iss["message"] = _tpl(str(st["message_tpl"]), fields)
                    if st.get("fix_tpl"):
                        iss["fix"] = str(st["fix_tpl"])
                    issues.append(iss)
        elif chk["op"] == "and":
            if not all(eval_expr(str(e), fields) for e in chk["all"]):
                issues.append(_issue(rule, fields, {}))
        elif chk["op"] == "or":  # check-op 层析取(P1-β批二):任一支成立即过;全支不成立=violation;空 any=violation(空 all=PASS,数学标准)
            if not any(eval_expr(str(e), fields) for e in chk["any"]):
                issues.append(_issue(rule, fields, {}))
        elif chk["op"] == "all":  # 结构级全称量词(A7):行 dict 以 var 名并入 env,复用同一字段解析语义
            var = str(chk["var"])
            for row in _val(chk["target"], fields) or []:
                if not eval_expr(str(chk["cond"]), fields, {var: row}):
                    iss = _issue(rule, fields, {}, {var: row})
                    # W9 匹配面(A-β2-⑦,P1-β批二):行级 entity_keys 取 name/no 结构化锚
                    # (禁 message 全文——样板词自由重叠会误折叠全部 L3-012);其余行键不取。
                    if isinstance(row, dict):
                        iss["entity_keys"] = [row[k].strip() for k in ("name", "no") if isinstance(row.get(k), str) and row[k].strip()]
                    issues.append(iss)
        elif chk["op"] == "set_eq":
            lhs, rhs = set(_val(chk["left"], fields) or []), set(_val(chk["right"], fields) or [])
            miss, extra = sorted(rhs - lhs, key=str), sorted(lhs - rhs, key=str)
            if miss or extra:
                issues.append(_issue(rule, fields, {"missing": miss, "extra": extra}))
        elif chk["op"] in ("att_check", "att_count", "att_missing_rows", "att_year_span"):  # L2 P1 附件核对(spec 2026-11-02 §3);P2:UNKNOWN→need_human+实体键(§7);L2-023 粗筛(spec 2026-11-04 §2.1);L2-052 年份连续性(P1-β批九 2026-11-08)
            reqs, prov = _val(chk["left"], fields), _val(chk["right"], fields)
            if not isinstance(reqs, list) or not isinstance(prov, list):
                issues.append(_need_human(rule, "附件字段缺失或类型非法(need_human)"))
            else:
                out = match_attachments(reqs, prov)

                def _label(r: dict) -> str:
                    no = str(r.get("no") or "").strip()
                    return f"{no} {r.get('name')}" if no else str(r.get("name") or "")

                if chk["op"] == "att_year_span":  # L2-052 附件年份连续性(P1-β批九 T1,A-β9-② 2026-11-08;镜像 att_* 家族)
                    # 参与门(②④):year_span 正整数(int 且非 bool)且状态∈{MATCHED,PARTIAL};其余零参与零发声
                    # ——MISSING/UNKNOWN 归 L2-020(att_check)/L2-023(att_missing_rows)属地,零双报。
                    for r in out["per_req"]:
                        n = r["req"].get("year_span")
                        if not (isinstance(n, int) and not isinstance(n, bool) and n > 0) or r["status"] not in ("MATCHED", "PARTIAL"):
                            continue
                        # ② 年份载体=命中提供行 name 的 4 位年份 token 集(负向后顾/前瞻防编号切片;
                        #    findall 同名全收——勘误② controller 裁,A-β9-②「token 集」原文,「2023及2025」双年均落),去重升序
                        years = sorted({int(y) for p in r["matched"] for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", str(p.get("name") or ""))})
                        if not years:  # ③ 零可解析年份(A-β6-③ v2)=need_human;实体键/dedup 与 att UNKNOWN 行同构
                            nh = _need_human(rule, f"附件「{_label(r['req'])}」命中行无一可解析年份(年份连续性无法自动核对),需人工确认")
                            nh["entity_keys"] = [_entity_key(r["req"])]
                            nh["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"
                            issues.append(nh)
                            continue
                        entries: list[str] = []  # ⑥ 同行两因不互吞:各自成条目合入同一条 violation(span_fail 列表;att_count insufficient 条目句式同构)
                        if len(years) < n:
                            entries.append(f"「{_label(r['req'])}: 要求{n}年/覆盖{len(years)}年」")
                        if years[-1] - years[0] + 1 != len(years):  # ② 连续性=无断档;不锚定截止日日历年(财年书写惯例异构=FP 源)
                            entries.append(f"「{_label(r['req'])}: 覆盖年份断档 {years[0]}-{years[-1]}」")
                        if not entries:
                            continue  # 合规行零发声
                        iss = _issue(rule, fields, {"span_fail": entries})
                        iss["entity_keys"] = [_entity_key(r["req"])]
                        iss["dedup_key"] = f"{rule.id}|-|{_entity_key(r['req'])}"  # 按要求行实体键派生(I-1 同规)
                        iss["severity"] = _src_severity([r["req"]], rule.severity)  # ⑤ C-11 单行源覆盖(A-β1-③)
                        issues.append(iss)
                elif chk["op"] == "att_check":
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
