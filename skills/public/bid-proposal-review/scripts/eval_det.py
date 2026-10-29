#!/usr/bin/env python3
"""bid-proposal-review M1 自审:det 规则求值器(副本,自包含分发;canonical 引擎在子系统 engine/expr.py)。

用法:
  python eval_det.py run  --fields fields.json --rules ../references/rules-det-subset.yaml --out issues.json [--md issues.md]
  python eval_det.py selftest
字段缺失 → need_human(不猜测不默认通过)。退出码:0 干净 / 3 有异常(need_human 或 violation)。
副本刻意不含表达式内量词(M1 七条用不到;all/any/every/exists 见 canonical expr.py)。

已知差异 vs canonical(子系统 engine/expr.py):
- 无 validate_expr 加载期白名单校验(未支持构造运行期直接 ExprError)
- 通配 ".attr" 为合并单 token;canonical 同源分词器带同一 eat('.') 死码,同步时须同样处理
- number_to_words 负数入参直接 raise;token 耗尽 = ExprError(不作 None 字面量)
- number_to_words 段间零(junction)规则:高位→低位装配,补零条件 = 已有输出且(本段<1000 或 上一已输出段末位为 0 或 中间跳过全零段);canonical 同步时须按同一规则处理
"""
from __future__ import annotations
import argparse, json, operator, re, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML: pip install pyyaml")

class ExprError(ValueError): ...

_BIN = {"<=": operator.le, ">=": operator.ge, "==": operator.eq, "!=": operator.ne,
        "<": operator.lt, ">": operator.gt, "in": lambda a, b: a in (b or [])}
_TOK = re.compile(r'\s*(>=|<=|==|!=|[-\w.]+|[\[\]*"\'(),<>])')

def _tokens(s):
    out, i = [], 0
    while i < len(s):
        m = _TOK.match(s, i)
        if not m:
            if s[i] == " ":
                i += 1
                continue
            raise ExprError(f"无法 tokenize: {s[i:]!r} @ {s!r}")
        out.append(m.group(1)); i = m.end()
    return out

def _resolve(name: str, fields: dict):
    if name in fields:
        return fields[name]
    if "." in name:  # var-attr(评审修正 A6):量词 var 头的点名,如 a.value
        head, _, rest = name.partition(".")
        if head in fields:
            cur = fields[head]
            for seg in rest.split("."):
                if not isinstance(cur, dict) or seg not in cur:
                    raise KeyError(name)
                cur = cur[seg]
            return cur
    raise KeyError(name)  # 上层捕获 → need_human

def _normalize_unit(v):
    if isinstance(v, dict):
        val, unit = float(v.get("value", 0)), str(v.get("unit", "day")).lower()
        if unit in ("month", "months", "月"):
            return val * 30  # 月按 30 日历天
        return val  # ponytail: 工作日/日历天换算口径未定,M1 仅同单位比较,v2 再定
    return float(v)

def _number_to_words(v):
    # 中文大写整数(取整到元,尾缀"整");ponytail: 亿内四位分段,角分/兆 v2
    # 质量评审修正:高位→低位装配(基线低位→高位 + 反转,使"零"错置到高位段之前,如 100001→零壹拾万壹元整)
    digits = "零壹贰叁肆伍陆柒捌玖"
    u_map = ["仟", "佰", "拾", ""]
    units = ["", "万", "亿"]
    n = int(round(float(v)))
    if n < 0:
        raise ExprError(f"number_to_words 不接受负数: {v!r}")  # 基线 while n: 对负数死循环(-1//10000==-1)
    if n == 0:
        return "零元整"
    def four(x):
        parts, zero = [], False
        for pos, d in enumerate(f"{x:04d}"):
            if d != "0":
                if zero and parts:
                    parts.append("零")
                zero = False
                parts.append(digits[int(d)] + u_map[pos])
            else:
                zero = True
        return "".join(parts)
    segs = []
    m = n
    while m:
        segs.append(m % 10000); m //= 10000
    out, prev, zero_skipped = [], None, False
    for idx in range(len(segs) - 1, -1, -1):  # 高位→低位
        x = segs[idx]
        if x == 0:
            zero_skipped = True  # 全零段被跳过,下一非零段前须补零(复审 I1:100004567)
            continue
        part = four(x)
        # 段间零(复审 I1 junction 规则):已有输出且(本段<1000 或 上一输出段末位为0 或 跳过过全零段);禁止前导零
        if out and (x < 1000 or prev % 10 == 0 or zero_skipped):
            part = "零" + part
        out.append(part + units[idx])
        prev, zero_skipped = x, False
    return "".join(out) + "元整"

