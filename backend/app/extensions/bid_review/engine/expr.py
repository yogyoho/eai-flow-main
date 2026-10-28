"""确定性规则 DSL:受限 AST 求值器(canonical;技能内 eval_det.py 为其无量词子集副本)。
白名单外算子/函数 = RulePackError(加载期拒载);未知字段 = KeyError(上层转 need_human);不 eval 任意字符串。
"""

from __future__ import annotations

import operator
import re


class ExprError(ValueError):
    pass


class RulePackError(ExprError):
    pass


_BIN = {"<=": operator.le, ">=": operator.ge, "==": operator.eq, "!=": operator.ne, "<": operator.lt, ">": operator.gt, "in": lambda a, b: a in (b or [])}
_FUNCS = {"normalize_unit", "number_to_words", "months_ago", "codes", "covers", "keywords", "sum", "count", "contains_any", "imply", "all_equal"}
_QUANT = {"all", "any", "every", "exists"}
_FORM2 = {"all": "all", "any": "any", "every": "all", "exists": "any"}
# 引号串整体成单 token(评审修正 A5/A6 实测:引号逐字符成 token 会撕裂 CJK 字面量,如 covers(x, '本次投标及签署'))
_TOK = re.compile(r'\s*(->|>=|<=|==|!=|"[^"]*"|\'[^\']*\'|[-\w.]+|[\[\]*"\'(),<>])')


def _tokens(s):
    out, i = [], 0
    while i < len(s):
        m = _TOK.match(s, i)
        if not m:
            raise ExprError(f"无法 tokenize: {s[i:]!r}")
        out.append(m.group(1))
        i = m.end()
    return out


class _P:
    def __init__(self, t):
        self.t, self.i = t, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def eat(self, x=None):
        tok = self.peek()
        if x is not None and tok != x:
            raise ExprError(f"期望 {x} 得 {tok}")
        self.i += 1
        return tok

    def expr(self):
        n = self._and()
        while self.peek() == "or":
            self.eat()
            n = ("or", n, self._and())
        return n

    def _and(self):
        n = self._cmp()
        while self.peek() == "and":
            self.eat()
            n = ("and", n, self._cmp())
        return n

    def _cmp(self):
        n = self._atom()
        while self.peek() in _BIN:
            n = (self.eat(), n, self._atom())
        return n

    def _atom(self):
        tok = self.peek()
        if tok is None:  # A11:token 耗尽必须 ExprError,禁止 str(None) 落成 None 字面量求值(截断表达式会静默翻转判定)
            raise ExprError("表达式意外结束(token 耗尽)")
        if tok == "(":
            self.eat()
            n = self.expr()
            self.eat(")")
            return n
        if tok == "not":
            self.eat()
            return ("not", self._atom())
        s = str(tok)
        if s in ("null", "None"):
            self.eat()
            return ("lit", None)
        if s in ("True", "False"):
            self.eat()
            return ("lit", s == "True")
        if re.fullmatch(r"[-\d][\d.]*", s):
            self.eat()
            return ("lit", float(s))
        if s[:1] in "'\"":
            self.eat()
            return ("lit", s.strip("'\""))
        if re.fullmatch(r"[\w.-]+", s):
            self.eat()
            if self.peek() == "(":  # 函数调用分发(评审修正 A5)
                return self._call(s)
            if self.peek() == "[":  # 通配:bid.detail_rows[*].amount → 值列表节点
                self.eat("[")
                self.eat("*")
                self.eat("]")
                nxt = self.peek()  # tokenizer 将 ".attr" 并为单 token(eat(".") 永不匹配)
                if nxt is None or not str(nxt).startswith("."):  # A11 收紧:[*] 后非 .attr token → ExprError(勿照抄副本容忍)
                    raise ExprError(f"[*] 后必须为 .attr,得 {nxt}")
                self.eat()
                return ("wild", s, str(nxt)[1:])
            return ("field", s)
        raise ExprError(f"意外 token {tok}")

    def _call(self, name):
        if name in _QUANT:
            return self._quant(name)
        if name not in _FUNCS:
            raise RulePackError(f"未知函数 {name}(白名单外,拒载)")
        self.eat("(")
        args = []
        if self.peek() != ")":
            args.append(self.expr())
            while self.peek() == ",":
                self.eat()
                args.append(self.expr())
        self.eat(")")
        return ("call", name, args)

    def _quant(self, name):
        self.eat("(")
        # 形态1: all/any(<list>, var -> body);形态2: every/exists(var in <list> [where cond] | , body)
        lookahead_in = len(self.t) > self.i + 1 and self.t[self.i + 1] == "in"
        if lookahead_in:
            var = self.eat()
            self.eat("in")
            lst = self.expr()
            if self.peek() == "where":
                self.eat()
                where = self.expr()
                self.eat(")")
                # exists(var in L where C) ≡ any(var in L, var -> C);every+where 同理取 all
                return ("quant", _FORM2[name], var, lst, where)
            self.eat(",")
            body = self.expr()
            self.eat(")")
            return ("quant", _FORM2[name], var, lst, body)
        lst = self.expr()
        self.eat(",")
        var = self.eat()
        self.eat("->")
        body = self.expr()
        self.eat(")")
        return ("quant", name, var, lst, body)


def parse(expr: str):
    p = _P(_tokens(expr))
    node = p.expr()
    if p.peek() is not None:
        raise ExprError(f"尾随 token {p.peek()}")
    return node


def validate_expr(expr: str) -> None:
    """加载期校验:语法错/未知函数在此抛出 → 拒载规则包。"""
    parse(expr)


