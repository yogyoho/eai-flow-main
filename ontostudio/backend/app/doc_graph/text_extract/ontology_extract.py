# EAI-CUSTOM: 环评样例 四类目标抽取（kernel P5 对接，2026-09-20 用户需求）——
# ① 章节结构（extract_outline 承担，chapter/section 实体化由调用方按 outline 树展开）
# ② 上下文逻辑链条（治理合规链 源→措施→标准→监测 + 影响链 源→污染物→敏感点）
# ③ 标准阈值/法规条款（GB/HJ/DB 标准号 + 限值 ≤X 单位 + 《法》第X条）
# ④ 业务节点佐证需求（表/图/公式/附件/流程图 引用）
#
# 词汇对齐 ontostudio registry eia.yaml（etype/谓词枚举）与 doc_graph EiaExtraction 域表；
# 输出为 ExtractionPayload(domain="eia") 兼容的 {entities, relations} 形态（name 引用）。
# 全部确定性正则/启发式（无 LLM 依赖），与 extract.py 抽取 MVP 同风格。

import re

ONTOLOGY_SCHEMA = "eia-sample-ontology/v1"

_SENT_SPLIT = re.compile(r"[。；]")

# ── ③ 标准号（GB/HJ/DB/T 系，3-5 位数字 + 可选年号）──
STANDARD_CODE = re.compile(r"(?<![A-Za-z0-9])((?:GB\s?|HJ\s?|DB\d{2}/|T/[A-Z]{2,4}\s?)(?:\d{3,5})(?:\.\d+)?)(?:[-—–](\d{4}))?")

# ── ③ 阈值：污染物 + 限值符 + 数值 + 单位（同一句内、邻近标准号时归入该标准）──
_POLLUTANT = r"(?:SO2|SO₂|NOx|NO₂|PM10|PM2\.5|颗粒物|二氧化硫|氮氧化物|化学需氧量|COD|氨氮|氟化物|总磷|总氮)"
THRESHOLD = re.compile(
    rf"({_POLLUTANT})[^。；]{{0,24}}?(≤|≥|不超过|不得超过|低于|小于|大于)\s*(\d+(?:\.\d+)?)\s*"
    r"(mg/m³|mg/m3|μg/m³|kg/d|t/a|mg/L|dB\(A\)|%)"
)

# ── ③ 法规条款：《法名》第X条 ──
REG_CLAUSE = re.compile(r"《([^》]{4,40})》第([一二三四五六七八九十百千\d]+条)")

# ── ② 链要素 ──
SOURCE_TERM = re.compile(r"([一-龥A-Za-z0-9]{2,10}(?:烟气|废气|废水|污水|噪声|扬尘|粉尘))")
TREAT = re.compile(
    r"(?:采用|配套|建设|经|通过|使用)[^。，；]{0,24}?(高效)?(旋风|布袋|脉冲|静电)?"
    r"(除尘器|脱硫塔|脱硫设施|脱硝设施|净化装置|污水处理站|综合处理设施|治理设施)"
)
MONITOR = re.compile(r"(连续监测|在线监测|例行监测|监测计划|按[^。，；]{0,12}(?:规范|标准|要求)[^。，；]{0,6}监测)")
EMIT = re.compile(r"([一-龥A-Za-z0-9]{2,8}(?:烟气|废气|废水))排放([一-龥]{1,8}(?:污染物|SO2|NOx|颗粒物))")
THREATEN = re.compile(r"(?:威胁|影响|涉及)([一-龥A-Za-z0-9]{2,16}?(?:保护区|水源地|村庄|学校|河流|湿地公园))")

# ── ④ 佐证引用 ──
EVIDENCE = re.compile(r"(见表\s?\d+(?:[-—–]\d+)?)|(见图\s?\d+)|(公式(?:（|\()\d+(?:）|\)))|(附件\s?\d+)|((?:工艺流程|治理工艺)流程图)")
EVIDENCE_KIND = [("table", "表"), ("figure", "图"), ("formula", "公式"), ("appendix", "附件"), ("flowchart", "流程图")]

_CHAIN_LEADS = ("采用", "配套", "建设", "经", "通过", "使用", "执行", "满足", "项目", "该", "本")


def _trim_chain_name(name: str) -> str:
    """链要素名去黏连：括号/标点/前导动词与泛指词。"""
    name = name.strip("（）()、，。;；:： \t　")
    for lead in _CHAIN_LEADS:
        if name.startswith(lead):
            name = name[len(lead) :]
    return name


def _std_entities_and_names(text: str) -> tuple[list[dict], list[str]]:
    """③ 标准号 → emission_standard 实体（去重、去内部空格）。"""
    entities, seen = [], []
    for m in STANDARD_CODE.finditer(text):
        code = re.sub(r"\s+", "", m.group(1))
        if code in seen:
            continue
        seen.append(code)
        entities.append(
            {
                "etype": "emission_standard",
                "name": code,
                "attrs": {"year": m.group(2) or ""},
                "confidence": 0.95,
            }
        )
    return entities, seen


def _threshold_entities(text: str, standards: list[str]) -> tuple[list[dict], list[dict]]:
    """③ 阈值：限值句 → standard_threshold 实体 + (标准 specifies_threshold 阈值) 关系。"""
    entities, relations = [], []
    for sent in _SENT_SPLIT.split(text):
        codes = [c for c in (re.sub(r"\s+", "", m.group(1)) for m in STANDARD_CODE.finditer(sent)) if c in standards]
        if not codes:
            continue
        for m in THRESHOLD.finditer(sent):
            pollutant, op, value, unit = m.group(1), m.group(2), m.group(3), m.group(4)
            name = f"{pollutant}{op}{value}{unit}"
            if any(e["name"] == name for e in entities):
                continue
            entities.append(
                {
                    "etype": "standard_threshold",
                    "name": name,
                    "attrs": {"pollutant": pollutant, "op": op, "value": value, "unit": unit},
                    "confidence": 0.85,
                }
            )
            for code in codes:
                relations.append({"predicate": "specifies_threshold", "subject": code, "object": name, "confidence": 0.85})
    return entities, relations