def _fmt(v, spec=""):
    if spec == "money":
        return f"¥{float(v):,.2f}"
    if isinstance(v, list):  # 非标量渲染(评审修正 A6b):L1-011 missing/extra 列表
        return "、".join(str(x) for x in v)
    if isinstance(v, dict) and "value" in v and "unit" in v:  # 工期等 {value,unit} 结构(L3-005)
        unit = {"day": "天", "month": "个月", "week": "周", "percent": "%"}.get(str(v["unit"]).lower(), str(v["unit"]))
        return f"{v['value']}{unit}"
    return str(v)

def _tpl(tpl: str, fields: dict) -> str:
    def sub(m):
        # 基线 partition(m.group(1)) 永得空 spec(":"在组外非捕获);实测修正:spec 单独捕获为 group(2)
        # 复审 I2:\x00 哨兵+label 剪除实证有害(空 where 时吞金额数字),整体拆除;空串如实传递(双空格为可容忍如实渲染)
        path, spec = m.group(1), m.group(2) or ""
        try:
            v = _resolve(path, fields)
            if v is None:
                return ""  # None 不渲染 "None" 字面量——守卫必须在 _fmt 前(_fmt(None)→str(None)='None' 使后置守卫恒死码,s2 复审;与 rule_runner.py:130 同规)
            return _fmt(v, spec)
        except Exception:
            return m.group(0)
    return re.sub(r"\{([\w.]+)(?::(\w+))?\}", sub, tpl)

# ---- 单遍解释器(无量词;每个构造的 token 只消费一次,故单遍正确)----
class P:
    def __init__(self, toks, fields):
        self.t, self.i, self.f = toks, 0, fields
    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None
    def eat(self, x=None):
        tok = self.peek()
        if x is not None and tok != x:
            raise ExprError(f"期望 {x} 得 {tok}")
        self.i += 1
        return tok
    def expr(self):
        return self._or()
    def _or(self):
        v = self._and()
        while self.peek() == "or":
            self.eat(); v = v or self._and()
        return v
    def _and(self):
        v = self._cmp()
        while self.peek() == "and":
            self.eat(); v = v and self._cmp()
        return v
    def _cmp(self):
        v = self._atom()
        while self.peek() in _BIN:
            op = _BIN[self.eat()]
            v = op(v, self._atom())
        return v
    def _atom(self):
        tok = self.peek()
        if tok is None:  # token 耗尽(质量评审修正):必须 raise,禁止落到 str(tok)=="None" 当字面量(缺 RHS 求值 False → 误报)
            raise ExprError("表达式意外结束(token 耗尽)")
        if tok == "(":
            self.eat(); v = self.expr(); self.eat(")")
            return v
        if tok == "not":
            self.eat()
            return not self._atom()
        if str(tok) in ("null", "None"):
            self.eat()
            return None
        if tok in ("True", "False"):
            self.eat()
            return tok == "True"
        s = str(tok)
        if re.fullmatch(r"[-\d][\d.]*", s):
            self.eat()
            return float(s)
        if s[:1] in "'\"":
            self.eat()
            return s.strip("'\"")
        if re.fullmatch(r"[\w.-]+", s):
            self.eat()
            if self.peek() == "(":  # 函数调用(评审修正 A5)
                self.eat("(")
                args: list = []
                if self.peek() != ")":
                    args.append(self.expr())
                    while self.peek() == ",":
                        self.eat(","); args.append(self.expr())
                self.eat(")")
                if s not in _BUILTIN:
                    raise ExprError(f"未支持函数 {s}(白名单见 _BUILTIN)")
                return _BUILTIN[s](*args)
            if self.peek() == "[":  # 通配:bid.detail_rows[*].amount → 值列表
                self.eat("["); self.eat("*"); self.eat("]")
                nxt = str(self.eat())  # tokenizer 将 ".attr" 并为单个 token(实测修正:基线 eat(".") 永不匹配)
                sub = nxt[1:] if nxt.startswith(".") else nxt
                base = _resolve(s, self.f)
                return [row.get(sub) for row in (base or []) if isinstance(row, dict)]
            return _resolve(s, self.f)
        raise ExprError(f"意外 token {tok}")

def _eval_expr(expr: str, fields: dict):
    p = P(_tokens(expr), fields)
    v = p.expr()
    if p.peek() is not None:
        raise ExprError(f"尾随 token {p.peek()}")
    return v

_BUILTIN = {
    "normalize_unit": _normalize_unit,
    "number_to_words": _number_to_words,
    "codes": lambda rows: [r.get("code") for r in (rows or [])],
    "covers": lambda scope, need: str(need) in str(scope or ""),
    "keywords": lambda name: re.findall(r"[一-龥]{2,}", str(name or "")),
    "sum": lambda vals: float(sum(v for v in (vals or []) if isinstance(v, (int, float)))),
}

