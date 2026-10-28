"""七道后处理校验管线(模型输出→入库之间必过,设计文档 §4.6)。

| # | 校验 | 不通过处置 |
|---|------|-----------|
| 1 | check_schema(raw) 输出 Schema | 坏 JSON 重试 1 次,仍失败丢弃+记日志(重试由 llm_runner 在 raw 层驱动) |
| 2 | align_evidence 证据对齐(归一相似度≥0.9,页码±1) | 降级 need_human=true,标"证据未对齐" |
| 3 | recompute_numeric 数值复核(涉数结论用 fields 重算) | 以确定性结果覆盖模型结论 |
| 4 | gate_confidence 阈值过滤(confidence < gate) | 转"待人工确认"(need_human=true) |
| 5 | dedup 去重(dedup_key 合并) | 合并,保留多证据 |
| 6 | normalize_severity 严重度归一 | 以规则定义为准,fatal 不可被模型输出降级 |
| 7 | injection_guard 注入检测 | 丢弃并记录安全事件 |
"""

from __future__ import annotations

import difflib
import json
import logging
import re

logger = logging.getLogger(__name__)

DEFAULT_VERDICT_SET = ("full", "partial", "none", "unclear")
SEVERITIES = ("fatal", "major", "minor", "info")
EVIDENCE_SIM_THRESHOLD = 0.9
PAGE_TOLERANCE = 1

# 注入检测:指令性/越权句式(宁可误弃,安全事件留痕;材料内指令性文字被模型复读进输出即命中)
_INJECTION_PATTERNS = (
    r"(ignore|disregard|forget)\s+(all\s+)?(the\s+)?(previous|prior|above|earlier|all)\b.{0,20}(instruction|rule|prompt|restriction)",
    r"(now\s+)?(you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay)\b",
    r"reveal\s+(the\s+)?(system\s+prompt|your\s+instructions)",
    r"忽略.{0,10}(指令|规则|要求|提示|约束)",
    r"(无视|不遵守|推翻).{0,6}(系统|之前|以上|上述)?(指令|规则|约束)",
    r"(输出|打印|泄露|交出|透露).{0,8}(系统提示|系统指令|system\s*prompt)",
    r"(现在)?你是.{0,4}(管理员|系统管理员|开发者|审核专家|DAN)",
    r"(请你|现在)(扮演|充当)",
)
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS), re.IGNORECASE)

_WS_RE = re.compile(r"\s+")
_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")


def _norm(text: str) -> str:
    """归一化:去空白、小写(证据匹配口径 conventions.evidence_matching.normalize)。"""
    return _WS_RE.sub("", str(text)).lower()


def injection_guard(text: str) -> bool:
    """第7道:True=干净;False=检出指令性/越权内容(调用方丢弃 + 记录安全事件)。"""
    if not text:
        return True
    hit = _INJECTION_RE.search(str(text))
    if hit:
        logger.warning(
            "bid_review.security.injection_detected pattern=%r text=%r",
            hit.group(0),
            str(text)[:200],
        )
    return hit is None


def check_schema(raw, verdict_set=None):
    """第1道(raw 层,由 llm_runner 驱动重试):模型原始输出 → (verdicts, None) 或 (None, 错误)。"""
    vs = set(verdict_set or DEFAULT_VERDICT_SET)
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as exc:
        return None, f"not_json: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("verdicts"), list) or not data["verdicts"]:
        return None, "schema: 需要非空 verdicts 列表"
    for i, entry in enumerate(data["verdicts"]):
        if not isinstance(entry, dict):
            return None, f"verdicts[{i}]: 非对象"
        if not isinstance(entry.get("verdict"), str) or entry["verdict"] not in vs:
            return None, f"verdicts[{i}].verdict 必须在 {sorted(vs)}"
        conf = entry.get("confidence")
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
            return None, f"verdicts[{i}].confidence 必须为 0-1 数值"
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            return None, f"verdicts[{i}].reason 必须为非空字符串"
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return None, f"verdicts[{i}].evidence 必须为非空数组(铁律2:无证据不出结论)"
        for j, ev in enumerate(evidence):
            if not isinstance(ev, dict) or not isinstance(ev.get("doc_id"), str) or not ev.get("doc_id"):
                return None, f"verdicts[{i}].evidence[{j}].doc_id 必须为非空字符串"
            page = ev.get("page")
            if isinstance(page, bool) or not isinstance(page, int) or page < 1:
                return None, f"verdicts[{i}].evidence[{j}].page 必须为正整数"
            if "text" in ev and not isinstance(ev.get("text"), str):
                return None, f"verdicts[{i}].evidence[{j}].text 必须为字符串"
        severity = entry.get("severity")
        if severity is not None and severity not in SEVERITIES:
            return None, f"verdicts[{i}].severity 必须在 {list(SEVERITIES)}"
    return data["verdicts"], None


