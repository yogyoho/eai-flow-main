"""Condition and handler expressions.

Wire format (identical to warm-flow)::

    eq@@flag|4          variable ``flag`` equals 4 (numeric or string)
    gt@@amount|100      greater than
    like@@name|foo      contains
    default@@...        always true
    spel@@#{a == 1}     safe expression subset
    ${handler}          handler expression resolved from variables

The SpEL implementation is deliberately a *safe subset* built on :mod:`ast`:
no attribute access, no calls, no imports.  This keeps the public contract but
removes the arbitrary-code-execution surface of Spring EL.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

_CONDITION_PREFIXES = ("eq", "ge", "gt", "le", "like", "lt", "ne", "notLike")
_COMPARE = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "ge": operator.ge,
    "lt": operator.lt,
    "le": operator.le,
}
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos}
_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _compare(op: str, left: Any, right: str) -> bool:
    if op in ("like", "notLike"):
        result = right in str(left)
        return not result if op == "notLike" else result
    left_num, right_num = _as_number(left), _as_number(right)
    if left_num is not None and right_num is not None:
        return bool(_COMPARE[op](left_num, right_num))
    return bool(_COMPARE[op](str(left), right))


def _safe_eval(node: ast.AST, variables: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body, variables)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in {"true", "True"}:
            return True
        if node.id in {"false", "False"}:
            return False
        if node.id in {"null", "None"}:
            return None
        return variables.get(node.id)
    if isinstance(node, ast.BoolOp):
        values = [_safe_eval(value, variables) for value in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_safe_eval(node.operand, variables))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_safe_eval(node.left, variables), _safe_eval(node.right, variables))
    if isinstance(node, ast.Compare):
        left = _safe_eval(node.left, variables)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            if type(op) not in _CMP_OPS:
                return False
            right = _safe_eval(comparator, variables)
            if not _CMP_OPS[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_safe_eval(item, variables) for item in node.elts]
    if isinstance(node, ast.Dict):
        return {
            _safe_eval(k, variables): _safe_eval(v, variables) for k, v in zip(node.keys, node.values, strict=False)
        }
    if isinstance(node, ast.Subscript):
        value = _safe_eval(node.value, variables)
        key = _safe_eval(node.slice, variables)
        try:
            return value[key]
        except Exception:
            return None
    return None


def _spel(expression: str, variables: dict[str, Any]) -> Any:
    text = expression.strip()
    if text.startswith("#{") and text.endswith("}"):
        text = text[2:-1]
    text = text.strip()
    # Translate common SpEL boolean spellings.
    text = re.sub(r"\btrue\b", "True", text)
    text = re.sub(r"\bfalse\b", "False", text)
    text = re.sub(r"\bnull\b", "None", text)
    text = re.sub(r"\band\b", " and ", text)
    text = re.sub(r"\bor\b", " or ", text)
    text = re.sub(r"\bnot\b", " not ", text)
    text = text.replace("&&", " and ").replace("||", " or ")
    try:
        tree = ast.parse(text, mode="eval")
        return _safe_eval(tree, variables)
    except Exception:
        return None


def evaluate_condition(expression: str | None, variables: dict[str, Any] | None = None) -> bool:
    """Evaluate a warm-flow condition. Empty / ``default@@`` means *true*."""

    if not expression:
        return True
    variables = variables or {}
    expression = expression.strip()
    if expression.startswith("default@@"):
        return True
    if expression.startswith("spel@@"):
        return bool(_spel(expression[len("spel@@") :], variables))

    # Allow simple OR / AND composition for hand-written definitions.
    if "||" in expression:
        return any(evaluate_condition(part, variables) for part in expression.split("||"))
    if "&&" in expression:
        return all(evaluate_condition(part, variables) for part in expression.split("&&"))

    if "@@" not in expression:
        return bool(_spel(expression, variables))
    prefix, _, payload = expression.partition("@@")
    prefix = prefix.strip()
    if prefix not in _CONDITION_PREFIXES:
        return False
    if "|" not in payload:
        return False
    name, _, expected = payload.partition("|")
    name = name.strip()
    if name not in variables or variables.get(name) is None:
        return False
    return _compare(prefix, variables.get(name), expected.strip())


def resolve_handlers(expression: str | None, variables: dict[str, Any] | None = None) -> list[str]:
    """Resolve a handler expression into concrete handler ids."""

    if not expression:
        return []
    variables = variables or {}
    text = expression.strip()
    if text.startswith("spel@@"):
        value = _spel(text[len("spel@@") :], variables)
        if value is None:
            return []
        return _to_list(value)
    if "${" in text or "#{" in text:

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            value = variables.get(name)
            return "" if value is None else str(value)

        text = re.sub(r"\$\{([^}]+)\}", replace, text)
        text = re.sub(r"#\{([^}]+)\}", replace, text)
    return _to_list(text)


def _to_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_to_list(item))
        return result
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "undefined"}:
        return []
    return [item.strip() for item in re.split(r"[,;]|@@", text) if item.strip()]


def expression_label(expression: str | None) -> str:
    """Human readable label used by the designer / chart tooltips."""

    if not expression:
        return "默认分支"
    if expression.startswith("default@@"):
        return "默认分支"
    if expression.startswith("spel@@"):
        return expression[len("spel@@") :]
    prefix, _, payload = expression.partition("@@")
    if "|" in payload:
        name, _, expected = payload.partition("|")
        return f"{name} {prefix} {expected}"
    return expression