def _fields_used(expr: str) -> set:
    return {t for t in _tokens(expr) if re.fullmatch(r"(?:bid|tender|project)[\w.]*", t)}

def _collect_exprs(chk: dict) -> list:
    out = []
    for key in ("precondition", "left", "right", "target", "cond"):
        if key in chk:
            out.append(str(chk[key]))
    out += [str(e) for e in chk.get("steps", [])]
    out += [str(e) for e in chk.get("all", [])]
    out += [str(v) for v in chk.get("values", [])]
    return out

def _paths_missing(expr: str, fields: dict) -> list:
    return [p for p in _fields_used(expr) if p not in fields]

def _val(x, fields):
    if isinstance(x, str):
        return _resolve(x, fields) if x in fields else _eval_expr(x, fields)
    return x

def _need_human(rule, msg) -> dict:
    return {"rule_id": rule["id"], "layer": rule["layer"], "severity": rule["severity"],
            "verdict": "need_human", "need_human": True, "matched_expected": False,
            "message": msg, "fix": rule.get("fix_tpl", ""), "evidence": [],
            "source": "local-det", "dedup_key": f"{rule['id']}|-|missing"}

def _issue(rule, fields, extra) -> dict:
    msg = _tpl(rule["message_tpl"], {**fields, **extra})
    return {"rule_id": rule["id"], "layer": rule["layer"], "severity": rule["severity"],
            "verdict": "violation", "need_human": False, "matched_expected": False,
            "message": msg, "fix": rule.get("fix_tpl", ""), "evidence": [],
            "source": "local-det", "dedup_key": f"{rule['id']}|-|{msg[:40]}"}

def run_rule(rule: dict, fields: dict) -> list:
    missing = sorted({p for e in _collect_exprs(rule["check"]) for p in _paths_missing(e, fields)})
    if not missing:
        missing = sorted(p for p in rule["inputs"] if p not in fields)
    if missing:
        return [_need_human(rule, f"字段缺失无法判定:{', '.join(missing)}(on_missing_input=need_human)")]
    issues = []
    chk = rule["check"]
    try:
        if "precondition" in chk and not _eval_expr(chk["precondition"], fields):
            return []  # 前置不成立=不适用,非问题
        if "steps" in chk:
            if not all(_eval_expr(st, fields) for st in chk["steps"]):
                issues.append(_issue(rule, fields, {}))
        elif chk["op"] == "and":
            if not all(_eval_expr(e, fields) for e in chk["all"]):
                issues.append(_issue(rule, fields, {}))
        elif chk["op"] == "all":  # 结构级全称量词(非表达式内),如 L3-006
            var = chk["var"]
            for a in (_val(chk["target"], fields) or []):
                if not _eval_expr(chk["cond"], {**fields, var: a}):
                    issues.append(_issue(rule, fields, {var: a}))
        elif chk["op"] == "set_eq":
            l = set(_val(chk["left"], fields) or [])
            r = set(_val(chk["right"], fields) or [])
            miss, extra = sorted(r - l, key=str), sorted(l - r, key=str)
            if miss or extra:
                issues.append(_issue(rule, fields, {"missing": miss, "extra": extra}))
        elif chk["op"] in ("lte", "gte", "eq"):
            l, r = _val(chk["left"], fields), _val(chk["right"], fields)
            if not {"lte": operator.le, "gte": operator.ge, "eq": operator.eq}[chk["op"]](l, r):
                issues.append(_issue(rule, fields, {}))
        else:
            raise ExprError(f"规则 {rule['id']} 使用未支持算子 {chk['op']}")
    except KeyError as e:
        return [_need_human(rule, f"求值期字段缺失 {e}(need_human)")]
    return issues

