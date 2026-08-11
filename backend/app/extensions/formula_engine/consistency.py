"""跨章节 + 跨专业一致性校验引擎。

检查工程设计参数在以下维度的一致性：
  - 章节间：同一报告中，同一参数在不同章节的值必须一致
  - 专业间：不同专业报告中，同一参数的值必须一致（如给排水.消防水量 = 消防.消防给水）
  - 规范约束：设计值必须满足 GB/HG 等规范的范围要求
  - 公式链：公式计算结果必须等于下游公式的对应输入
  - 多规范矩阵：同一设计值对照多本规范/多条条款，产出围框矩阵（仅展示比对结果，不驱动单点 pass/fail）

设计原则：零漏报。每一条声明的一致性合约都会被评估，不抽样、不跳过。
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any, Callable


# ═══════════════════════════════════════════════════════════════════════════════
# 合约类型 — 五种一致性检查维度
# ═══════════════════════════════════════════════════════════════════════════════

class ContractType(str, enum.Enum):
    """一致性合约的五种类型。

    不同类型的合约有不同的数据来源和校验逻辑：
    - cross_section: 跨章节对比 → 检查同一参数在多个章节的值
    - cross_discipline: 跨专业对比 → 检查不同专业的同一参数
    - code_constraint: 规范约束 → 检查设计值是否满足 GB/HG 规范范围
    - formula_chain: 公式链校验 → 检查上游输出是否等于下游输入
    - code_constraint_multi: 多规范矩阵比对 → 仅产出围框矩阵，不驱动 check() 的 pass/fail
    """
    CROSS_SECTION = "cross_section"          # 同一参数在报告的多个章节中保持一致
    CROSS_DISCIPLINE = "cross_discipline"    # 同一参数在不同专业报告间保持一致
    CODE_CONSTRAINT = "code_constraint"      # 设计值必须满足规范要求范围
    FORMULA_CHAIN = "formula_chain"          # 公式计算结果必须等于下游输入值
    CODE_CONSTRAINT_MULTI = "code_constraint_multi"  # 多规范围框比对（反馈5，不驱动单 pass/fail）


class Severity(str, enum.Enum):
    """违规严重程度。

    - FAIL: 硬性阻断，不允许发布。如：跨章数据不一致、规范下限不满足。
    - WARN: 建议修正，不阻断。如：浓缩倍数低于推荐值但高于最低值。
    - PASS: 通过。
    """
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


# ═══════════════════════════════════════════════════════════════════════════════
# Contract — 一条一致性合约
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Contract:
    """一条一致性校验合约。

    合约定义了"什么参数应该在什么条件下保持一致"。
    引擎加载合约后，根据合约类型执行对应的校验逻辑。

    示例 — 跨章节一致:
        Contract(
            id="Q-cross-section",
            type=ContractType.CROSS_SECTION,
            param_name="Q",
            rule="exact_match",
            severity=Severity.FAIL,
            sources=[
                {"section": "3.1"},        # 设计规模章节中的 Q
                {"section": "6.1.1"},       # 蒸发水量计算中的 Q
            ],
            description="循环水量Q在设计和计算章节间必须一致",
        )

    示例 — 规范约束:
        Contract(
            id="volume-ratio-code",
            type=ContractType.CODE_CONSTRAINT,
            expression="V_system_V_system / Q",
            expected_min=0.333, expected_max=0.5,
            severity=Severity.FAIL,
            description="系统容积比应在1/3~1/2之间 (GB/T 50746 §6.1.9)",
        )
    """

    id: str                                          # 合约唯一标识
    type: ContractType                                # 合约类型
    description: str = ""                            # 人类可读说明
    severity: Severity = Severity.FAIL               # 违规严重程度（默认阻断）

    # ── CROSS_SECTION / CROSS_DISCIPLINE 专用字段 ──
    param_name: str = ""                             # 要检查的参数名
    sources: list[dict] = field(default_factory=list)  # 参数来源列表 [{section, discipline, value}]
    rule: str = "exact_match"                        # 匹配规则: exact_match | tolerance | tolerance_pct
    tolerance: float | None = None                   # 绝对容差（rule=tolerance 时生效）
    tolerance_pct: float | None = None               # 百分比容差（如 1.0 = 1%）

    # ── CODE_CONSTRAINT 专用字段 ──
    expression: str = ""                             # eval 表达式（可引用计算参数，点号自动转下划线）
    expected_min: float | None = None                # 下限（≥）
    expected_max: float | None = None                # 上限（≤）
    actual_value: float | None = None                 # 直接指定值（无表达式时使用）

    # ── CODE_CONSTRAINT_MULTI 专用字段 ──
    standards: list[dict] = field(default_factory=list)  # [{code, clause, min, max, severity, note}, ...]

    # ── FORMULA_CHAIN 专用字段 ──
    upstream_param: str = ""                         # 上游参数 "formula_id.output_name"
    downstream_param: str = ""                       # 下游参数 "formula_id.output_name"


# ═══════════════════════════════════════════════════════════════════════════════
# Violation — 一条违规记录
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Violation:
    """一次一致性违规的详细记录。"""
    contract_id: str       # 触发违规的合约 ID
    severity: Severity     # FAIL 或 WARN
    description: str       # 合约描述
    detail: str = ""       # 违规详情（含具体数值）
    expected: str = ""     # 期望值
    actual: str = ""       # 实际值


# ═══════════════════════════════════════════════════════════════════════════════
# ConsistencyEngine — 一致性校验引擎
# ═══════════════════════════════════════════════════════════════════════════════

class ConsistencyEngine:
    """一致性校验引擎。

    加载合约 → 注册参数 → 逐条校验 → 输出违规报告。

    使用流程:
        engine = ConsistencyEngine()

        # 1. 从 JSON 定义文件加载合约
        engine.load_contracts(contracts_json)

        # 2. 从 FormulaGraph 导入参数 + 手动注册跨专业参数
        engine.set_params_from_formula_graph(graph, discipline="water_drainage")
        engine.set_param("5.1", "消防水量", 120.0, discipline="fire_protection")

        # 3. 执行全部校验
        violations = engine.check()       # → [] 表示全部通过

        # 4. 生成结构化报告（含汇总统计）
        report = engine.check_report()
        # → {"summary": {"total": 11, "passed": 10, "failed": 1}, "violations": [...]}
    """

    def __init__(self) -> None:
        self._contracts: dict[str, Contract] = {}     # 合约注册表 {contract_id: Contract}
        self._param_table: dict[str, Any] = {}         # 参数表：多格式 key → value
        self._computed: dict[str, float] = {}           # 计算参数表（用于 code_constraint 表达式 eval）
        self._resolver: Callable[[str], float] | None = None  # 外部解析器（预留扩展点）

    # ═══════════════════════════════════════════════════════════════════
    # 合约管理
    # ═══════════════════════════════════════════════════════════════════

    def add_contract(self, contract: Contract) -> "ConsistencyEngine":
        """添加一条合约。返回 self 支持链式调用。"""
        self._contracts[contract.id] = contract
        return self

    def add_contracts(self, contracts: list[Contract]) -> "ConsistencyEngine":
        """批量添加合约。"""
        for c in contracts:
            self._contracts[c.id] = c
        return self

    def load_contracts(self, contracts_json: list[dict]) -> "ConsistencyEngine":
        """从 JSON 字典列表批量加载合约。

        这是从技能目录下的 consistency_contracts.json 加载合约的主要入口。
        JSON 中的点号表达式（如 "V_system.V_system / Q"）会在 eval 时自动转换。

        JSON 格式示例:
            [
                {
                    "id": "Q-cross-section",
                    "type": "cross_section",
                    "param_name": "Q",
                    "rule": "exact_match",
                    "severity": "fail",
                    "sources": [{"section": "3.1"}, {"section": "6.1.1"}],
                    "description": "循环水量Q在设计和计算章节间必须一致"
                },
                {
                    "id": "volume-ratio-code",
                    "type": "code_constraint",
                    "expression": "V_system_V_system / Q",
                    "expected_min": 0.333, "expected_max": 0.5,
                    "severity": "fail",
                    "description": "系统容积比应在1/3~1/2之间"
                }
            ]
        """
        for cdef in contracts_json:
            ctype = ContractType(cdef["type"])
            contract = Contract(
                id=cdef["id"],
                type=ctype,
                description=cdef.get("description", ""),
                severity=Severity(cdef.get("severity", "fail")),
                param_name=cdef.get("param_name", ""),
                sources=cdef.get("sources", []),
                rule=cdef.get("rule", "exact_match"),
                tolerance=cdef.get("tolerance"),
                tolerance_pct=cdef.get("tolerance_pct"),
                expression=cdef.get("expression", ""),
                expected_min=cdef.get("expected_min"),
                expected_max=cdef.get("expected_max"),
                upstream_param=cdef.get("upstream_param", ""),
                downstream_param=cdef.get("downstream_param", ""),
                standards=cdef.get("standards", []),
            )
            self._contracts[contract.id] = contract
        return self

    # ═══════════════════════════════════════════════════════════════════
    # 参数注册 — 将公式结果和手动指定的参数写入参数表
    # ═══════════════════════════════════════════════════════════════════

    def set_param(self, section: str, param_name: str, value: float, *,
                   discipline: str = "") -> "ConsistencyEngine":
        """注册一个参数值到参数表。

        key 格式（由参数决定）:
        - 跨章节检查（无 discipline）: "{section}.{param_name}"  → "3.1.Q"
        - 跨专业检查（有 discipline）: "{discipline}:{section}.{param_name}" → "water_drainage:5.1.消防水量"

        Args:
            section: 章节号（如 "3.1", "6.1.1"）
            param_name: 参数名（如 "Q", "消防水量"）
            value: 参数值
            discipline: 专业名称（如 "water_drainage", "fire_protection"），用于跨专业检查
        """
        key = f"{discipline}:{section}.{param_name}" if discipline else f"{section}.{param_name}"
        self._param_table[key] = value
        return self

    def set_params_from_formula_graph(self, graph, *,
                                       discipline: str = "",
                                       section_map: dict[str, str] | None = None) -> "ConsistencyEngine":
        """从 FormulaGraph 一键导入所有参数。

        自动注册两类参数：
        1. 公式输出 → key = "{discipline}:{section}.{output_name}"
           同时存入 _computed["formula_id.output_name"]（供 code_constraint 表达式引用）
        2. 用户输入 → key = 参数名本身（如 "Q", "N"），无章节前缀
           同时存入 _computed[param_name]

        Args:
            graph: 已 build + execute 的 FormulaGraph 实例
            discipline: 专业名称（如 "water_drainage"）
            section_map: 可选映射 {formula_id: section_number}，覆盖 FormulaNode 自带的 section
        """
        # 注册公式输出（带章节号 + 可选专业前缀）
        for fid, node in graph.nodes.items():
            section = (section_map or {}).get(fid, node.section)
            for oname, _unit in node.outputs.items():
                value = graph.get_param(fid, oname)
                if value is not None:
                    # 注册到参数表（供跨章节/跨专业检查使用）
                    key = f"{discipline}:{section}.{oname}" if discipline else f"{section}.{oname}"
                    self._param_table[key] = value
                    # 同时存入计算参数表（供 code_constraint 表达式 eval 使用）
                    self._computed[f"{fid}.{oname}"] = value

        # 注册用户输入参数（无章节号，直接使用参数名）
        for key, val in graph.get_all_params().items():
            if "." not in key:                     # 用户输入参数的特征：key 中不含 "."
                self._param_table[key] = val
                self._computed[key] = val
        return self

    # ═══════════════════════════════════════════════════════════════════
    # 校验入口 — 遍历全部合约，逐条执行
    # ═══════════════════════════════════════════════════════════════════

    def check(self) -> list[Violation]:
        """逐条执行所有注册的合约。返回违规列表。空列表 = 全部通过。

        每条合约根据其 type 字段自动路由到对应的校验方法。
        """
        violations: list[Violation] = []
        for contract in self._contracts.values():
            result = self._evaluate(contract)
            if result:
                violations.append(result)
        return violations

    def _evaluate(self, c: Contract) -> Violation | None:
        """根据合约类型路由到对应的校验方法。"""
        if c.type == ContractType.CROSS_SECTION:
            return self._check_cross_section(c)
        elif c.type == ContractType.CROSS_DISCIPLINE:
            return self._check_cross_discipline(c)
        elif c.type == ContractType.CODE_CONSTRAINT:
            return self._check_code_constraint(c)
        elif c.type == ContractType.CODE_CONSTRAINT_MULTI:
            return None  # 多规范矩阵由 multi_standard_matrix() 单独消费，不走单违规路径
        elif c.type == ContractType.FORMULA_CHAIN:
            return self._check_formula_chain(c)
        return None

    # ═══════════════════════════════════════════════════════════════════
    # 1) 跨章节一致性 — 同一参数在报告的多个章节中值是否一致
    # ═══════════════════════════════════════════════════════════════════

    def _check_cross_section(self, c: Contract) -> Violation | None:
        """校验同一参数在不同章节的值是否一致。

        示例: Q 在 §3.1、§6.1.1 两处出现，值必须完全相等（exact_match）。

        查找策略:
        - 对每个 source，按优先级尝试 3 种 key 格式查找参数值
        - key 格式: "discipline:section.param" > "section.param" > "param"
        - 至少需要 2 个有效值才能进行对比
        """
        values: list[tuple[str, float]] = []

        for src in c.sources:
            section = src.get("section", "")
            disc = src.get("discipline", "")

            # 按优先级尝试多种 key 格式查找参数值
            val = None
            for key in self._cross_section_keys(section, c.param_name, disc):
                if key in self._param_table:
                    val = float(self._param_table[key])
                    break

            # 回退：使用合约定义中的内联数值
            if val is None and "value" in src and src["value"] is not None:
                val = float(src["value"])

            if val is not None:
                label = f"{disc}:" if disc else ""
                label += f"{section}." if section else ""
                label += c.param_name
                values.append((label, val))

        # 至少需要 2 个值才能判断是否一致
        if len(values) < 2:
            return None

        # 以第一个值为基准，逐一对比后续值
        ref_val = values[0][1]
        for label, val in values[1:]:
            if not self._values_match(ref_val, val, c.rule, c.tolerance, c.tolerance_pct):
                return Violation(
                    contract_id=c.id,
                    severity=c.severity,
                    description=c.description,
                    detail=f"参数 '{c.param_name}': {values[0][0]}={ref_val}, {label}={val}",
                    expected=str(ref_val),
                    actual=f"{label}={val}",
                )
        return None

    # ═══════════════════════════════════════════════════════════════════
    # 2) 跨专业一致性 — 同一参数在不同专业报告中值是否一致
    # ═══════════════════════════════════════════════════════════════════

    def _check_cross_discipline(self, c: Contract) -> Violation | None:
        """校验不同专业报告中同一参数的值是否一致。

        这是跨专业数据共享的保障机制。
        示例: 给排水专业计算的消防水量必须等于消防专业引用的消防水量。

        与 _check_cross_section 的区别:
        - 对比维度是专业（discipline）而非章节（section）
        - key 格式包含专业前缀: "water_drainage:5.1.消防水量"
        """
        values: list[tuple[str, float]] = []
        for src in c.sources:
            disc = src.get("discipline", "")
            section = src.get("section", "")

            val = None
            for key in self._cross_section_keys(section, c.param_name, disc):
                if key in self._param_table:
                    val = float(self._param_table[key])
                    break

            if val is None and "value" in src and src["value"] is not None:
                val = float(src["value"])

            if val is not None:
                values.append((disc, val))

        if len(values) < 2:
            return None

        ref_val = values[0][1]
        for disc, val in values[1:]:
            if not self._values_match(ref_val, val, c.rule, c.tolerance, c.tolerance_pct):
                return Violation(
                    contract_id=c.id,
                    severity=c.severity,
                    description=c.description,
                    detail=f"参数 '{c.param_name}': {values[0][0]}={ref_val}, {disc}={val}",
                    expected=str(ref_val),
                    actual=f"{disc}={val}",
                )
        return None

    # ═══════════════════════════════════════════════════════════════════
    # 3) 规范约束 — 设计值是否满足 GB/HG 规范的范围要求
    # ═══════════════════════════════════════════════════════════════════

    def _resolve_actual(self, c: Contract) -> float | None:
        """解析合约的实际值：优先 expression eval，其次 actual_value，都无法则 None。

        被 _check_code_constraint（单标准）和 multi_standard_matrix（多标准）共用。
        """
        if c.expression:
            try:
                namespace = dict(self._computed)
                expr = re.sub(r'(\w+)\.(\w+)', r'\1_\2', c.expression)
                for key, val in list(namespace.items()):
                    namespace[key.replace(".", "_")] = val
                namespace["__builtins__"] = {}
                return float(eval(expr, namespace, {}))
            except Exception:
                return None
        if c.actual_value is not None:
            return c.actual_value
        return None

    def _check_code_constraint(self, c: Contract) -> Violation | None:
        """校验设计值是否满足规范要求（如 GB/T 50746, GB 50648 等）。

        取值方式（按优先级）:
        1. expression: eval 表达式，可使用 _computed 中的计算参数
           - 表达式中的点号自动转下划线（V_system.V_system → V_system_V_system）
           - 因为 Python eval 中 "." 是属性访问符，不能作为变量名
        2. actual_value: 直接指定的值

        示例:
            容积比 = V_system / Q = 3923.5 / 20000 = 0.196
            expected_min = 0.333 → 0.196 < 0.333 → FAIL
        """
        # 解析实际值（与 multi_standard_matrix 共用 _resolve_actual）
        actual = self._resolve_actual(c)
        if actual is None:
            return None                            # 无法计算 → 安全跳过（不阻塞）

        # 下限检查
        if c.expected_min is not None and actual < c.expected_min:
            return Violation(
                contract_id=c.id,
                severity=c.severity,
                description=c.description,
                detail=f"实际值 {actual:.4f} 低于下限 {c.expected_min}",
                expected=f"≥ {c.expected_min}",
                actual=str(round(actual, 4)),
            )
        # 上限检查
        if c.expected_max is not None and actual > c.expected_max:
            return Violation(
                contract_id=c.id,
                severity=c.severity,
                description=c.description,
                detail=f"实际值 {actual:.4f} 超过上限 {c.expected_max}",
                expected=f"≤ {c.expected_max}",
                actual=str(round(actual, 4)),
            )
        return None

    # ═══════════════════════════════════════════════════════════════════
    # 4) 公式链 — 上游输出必须等于下游输入
    # ═══════════════════════════════════════════════════════════════════

    def _check_formula_chain(self, c: Contract) -> Violation | None:
        """校验公式链的完整性——上游输出必须等于下游的对应输入。

        这是 DAG 计算链自洽性的验证。正常情况下应该永远通过
        （因为公式引擎在拓扑执行时自动传递了参数）。
        此检查用于发现序列化/反序列化或手动修改中间结果导致的异常。
        """
        upstream_val = self._computed.get(c.upstream_param)
        downstream_val = self._computed.get(c.downstream_param)
        if upstream_val is None or downstream_val is None:
            return None                            # 数据不足，跳过
        if not self._values_match(upstream_val, downstream_val, c.rule, c.tolerance, c.tolerance_pct):
            return Violation(
                contract_id=c.id,
                severity=c.severity,
                description=c.description,
                detail=f"{c.upstream_param}={upstream_val}, {c.downstream_param}={downstream_val}",
                expected=f"{c.upstream_param}={upstream_val}",
                actual=f"{c.downstream_param}={downstream_val}",
            )
        return None

    # ═══════════════════════════════════════════════════════════════════
    # 3b) 多规范矩阵 — 同一参数对照多本规范逐条判定（反馈5 围框比对）
    # ═══════════════════════════════════════════════════════════════════

    def multi_standard_matrix(self) -> list[dict]:
        """对所有 code_constraint_multi 合约求值，返回每参数×每规范的结果矩阵（反馈5 围框比对）。

        返回:
            [
              {
                "contract_id", "description", "actual"(当前值或 None),
                "standards": [
                  {"code","clause","min","max","actual","severity","passed","note"}, ...
                ]
              }, ...
            ]

        actual 为 None（表达式无法求值）时，每条 standard 的 passed=None（无法判定），
        供报告标【需人工对照规范】。
        """
        rows: list[dict] = []
        for c in self._contracts.values():
            if c.type != ContractType.CODE_CONSTRAINT_MULTI:
                continue
            actual = self._resolve_actual(c)
            std_results = []
            for std in c.standards:
                lo, hi = std.get("min"), std.get("max")
                passed = None if actual is None else True
                if actual is not None:
                    if lo is not None and actual < lo:
                        passed = False
                    if hi is not None and actual > hi:
                        passed = False
                std_results.append({
                    "code": std.get("code", ""),
                    "clause": std.get("clause", ""),
                    "min": lo, "max": hi, "actual": actual,
                    "severity": std.get("severity", "warn"),
                    "passed": passed,
                    "note": std.get("note", ""),
                })
            rows.append({
                "contract_id": c.id,
                "description": c.description,
                "actual": actual,
                "standards": std_results,
            })
        return rows

    # ═══════════════════════════════════════════════════════════════════
    # 辅助工具方法
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _cross_section_keys(section: str, param: str, discipline: str) -> list[str]:
        """生成参数查找 key 的优先级列表。

        查找顺序（优先级从高到低）:
        1. "{discipline}:{section}.{param}" — 带专业+章节前缀
        2. "{section}.{param}" — 仅带章节前缀
        3. "{param}" — 裸参数名（用户输入参数的格式）

        这个顺序确保：章节特定的参数值优先匹配，否则回退到全局用户输入值。
        """
        keys = []
        if discipline and section:
            keys.append(f"{discipline}:{section}.{param}")
        if section:
            keys.append(f"{section}.{param}")
        keys.append(param)
        return keys

    @staticmethod
    def _values_match(a: float, b: float, rule: str,
                       tolerance: float | None, tolerance_pct: float | None) -> bool:
        """判断两个浮点数是否满足给定的匹配规则。

        三种规则:
        - exact_match: a == b（浮点容差 1e-9，用于精确对比）
        - tolerance: |a-b| ≤ absolute_tolerance（用于有工程余量的对比）
        - tolerance_pct: |a-b|/|b|*100% ≤ percentage_tolerance（用于比例对比）

        示例:
            _values_match(120.0, 120.1, "tolerance", tolerance=1.0) → True
            _values_match(120.0, 130.0, "tolerance", tolerance=1.0) → False
        """
        if rule == "exact_match":
            return abs(a - b) < 1e-9
        if rule == "tolerance" and tolerance is not None:
            return abs(a - b) <= tolerance
        if rule == "tolerance_pct" and tolerance_pct is not None:
            if b == 0:
                return abs(a) < 1e-9
            return abs(a - b) / abs(b) * 100 <= tolerance_pct
        return abs(a - b) < 1e-9                  # 回退到精确匹配

    # ═══════════════════════════════════════════════════════════════════
    # 结构化报告
    # ═══════════════════════════════════════════════════════════════════

    def check_report(self) -> dict:
        """执行全部合约并生成结构化校验报告。

        返回格式:
            {
                "summary": {
                    "total_contracts": 11,         # 合约总数
                    "passed": 9,                    # 通过数
                    "failed": 1,                    # FAIL 严重度违规数
                    "warned": 1,                    # WARN 严重度违规数
                    "clean": false                  # 是否有任何违规（true = 全部通过）
                },
                "violations": [
                    {
                        "contract_id": "volume-ratio-code",
                        "severity": "fail",
                        "description": "系统容积比应在1/3~1/2之间",
                        "detail": "实际值 0.1962 低于下限 0.333",
                        "expected": "≥ 0.333",
                        "actual": "0.1962"
                    }
                ]
            }

        前端/下游系统可直接使用此报告展示校验结果。
        """
        violations = self.check()
        passed = len(self._contracts) - len(violations)
        failed = sum(1 for v in violations if v.severity == Severity.FAIL)
        warned = sum(1 for v in violations if v.severity == Severity.WARN)

        return {
            "summary": {
                "total_contracts": len(self._contracts),
                "passed": passed,
                "failed": failed,
                "warned": warned,
                "clean": len(violations) == 0,
            },
            "violations": [
                {
                    "contract_id": v.contract_id,
                    "severity": v.severity.value,
                    "description": v.description,
                    "detail": v.detail,
                    "expected": v.expected,
                    "actual": v.actual,
                }
                for v in violations
            ],
        }