def _clause_entities(text: str) -> list[dict]:
    """③ 法规条款：《法名》第X条 → regulation_clause 实体。"""
    entities, seen = [], []
    for m in REG_CLAUSE.finditer(text):
        name = f"{m.group(1)}第{m.group(2)}"
        if name in seen:
            continue
        seen.append(name)
        entities.append(
            {
                "etype": "regulation_clause",
                "name": name,
                "attrs": {"law": m.group(1), "clause_no": m.group(2)},
                "confidence": 0.85,
            }
        )
    return entities


def _logic_chain_entities(text: str, standards: list[str]) -> tuple[list[dict], list[dict]]:
    """② 治理合规链：句内 (污染源 treated_by 措施 governed_by 标准 monitored_by 监测)。"""
    entities, relations = [], []
    seen: set[tuple[str, str]] = set()

    def _add(etype: str, name: str, confidence: float = 0.85) -> None:
        key = (etype, name)
        if key in seen:
            return
        seen.add(key)
        entities.append({"etype": etype, "name": name, "confidence": confidence})

    def _rel(pred: str, s: str, o: str) -> None:
        relations.append({"predicate": pred, "subject": s, "object": o, "confidence": 0.8})

    for sent in _SENT_SPLIT.split(text):
        sm = SOURCE_TERM.search(sent)
        if not sm:
            continue
        source = _trim_chain_name(sm.group(1))
        if not source:
            continue
        _add("pollution_source", source)
        tm = TREAT.search(sent)
        measure = ""
        if tm:
            measure = _trim_chain_name("".join(g for g in tm.groups() if g))
            if measure:
                _add("treatment_measure", measure)
                _rel("treated_by", source, measure)
        code = ""
        for m in STANDARD_CODE.finditer(sent):
            candidate = re.sub(r"\s+", "", m.group(1))
            if candidate in standards:
                code = candidate
                break
        if code and measure:
            _add("emission_standard", code, 0.95)
            _rel("governed_by", measure, code)
        if code and MONITOR.search(sent):
            monitoring = f"{code} 监测"
            _add("monitoring", monitoring, 0.8)
            _rel("monitored_by", code, monitoring)
    return entities, relations


def _impact_entities(text: str) -> tuple[list[dict], list[dict]]:
    """② 影响链：源 排放 污染物，污染物 威胁 敏感点 ⇒ 源 impact_to 敏感点。"""
    entities, relations = [], []
    seen: set[tuple[str, str]] = set()

    def _add(etype: str, name: str) -> None:
        key = (etype, name)
        if key in seen:
            return
        seen.add(key)
        entities.append({"etype": etype, "name": name, "confidence": 0.8})

    def _rel(pred: str, s: str, o: str) -> None:
        relations.append({"predicate": pred, "subject": s, "object": o, "confidence": 0.8})

    for sent in _SENT_SPLIT.split(text):
        pm = EMIT.search(sent)
        if not pm:
            continue
        src = _trim_chain_name(pm.group(1))
        pol = pm.group(2)
        if not src:
            continue
        _add("pollution_source", src)
        _add("pollutant", pol)
        _rel("emitted_as", src, pol)
        tm = THREATEN.search(sent)
        if tm:
            sp = tm.group(1)
            _add("sensitive_point", sp)
            _rel("threatens", pol, sp)
            _rel("impact_to", src, sp)
    return entities, relations


def _evidence_entities(text: str) -> list[dict]:
    """④ 佐证需求：表/图/公式/附件/流程图 引用 → evidence_requirement 实体。"""
    entities: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for m in EVIDENCE.finditer(text):
        for idx, (kind, _token) in enumerate(EVIDENCE_KIND, start=1):
            if not m.group(idx):
                continue
            ref = m.group(idx).strip()
            key = (kind, ref)
            if key in seen:
                break
            seen.add(key)
            entities.append(
                {
                    "etype": "evidence_requirement",
                    "name": ref,
                    "attrs": {"evidence_type": kind},
                    "confidence": 0.9,
                }
            )
            break
    return entities


def extract_ontology(text: str) -> dict:
    """四类目标抽取 → ExtractionPayload（domain="eia"）兼容的 {entities, relations} 形态.

    ① 章节结构由 extract_outline 承担（chapter/section 实体化由调用方按 outline 树展开）；
    本函数覆盖 ② 治理合规链+影响链 ③ 标准阈值+法规条款 ④ 佐证需求。
    关系谓词/实体 etype 与 eia.yaml 枚举严格同名（kernel loader 直读）。
    """
    std_entities, std_names = _std_entities_and_names(text)
    th_entities, th_relations = _threshold_entities(text, std_names)
    clause_entities = _clause_entities(text)
    chain_entities, chain_relations = _logic_chain_entities(text, std_names)
    impact_entities, impact_relations = _impact_entities(text)
    evidence_entities = _evidence_entities(text)

    # 装配级全局去重：跨函数 (etype, name) 重复只保留首见
    entities: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for e in std_entities + th_entities + clause_entities + chain_entities + impact_entities + evidence_entities:
        key = (e["etype"], e["name"])
        if key not in seen:
            seen.add(key)
            entities.append(e)
    relations = th_relations + chain_relations + impact_relations
    return {"schema": ONTOLOGY_SCHEMA, "entities": entities, "relations": relations}