def selftest():
    ok_fields = {
        "bid.total_price": 900000.0, "tender.max_price": 1000000.0,
        "bid.price_includes_tax": True, "tender.price_includes_tax": True,
        "bid.detail_rows": [{"code": "A", "amount": 900000.0}], "bid.subtotal": 900000.0,
        "bid.total_price_words": "玖拾万元整",
        "tender.boq_items": [{"code": "A"}, {"code": "B"}],
        "bid.boq_items": [{"code": "A"}, {"code": "B"}],
        "tender.project_identity.name": "某某工程", "tender.project_identity.code": "ZB-2026-001",
        "bid.header_footer.project_name": "某某工程",
        "bid.entity.license_name": "甲公司有限公司",
        "bid.entity.name_in_bid_letter": "甲公司有限公司",
        "project.entity_whitelist.names": ["甲公司有限公司"],
        "bid.duration_main_text": {"value": 180, "unit": "day"},
        "bid.duration_schedule": {"value": 180, "unit": "day"},
        "bid.duration_commitment_letter": {"value": 6, "unit": "month"},
        "bid.amount_occurrences": [{"where": "承诺函", "value": 900000.0}],
    }
    rules = yaml.safe_load((Path(__file__).parent.parent / "references" / "rules-det-subset.yaml").read_text(encoding="utf-8"))["rules"]
    by_id = {r["id"]: r for r in rules}
    clean = [i for r in rules for i in run_rule(r, ok_fields)]
    assert not clean, f"干净案应零问题,得 {clean}"
    bad = {**ok_fields, "bid.total_price": 1000001.0, "bid.subtotal": 999999.0,
           "bid.total_price_words": "壹佰万元整", "bid.boq_items": [{"code": "A"}],
           "bid.header_footer.project_name": "旧项目名",
           "bid.duration_commitment_letter": {"value": 3, "unit": "month"},
           "bid.entity.name_in_bid_letter": "甲公司"}  # L3-003 假阴 tripwire(质量评审)
    all_bad = [i for r in rules for i in run_rule(r, bad)]  # 评审修正 A6c
    got = {i["rule_id"] for i in all_bad}
    assert {"L1-009", "L1-010", "L1-011", "L3-001", "L3-003", "L3-005", "L3-006"} <= got, f"坏案应至少命中7条,得 {got}"
    for i in all_bad:
        assert not re.search(r"\{[\w.]+(?::\w+)?\}", i["message"]), f"残留占位符: {i['rule_id']} {i['message']}"
    l1009 = next(i for i in all_bad if i["rule_id"] == "L1-009")
    assert "¥1,000,001.00" in l1009["message"], f"money spec 回归: {l1009['message']}"  # _tpl spec 修复回归门(质量评审)
    # 复审 I1:junction 零回归门——全规则集跑 1004567.0 干净案(L1-010 step3 仅在大写恰为 conventional 形态时通过)
    jf = {**ok_fields, "tender.max_price": 2000000.0, "bid.total_price": 1004567.0,
          "bid.subtotal": 1004567.0, "bid.detail_rows": [{"code": "A", "amount": 1004567.0}],
          "bid.total_price_words": "壹佰万零肆仟伍佰陆拾柒元整",
          "bid.amount_occurrences": [{"where": "承诺函", "value": 1004567.0}]}
    j_issues = [i for r in rules for i in run_rule(r, jf)]
    assert not j_issues, f"junction 案(1004567.0)应零问题,得 {j_issues}"
    # 复审 I2:空 where 消息数字完整(哨兵拆除回归门)
    msg006 = run_rule(by_id["L3-006"], {**bad, "bid.amount_occurrences": [{"where": "", "value": 900000.0}]})[0]["message"]
    assert "¥900,000.00" in msg006 and "¥1,000,001.00" in msg006, f"L3-006 空 where 数字不完整: {msg006}"
    need = run_rule(by_id["L1-009"], {"bid.total_price": 1.0})
    assert need[0]["verdict"] == "need_human", "缺字段必须 need_human"
    # s2 复审:显式 None 值不渲染 "None" 字面量(守卫须在 _fmt 前;同 rule_runner.py:130)
    assert _tpl("{bid.none_field}", {"bid": {"none_field": None}}) == "", "None 不得渲染为 'None' 字面量"
    print("SELFTEST OK")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r1 = sub.add_parser("run")
    r1.add_argument("--fields", required=True)
    r1.add_argument("--rules", default=None)
    r1.add_argument("--out", required=True)
    r1.add_argument("--md", default=None)
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
        return
    rules_path = Path(a.rules) if a.rules else Path(__file__).parent.parent / "references" / "rules-det-subset.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))["rules"]
    fields = json.loads(Path(a.fields).read_text(encoding="utf-8"))
    issues = [i for r in rules for i in run_rule(r, fields)]
    Path(a.out).write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.md:
        n_fatal = sum(1 for i in issues if i["severity"] == "fatal" and i["verdict"] == "violation")
        n_human = sum(1 for i in issues if i["verdict"] == "need_human")
        lines = ["# 问题清单(det 自审)\n", f"- 致命: {n_fatal}", f"- 待人工: {n_human}\n"]
        for i in issues:
            lines.append(f"- **[{i['severity']}] {i['rule_id']}** {i['message']}\n  - 修复: {i['fix']}")
        Path(a.md).write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"issues": len(issues),
                      "need_human": sum(1 for i in issues if i["verdict"] == "need_human")}, ensure_ascii=False))
    sys.exit(0 if not issues else 3)

if __name__ == "__main__":
    main()