def _page_text(doc, page) -> str:
    if not isinstance(doc, dict):
        return ""
    for key in (page, str(page)):
        if key in doc:
            return str(doc[key])
    return ""


def _similarity(needle_norm: str, hay_norm: str) -> float:
    """归一相似度:子串命中=1.0;否则按最长匹配块覆盖needle比例(difflib)。"""
    if not needle_norm:
        return 0.0
    if needle_norm in hay_norm:
        return 1.0
    matcher = difflib.SequenceMatcher(None, hay_norm, needle_norm)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(needle_norm)


def align_evidence(issue, docs_text, thr=EVIDENCE_SIM_THRESHOLD):
    """第2道:每条 evidence 的 text 须在 doc_id+page(±PAGE_TOLERANCE) 原文命中(归一相似度≥thr)。
    全部命中 True;任一失配 False(上层降级 need_human)。"""
    for ev in issue.get("evidence") or []:
        text = _norm(ev.get("text") or "")
        if not text:
            return False  # 无摘录=无证据,铁律2
        doc = docs_text.get(ev.get("doc_id")) if isinstance(docs_text, dict) else None
        page = ev.get("page")
        best = 0.0
        for offset in (-PAGE_TOLERANCE, 0, PAGE_TOLERANCE):
            hay = _norm(_page_text(doc, (page or 0) + offset))
            if hay:
                best = max(best, _similarity(text, hay))
                if best >= thr:
                    break
        if best < thr:
            return False
    return True


def _default_numeric_evaluator():
    """懒加载 Task 5 det 求值器基底;未落地/导入失败返回 None(不阻塞纯 sem 规则)。"""
    try:
        from app.extensions.bid_review.engine.rule_runner import eval_expr  # noqa: PLC0415 — 延迟依赖,Task 5 并行落地

        return eval_expr
    except Exception:  # noqa: BLE001 — 求值器缺席/签名演进一律降级
        return None


def recompute_numeric(issue, fields, evaluator=None):
    """第3道:涉数结论用已算字段重算。返回确定性 verdict("violation"/"pass")或 None(无从重算)。
    evaluator 可注入(测试 fake / 未来替换实现);缺省懒加载 engine.rule_runner.eval_expr,
    求值器缺席或表达式求值失败时返回 None,不覆盖模型结论。"""
    expr = issue.get("numeric_expr")
    if not expr:
        return None
    if evaluator is None:
        evaluator = _default_numeric_evaluator()
    if evaluator is None:
        return None
    try:
        det = evaluator(expr, fields)
    except Exception as exc:  # noqa: BLE001 — ExprError/字段缺失 → 不覆盖,由上层决定
        logger.info("bid_review.recompute_numeric.skipped expr=%s err=%s", expr, exc)
        return None
    return det if det in ("violation", "pass") else None


def gate_confidence(issue, rule):
    """第4道:confidence < rule.confidence_gate → 转"待人工确认"。返回是否通过。"""
    gate = float(rule.get("confidence_gate", 1.0))
    conf = issue.get("confidence")
    if isinstance(conf, (int, float)) and not isinstance(conf, bool) and conf < gate:
        issue["need_human"] = True
        issue.setdefault("notes", []).append(f"confidence {conf} 低于阈值 {gate},转待人工确认")
        return False
    return True


def evidence_keys(issue) -> str:
    """证据键集:去重键粒度取 doc_id 集合(同条款不同页可合并,多证据保留)。"""
    docs = {str(e.get("doc_id")) for e in issue.get("evidence") or [] if e.get("doc_id")}
    return ",".join(sorted(docs))