def fields_used(expr: str) -> set:
    return {t for t in _tokens(expr) if re.fullmatch(r"(?:bid|tender|project)[\w.]*", t)}


def _normalize_unit(v):
    # fix-round(L1-014/L1-015/L3-005):*_text 命名的工期/质保字段若以原始文本回流("540日历天"),
    # 数值强转失败必须 raise KeyError(上层 run_det_rule 转 need_human 既有通路),禁止 ValueError
    # 逃逸——否则单字段类型偏差会让整条审查任务经 _infra_fail 重试 3 次后 failed(可用性失败)。
    try:
        if isinstance(v, dict):
            val, unit = float(v.get("value", 0)), str(v.get("unit", "day")).lower()
        else:
            val, unit = float(v), "day"
    except (TypeError, ValueError) as exc:
        raise KeyError(f"normalize_unit 无法数值化 {v!r}(需 {{value,unit}} 结构或天数数值)") from exc
    if unit in ("month", "months", "月"):
        return val * 30
    return val  # ponytail: 工作日/日历天换算口径 v2 定


def _number_to_words(v):
    # 中文大写整数(取整到元,尾缀"整");ponytail: 亿内四位分段准确,角分/兆 v2
    # A11 修正:高位→低位装配+段间零三条件(本段<1000 或 上一输出段末位为0 或 中间跳过过全零段),禁前导零;负数 raise(基线 while n: 对负数死循环)
    digits = "零壹贰叁肆伍陆柒捌玖"
    u_map = ["仟", "佰", "拾", ""]
    units = ["", "万", "亿"]
    n = int(round(float(v)))
    if n < 0:
        raise ExprError(f"number_to_words 不接受负数: {v!r}")
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
        segs.append(m % 10000)
        m //= 10000
    out, prev, zero_skipped = [], None, False
    for idx in range(len(segs) - 1, -1, -1):  # 高位→低位
        x = segs[idx]
        if x == 0:
            zero_skipped = True  # 全零段被跳过,下一非零段前须补零(100004567 → 壹亿零肆仟伍佰陆拾柒元整)
            continue
        part = four(x)
        if out and (x < 1000 or prev % 10 == 0 or zero_skipped):
            part = "零" + part
        out.append(part + units[idx])
        prev, zero_skipped = x, False
    return "".join(out) + "元整"


def _months_ago(deadline, months):
    # ISO 日期往前推 months 个月(有效期比较);M1 子集未用,v2 接入
    from datetime import date

    d = date.fromisoformat(str(deadline)[:10])
    y, mo = d.year - (int(months) // 12), d.month - (int(months) % 12)
    while mo <= 0:
        y, mo = y - 1, mo + 12
    return date(y, mo, min(d.day, 28)).isoformat()


_BUILTIN = {
    "normalize_unit": _normalize_unit,
    "number_to_words": _number_to_words,
    "months_ago": _months_ago,
    "codes": lambda rows: [r.get("code") for r in (rows or [])],
    "covers": lambda scope, need: str(need) in str(scope or ""),
    "keywords": lambda name: re.findall(r"[一-龥]{2,}", str(name or "")),
    "sum": lambda vals: float(sum(v for v in (vals or []) if isinstance(v, (int, float)))),
    "count": lambda vals: len(vals or []),
    "contains_any": lambda hay, needles: any(str(n) in str(hay or "") for n in (needles or [])),
    "imply": lambda a, b: (not a) or bool(b),
    "all_equal": lambda *vals: len({str(v) for v in vals}) <= 1,
}


def _eval(n, fields, env):
    k = n[0]
    if k == "lit":
        return n[1]
    if k == "field":
        key = n[1]
        if key in fields:  # 全点平键 fields 优先(评审修正 A7)
            return fields[key]
        if key in env:  # 裸量词 var
            return env[key]
        if "." in key:  # var-attr:头段命中 env(量词 var)则属性链下钻,任一段非 dict/缺键 → KeyError(A6/A7)
            head, _, rest = key.partition(".")
            if head in env:
                cur = env[head]
                for seg in rest.split("."):
                    if not isinstance(cur, dict) or seg not in cur:
                        raise KeyError(key)
                    cur = cur[seg]
                return cur
        raise KeyError(key)
    if k == "wild":
        base = fields.get(n[1])
        if base is None:
            raise KeyError(n[1])
        return [row.get(n[2]) for row in (base or []) if isinstance(row, dict)]
    if k == "and":
        return _eval(n[1], fields, env) and _eval(n[2], fields, env)
    if k == "or":
        return _eval(n[1], fields, env) or _eval(n[2], fields, env)
    if k == "not":
        return not _eval(n[1], fields, env)
    if k in _BIN:
        return _BIN[k](_eval(n[1], fields, env), _eval(n[2], fields, env))
    if k == "call":
        name, args = n[1], [_eval(a, fields, env) for a in n[2]]
        return _BUILTIN[name](*args)
    if k == "quant":
        _, q, var, lst_node, body = n
        out = []
        for item in _eval(lst_node, fields, env) or []:
            env[var] = item
            try:
                out.append(bool(_eval(body, fields, env)))
            finally:
                env.pop(var, None)
        return all(out) if q == "all" else any(out)
    raise ExprError(f"未知节点 {k}")


def eval_expr(expr: str, fields: dict, env: dict | None = None):
    """求值;env 为量词 var 绑定(Task 5 结构级 all 把行 dict 以 var 名并入 env,复用同一字段解析语义)。"""
    return _eval(parse(expr), fields, env or {})