def build_dedup_key(issue, tpl=None) -> str:
    """conventions.dedup_tpl:{rule_id}|{clause_id or '-'}|{sorted(evidence_keys)}。"""
    if tpl:
        return tpl.format(
            rule_id=issue.get("rule_id"),
            clause_id=issue.get("clause_id") or "-",
            evidence_keys=evidence_keys(issue),
        )
    return f"{issue.get('rule_id')}|{issue.get('clause_id') or '-'}|{evidence_keys(issue)}"


def dedup(existing, issue, tpl=None):
    """第5道:dedup_key 相同 → 证据并入既有条目(保留多证据),返回 (既有条目, True);
    否则收编新条目,返回 (issue, False)。existing 为本轮已接受 issue 列表。"""
    key = issue.setdefault("dedup_key", build_dedup_key(issue, tpl))
    for prev in existing or []:
        if prev.get("dedup_key") == key:
            seen = {
                (e.get("doc_id"), e.get("page"), _norm(e.get("text") or ""))
                for e in prev.get("evidence") or []
            }
            for ev in issue.get("evidence") or []:
                token = (ev.get("doc_id"), ev.get("page"), _norm(ev.get("text") or ""))
                if token not in seen:
                    prev.setdefault("evidence", []).append(ev)
                    seen.add(token)
            return prev, True
    return issue, False


def normalize_severity(issue, rule):
    """第6道:严重度归一——以规则定义为准,模型输出的 severity 仅参考。
    fatal 不可被模型输出降级(模型侧原值留痕于 model_severity)。"""
    rule_severity = rule.get("severity", "major")
    model_severity = issue.get("model_severity")
    issue["severity"] = rule_severity
    if model_severity and model_severity != rule_severity:
        issue.setdefault("notes", []).append(
            f"模型侧 severity={model_severity} 与规则定义冲突,以规则定义为准"
        )
    return issue


def run_seven_checks(issue, rule, docs_text, fields, existing=None, evaluator=None):
    """第2-7道管线(第1道 schema 在 llm_runner raw 层驱动重试)。依次执行,
    失败处置按 §4.6 表;返回 (issue_or_merged, status)。
    status: accepted / merged(证据已并入既有条目) / refuted(确定性重算推翻) / discarded(注入丢弃)。"""
    notes = issue.setdefault("notes", [])

    # 第2道 证据对齐:失配 → 降级 need_human,标"证据未对齐"
    evidence_misaligned = not align_evidence(issue, docs_text)
    if evidence_misaligned:
        issue["need_human"] = True
        notes.append("证据未对齐:摘录与 doc_id+page±1 原文相似度不足")
        logger.warning("bid_review.verify.evidence_misaligned rule_id=%s clause=%s",
                       issue.get("rule_id"), issue.get("clause_id"))

    # 第3道 数值复核:以确定性结果覆盖模型结论
    det = recompute_numeric(issue, fields, evaluator)
    if det == "pass":
        notes.append("确定性重算未复现违规,模型结论被推翻")
        return issue, "refuted"
    if det == "violation" and issue.get("verdict") != "violation":
        notes.append("确定性重算坐实违规,覆盖模型结论")
        issue["verdict"] = "violation"
        if not evidence_misaligned:
            issue["need_human"] = False  # 仅解除 unclear 兜底旗标,不动证据未对齐降级

    # 第4道 置信门:低于 gate → 待人工确认
    gate_confidence(issue, rule)

    # 第7道(先于第5道执行:丢弃不得污染已合并条目;处置同 §4.6——丢弃+记录安全事件)
    blob = " ".join(
        filter(
            None,
            [issue.get("message") or "", issue.get("fix") or "",
             *[str(e.get("text") or "") for e in issue.get("evidence") or []],
             *notes],
        )
    )
    if not injection_guard(blob):
        logger.error("bid_review.security.injection_discarded rule_id=%s clause=%s",
                     issue.get("rule_id"), issue.get("clause_id"))
        return issue, "discarded"

    # 第5道 去重:同键合并,保留多证据
    merged, is_dup = dedup(existing or [], issue, rule.get("dedup_tpl"))
    if is_dup:
        return merged, "merged"

    # 第6道 严重度归一:fatal 不可被模型输出降级
    normalize_severity(merged, rule)
    return merged, "accepted"
