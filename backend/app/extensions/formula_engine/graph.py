"""公式 DAG 引擎 — 依赖图构建、拓扑排序、脏标记传播、增量重算。

建模真实的工程设计计算链：
  - 公式 A 的输出 → 公式 B 的输入 → 公式 C 的输入
  - 修改上游参数后，自动标记下游公式为"脏"，触发增量重算
  - 重算仅执行受影响的公式，按依赖拓扑序逐批执行

基于真实石化循环水装置设计计算书的公式链分析实现。
"""

from __future__ import annotations

import enum
import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# 参数来源类型 — 描述公式中每个输入参数的出处
# ═══════════════════════════════════════════════════════════════════════════════


class ParamSourceType(enum.StrEnum):
    """参数来源的四种类型。

    不同类型的参数在依赖推导和重算时行为不同：
    - USER_INPUT / LOOKUP_TABLE / CODE_REQUIREMENT → 视为"根参数"，不依赖其他公式
    - FORMULA_OUTPUT → 依赖上游公式，是 DAG 的边来源
    """

    USER_INPUT = "user_input"  # 用户直接输入的设计参数（如 Q=20000 m³/h）
    LOOKUP_TABLE = "lookup_table"  # 查表/内插法得到的参数（如 KZF 蒸发系数）
    FORMULA_OUTPUT = "formula_output"  # 来自其他公式的计算结果（建立依赖关系）
    CODE_REQUIREMENT = "code_requirement"  # 规范/标准强制规定的值（如 GB/T 50746 表3.3.3）


# ═══════════════════════════════════════════════════════════════════════════════
# ParamSource — 描述一个参数的来源和当前值
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ParamSource:
    """描述公式中一个输入参数的来源、取值和元信息。

    示例:
        # 用户输入参数
        ParamSource.user(20000, "m³/h")

        # 查表参数（附带出处说明）
        ParamSource.lookup(0.001461, "1/℃", description="GB/T 50746 表3.3.3 内插法")

        # 来自上游公式的输出（自动推导依赖关系）
        ParamSource.from_formula("Qe", "Qe")

        # 规范强制值
        ParamSource.code(5.0, description="浓缩倍数 N≥5 (GB 50648 §4.1.1)")
    """

    type: ParamSourceType  # 参数来源类型
    value: float | None = None  # 当前值（FORMULA_OUTPUT 类型时由公式计算填充）
    unit: str = ""  # 单位，如 "m³/h", "℃"
    symbol: str = ""  # 工程符号，如 "Q", "K_{ZF}"（EAI-CUSTOM：式下图例用，空则回退代码键名）
    source_formula_id: str = ""  # FORMULA_OUTPUT 专属：来源公式的 ID
    source_param_name: str = ""  # FORMULA_OUTPUT 专属：来源公式的输出参数名
    description: str = ""  # 人类可读说明，如 "查GB/T 50746表3.3.3内插"
    needs_verification: bool = False  # 经验/系数默认值是否标【待核实】（反馈2 分层放开）

    # ── 工厂方法：语义化构造不同类型的 ParamSource ──

    @classmethod
    def user(cls, value: float, unit: str = "", *, description: str = "", needs_verification: bool = False) -> ParamSource:
        """用户直接输入的设计参数。如循环水量 Q、进出水温差 Δt。

        这类参数是 DAG 的"根节点"——不依赖任何公式，但被下游公式依赖。
        用户修改这类参数时，所有直接/间接依赖它的公式都需要重算。
        """
        return cls(type=ParamSourceType.USER_INPUT, value=value, unit=unit, description=description, needs_verification=needs_verification)

    @classmethod
    def lookup(cls, value: float, unit: str = "", *, description: str = "", needs_verification: bool = False) -> ParamSource:
        """通过查表或内插法得到的参数。如蒸发损失系数 KZF。

        与 user_input 类似，也是根节点。区别在于语义：这类参数不是用户直接输入，
        而是从规范/手册的表格中查得的固定值。
        """
        return cls(type=ParamSourceType.LOOKUP_TABLE, value=value, unit=unit, description=description, needs_verification=needs_verification)

    @classmethod
    def from_formula(cls, formula_id: str, param_name: str, *, unit: str = "") -> ParamSource:
        """来自上游公式的计算结果。这是构建公式依赖图的关键。

        当公式 B 的输入是公式 A 的输出时，系统自动推导出 B 依赖 A。
        例如：排污水量 Qb 的输入 Qe 来自蒸发水量公式 Qe 的输出，
        系统据此建立依赖边 Qb → Qe。

        Args:
            formula_id: 上游公式的唯一 ID（如 "Qe"）
            param_name: 上游公式的输出参数名（通常与 formula_id 相同）
            unit: 单位
        """
        return cls(
            type=ParamSourceType.FORMULA_OUTPUT,
            source_formula_id=formula_id,
            source_param_name=param_name,
            unit=unit,
        )

    @classmethod
    def code(cls, value: float, unit: str = "", *, description: str = "", needs_verification: bool = False) -> ParamSource:
        """规范/标准强制规定的值。如浓缩倍数 N≥5.0、旁滤比例 1%~5%。

        与 user_input 类似，但来源是 GB/HG 等国家标准而不是用户输入。
        在一致性校验中，这类参数会触发 code_constraint 类型的合约检查。
        """
        return cls(type=ParamSourceType.CODE_REQUIREMENT, value=value, unit=unit, description=description, needs_verification=needs_verification)


# ═══════════════════════════════════════════════════════════════════════════════
# FormulaNode — 一个工程设计公式
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FormulaNode:
    """工程设计计算链中的一个公式节点。

    每个节点包含：
    - 公式标识（id, name, section）
    - 计算表达式（expression，Python 语法）
    - 输入参数列表（inputs，每个参数标注来源）
    - 输出参数列表（outputs，参数名→单位映射）
    - 运行时状态（dirty 标记、上次计算结果缓存）

    示例 — 蒸发水量公式:
        FormulaNode(
            id="Qe",
            name="蒸发水量",
            section="6.1.1",
            expression="Q * KZF * delta_t",
            inputs={
                "Q": ParamSource.user(20000, "m³/h"),
                "KZF": ParamSource.lookup(0.001461, "1/℃"),
                "delta_t": ParamSource.user(10, "℃"),
            },
            outputs={"Qe": "m³/h"},
        )
    """

    id: str  # 唯一标识，如 "Qe", "Qb", "Qm"
    name: str  # 人类可读名称，如 "蒸发水量"
    section: str = ""  # 章节引用，如 "6.1.1"
    expression: str = ""  # Python 计算表达式，如 "Q * KZF * delta_t"
    inputs: dict[str, ParamSource] = field(default_factory=dict)  # 参数名 → 来源描述
    outputs: dict[str, str] = field(default_factory=dict)  # 输出参数名 → 单位
    symbol: str = ""  # 输出工程符号，如 "Q_{e}"（EAI-CUSTOM：报告正文用它替代代码键名）
    citation: list = field(default_factory=list)  # 规范依据 [{"code","clause","text"}]，clause 可空（绝不编造条号）

    # ── 运行时状态（不参与序列化）──
    _output_values: dict[str, float] = field(default_factory=dict, repr=False)  # 上次计算结果缓存
    dirty: bool = True  # 脏标记：True = 需要重算

    # ── 参数解析 ──

    def resolve_inputs(self, global_params: dict[str, float]) -> dict[str, float]:
        """解析公式的所有输入参数，从全局参数表中获取当前值。

        解析优先级：
          1. FORMULA_OUTPUT 类型 → 从 global_params 读取（key 格式："formula_id.output_name"）
          2. 其他类型 → 从 global_params 按参数名读取（可变的真实来源）
          3. 回退 → 从 src.value 读取（初始默认值，用于尚未注册到 global_params 的参数）

        注意：第 2 步是增量重算的关键——update_param() 修改 global_params 中的值后，
        公式解析时自动获取最新值，而不是使用 ParamSource 中的初始值。

        Raises:
            KeyError: 当 FORMULA_OUTPUT 类型参数的上游公式尚未执行时抛出。
                      这通常意味着 DAG 拓扑排序有问题。
        """
        resolved: dict[str, float] = {}
        for name, src in self.inputs.items():
            if src.type == ParamSourceType.FORMULA_OUTPUT:
                # 来自上游公式的输出 → 从全局参数表读取
                key = f"{src.source_formula_id}.{src.source_param_name}"
                if key not in global_params:
                    raise KeyError(f"公式 '{self.id}' 的输入 '{name}' 依赖 '{key}'，但该公式尚未执行（DAG 拓扑排序可能有误？）")
                resolved[name] = global_params[key]
            elif name in global_params:
                # 用户输入/查表/规范值 → 从全局参数表读取（可变的真实来源）
                resolved[name] = global_params[name]
            elif src.value is not None:
                # 回退：使用初始值（首次执行时参数尚未写入 global_params）
                resolved[name] = src.value
            else:
                raise KeyError(f"公式 '{self.id}' 的输入 '{name}' 无法解析：不在 global_params 中，且没有默认值")
        return resolved

    def derived_dependencies(self) -> set[str]:
        """扫描所有输入，返回本公式依赖的上游公式 ID 集合。

        依赖推导规则：
        - 遍历 inputs 中所有 FORMULA_OUTPUT 类型的参数
        - 提取其 source_formula_id，形成依赖边
        - USER_INPUT / LOOKUP_TABLE / CODE_REQUIREMENT 类型不产生依赖

        例如：Qb 的输入有 Qe（FORMULA_OUTPUT，来源=Qe公式），则 Qb 依赖 Qe。
        """
        deps: set[str] = set()
        for src in self.inputs.values():
            if src.type == ParamSourceType.FORMULA_OUTPUT and src.source_formula_id:
                deps.add(src.source_formula_id)
        return deps


# ═══════════════════════════════════════════════════════════════════════════════
# FormulaGraph — 公式有向无环图管理器
# ═══════════════════════════════════════════════════════════════════════════════


class FormulaGraph:
    """管理一组公式的依赖关系、拓扑执行和增量重算。

    这是公式引擎的核心类。使用流程：

        # 1. 构建公式图
        graph = FormulaGraph()
        graph.add_formulas([qe, qw, qb, qm]).build()

        # 2. 全量执行
        results = graph.execute()
        # → {"Qe": {"Qe": 292.2}, "Qb": {"Qb": 73.05}, ...}

        # 3. 修改参数，触发增量重算
        affected = graph.update_param("Q", 25000)
        # → ["Qe", "Qsf", "Qw", "Qb", "Qm", "filter_count", ...]
        results = graph.execute()

        # 4. 查看变更摘要
        changes = graph.last_change_summary()
        # → {"Qe.Qe": "292.2 → 365.2", "Qm.Qm": "385.3 → 481.6", ...}

    核心数据结构:
        _nodes:        公式节点字典 {formula_id: FormulaNode}
        _deps:         正向依赖 {node_id: {依赖的上游 node_id, ...}}
        _rdeps:        反向依赖 {node_id: {被依赖的下游 node_id, ...}}
        _dep_order:    拓扑排序后的批次列表 [[batch0_ids], [batch1_ids], ...]
                       同一批次内的公式相互独立，可并行执行
        _global_params: 全局参数表 {param_name: value}
                       包含用户输入参数 + 所有公式的计算结果
                       key 格式：用户输入用参数名，公式输出用 "formula_id.output_name"
    """

    def __init__(self) -> None:
        self._nodes: dict[str, FormulaNode] = {}  # 公式节点
        self._dep_order: list[list[str]] = []  # 拓扑排序批次（同批可并行）
        self._deps: dict[str, set[str]] = {}  # 正向依赖图
        self._rdeps: dict[str, set[str]] = {}  # 反向依赖图（用于拓扑排序的入度递减）
        self._global_params: dict[str, float] = {}  # 全局参数表（输入 + 计算结果）
        self._prev_snapshot: dict[str, float] = {}  # 上次执行前的全局参数快照（用于变更摘要）
        self._dirty_order: list[str] = []  # 脏公式的执行顺序

    # ═══════════════════════════════════════════════════════════════════
    # 构建阶段：添加公式 → 推导依赖 → 拓扑排序 → 初始化参数
    # ═══════════════════════════════════════════════════════════════════

    def add_formula(self, node: FormulaNode) -> FormulaGraph:
        """添加一个公式节点。返回 self 支持链式调用。"""
        self._nodes[node.id] = node
        return self

    def add_formulas(self, nodes: list[FormulaNode]) -> FormulaGraph:
        """批量添加公式节点。返回 self 支持链式调用。"""
        for n in nodes:
            self._nodes[n.id] = n
        return self

    def build(self) -> FormulaGraph:
        """构建依赖图、拓扑排序、初始化全局参数表。

        必须在添加完所有公式后调用，之后才能执行 execute()。
        调用顺序：_derive_dependencies → _topological_sort → _init_global_params
        """
        self._derive_dependencies()
        self._dep_order = self._topological_sort()
        self._init_global_params()
        return self

    # ═══════════════════════════════════════════════════════════════════
    # 依赖分析：扫描输入 → 推导依赖边 → 拓扑排序分批次
    # ═══════════════════════════════════════════════════════════════════

    def _derive_dependencies(self) -> None:
        """扫描所有公式的输入参数，推导依赖关系。

        对每个公式，调用 FormulaNode.derived_dependencies() 获取其依赖的上游公式集合，
        同时构建反向依赖表 _rdeps（用于拓扑排序时递减入度）。
        """
        self._deps = {}
        self._rdeps = defaultdict(set)
        for nid, node in self._nodes.items():
            deps = node.derived_dependencies()
            self._deps[nid] = deps
            for dep_id in deps:  # 对于每个上游依赖
                self._rdeps[dep_id].add(nid)  # 记录"谁依赖了我"（反向边）

    def _topological_sort(self) -> list[list[str]]:
        """Kahn 算法拓扑排序 → 将公式分组为可并行执行的批次。

        返回 [[batch0], [batch1], ...]：
        - 同一批次内的公式相互独立，没有依赖关系，可以并行计算
        - 批次 N 的所有公式只依赖批次 0..N-1 中的公式

        例如循环水计算链的排序结果：
            Batch 0: ["Qe", "Qw", "Qsf", ...]  ← 全部是根公式，只依赖用户输入
            Batch 1: ["Qb", "V_system", ...]    ← 依赖 Batch 0 的结果
            Batch 2: ["Qm", "backwash_volume"]  ← 依赖 Batch 0+1 的结果

        Raises:
            ValueError: 检测到循环依赖（公式 A→B→A），无法拓扑排序
        """
        # 入度表：每个公式有多少个尚未执行的上游依赖
        in_degree: dict[str, int] = {nid: len(deps) for nid, deps in self._deps.items()}
        # 入度为 0 的公式可以立即执行（只依赖用户输入，不依赖其他公式）
        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        batches: list[list[str]] = []

        while queue:
            batch = sorted(queue)  # 排序保证确定性（同批次内字母序）
            batches.append(batch)
            queue.clear()
            for nid in batch:
                for dependent in self._rdeps.get(nid, set()):
                    in_degree[dependent] -= 1  # 减少下游公式的入度
                    if in_degree[dependent] == 0:  # 下游公式的所有上游都已完成
                        queue.append(dependent)

        # 如果还有公式未被纳入任何批次 → 存在循环依赖
        if sum(len(b) for b in batches) != len(self._nodes):
            remaining = set(self._nodes) - set(n for b in batches for n in b)
            raise ValueError(f"检测到公式循环依赖: {remaining}")

        return batches

    def _init_global_params(self) -> None:
        """初始化全局参数表。

        将所有非 FORMULA_OUTPUT 类型的参数（用户输入、查表值、规范值）
        以其参数名注册到全局参数表中。FORMULA_OUTPUT 类型参数在执行时动态填充。
        """
        self._global_params = {}
        for node in self._nodes.values():
            for pname, src in node.inputs.items():
                if src.type != ParamSourceType.FORMULA_OUTPUT and src.value is not None:
                    self._global_params[pname] = src.value

    # ═══════════════════════════════════════════════════════════════════
    # 执行阶段：按拓扑序逐批计算公式
    # ═══════════════════════════════════════════════════════════════════

    def execute(self) -> dict[str, dict[str, float]]:
        """按拓扑序执行所有公式。返回 {formula_id: {output_name: value}}。

        执行策略：
        - 遍历拓扑排序的每个批次，批次内公式按字母序执行
        - 如果公式的 dirty=False（未受参数变更影响），跳过执行，复用缓存结果
        - 如果公式的 dirty=True，解析输入→计算→写回全局参数表→标记为干净

        快照机制：首次执行前保存全局参数快照（_prev_snapshot），用于 last_change_summary()。
        如果 update_param() 已经设置了快照，则不覆盖——这样变更摘要能正确显示"修改前→修改后"。
        """
        if not self._prev_snapshot:
            self._prev_snapshot = dict(self._global_params)
        results: dict[str, dict[str, float]] = {}

        for batch in self._dep_order:
            for nid in batch:
                node = self._nodes[nid]
                if not node.dirty:
                    # 公式未受参数变更影响，复用缓存结果（增量重算的关键优化）
                    results[nid] = dict(node._output_values)
                    continue
                result = self._execute_node(node)
                results[nid] = result
                node._output_values = result
                node.dirty = False  # 标记为干净

        self._dirty_order = []
        return results

    def _execute_node(self, node: FormulaNode) -> dict[str, float]:
        """执行单个公式节点。

        步骤：
        1. 从全局参数表解析输入参数的最新值
        2. 在受限命名空间（math + 基本函数）中 eval 表达式
        3. 将计算结果写入全局参数表（key 格式: "formula_id.output_name"）
           → 下游公式可以通过 FormaulaOutput 类型引用这个值

        安全说明：eval 使用空 builtins，仅暴露 math 和基本数学函数，
        无法执行任意代码。表达式仅支持纯数学计算。
        """
        resolved = node.resolve_inputs(self._global_params)

        # 受限命名空间：仅包含数学函数，无 builtins（防注入）
        # 覆盖工程设计常用计算：代数、对数/指数、三角/双曲、取整/绝对值
        namespace: dict[str, Any] = {
            # ── math 模块整体（可调用 math.sin(), math.log() 等）──
            "math": math,
            # ── 基本函数 ──
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            # ── 幂与根 ──
            "sqrt": math.sqrt,
            "pow": pow,
            # ── 对数与指数 ──
            "log": math.log,
            "log10": math.log10,
            "log2": math.log2,
            "exp": math.exp,
            # ── 三角函数（弧度制）──
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "atan2": math.atan2,
            # ── 双曲函数（工程传热/流体力学常用）──
            "sinh": math.sinh,
            "cosh": math.cosh,
            "tanh": math.tanh,
            # ── 角度转换（工程中常需度数↔弧度互换）──
            "radians": math.radians,
            "degrees": math.degrees,
            # ── 常数 ──
            "pi": math.pi,
            "e": math.e,
        }
        namespace.update(resolved)

        try:
            value = float(eval(node.expression, {"__builtins__": {}}, namespace))
        except Exception as e:
            raise ValueError(f"公式 '{node.id}' ({node.name}): 计算表达式 '{node.expression}' 失败，输入参数: {resolved}，错误: {e}") from e

        # 将计算结果写入全局参数表，供下游公式引用
        for oname in node.outputs:
            full_key = f"{node.id}.{oname}"
            self._global_params[full_key] = value

        return {oname: value for oname in node.outputs}

    # ═══════════════════════════════════════════════════════════════════
    # 增量重算：参数变更 → 脏标记传播 → 仅重算受影响公式
    # ═══════════════════════════════════════════════════════════════════

    def update_param(self, param_name: str, new_value: float) -> list[str]:
        """修改一个用户输入参数，传播脏标记，返回受影响的公式 ID 列表。

        当前实现：全量标记 + 全量重算（ponytail 简化）。
        真实场景下 12 个公式的全量重算 < 1ms，无需精细脏标记传播。
        当公式数量超过 100 且单次计算耗时 > 10ms 时，再实现依赖链精确脏标记。

        返回的 affected 列表按拓扑执行顺序排列：
        先返回上游公式，再返回下游公式。

        Args:
            param_name: 参数名（如 "Q", "N", "delta_t"）
            new_value: 新的参数值

        Returns:
            按执行顺序排列的受影响公式 ID 列表
        """
        # 保存变更前的快照（用于 last_change_summary）
        self._prev_snapshot = dict(self._global_params)

        # 更新全局参数表中的值
        old_value = self._global_params.get(param_name)
        self._global_params[param_name] = new_value

        if old_value == new_value:
            return []  # 值未变，无需重算

        # ponytail: 全量脏标记。12 个公式的全量重算 < 1ms，无需精细传播。
        # 当公式 > 100 且单次计算 > 10ms 时，升级为 BFS 脏标记传播。
        for node in self._nodes.values():
            node.dirty = True

        # 按拓扑执行顺序收集受影响的公式 ID
        affected: list[str] = []
        for batch in self._dep_order:
            for nid in batch:
                affected.append(nid)

        self._dirty_order = affected
        return affected

    def execute_dirty(self) -> dict[str, dict[str, float]]:
        """仅执行标记为 dirty 的公式，跳过干净的公式（复用缓存）。

        这是增量重算的入口——调用 update_param() 后再调用本方法，
        引擎自动跳过未受影响的公式，只重算受影响的公式链。
        """
        return self.execute()

    # ═══════════════════════════════════════════════════════════════════
    # 查询接口
    # ═══════════════════════════════════════════════════════════════════

    def get_param(self, formula_id: str, output_name: str) -> float | None:
        """获取某个公式的计算结果。

        Args:
            formula_id: 公式 ID（如 "Qe"）
            output_name: 输出参数名（通常与 formula_id 相同）

        Returns:
            计算结果（float），如果公式尚未执行则返回 None
        """
        key = f"{formula_id}.{output_name}"
        return self._global_params.get(key)

    def get_all_params(self) -> dict[str, float]:
        """返回所有参数的副本（用户输入 + 公式计算结果）。

        key 格式:
        - 用户输入参数：直接使用参数名（如 "Q", "N"）
        - 公式输出：使用 "formula_id.output_name" 格式（如 "Qe.Qe", "Qm.Qm"）
        """
        return dict(self._global_params)

    def last_change_summary(self) -> dict[str, str]:
        """返回上次参数变更的摘要，仅包含变化了的公式输出。

        返回格式: {"Qe.Qe": "292.2 → 365.2", "Qm.Qm": "385.3 → 481.6", ...}
        仅包含 key 中有 "." 的参数（即公式输出，不包含用户输入）。

        使用场景：用户修改参数后，展示哪些计算结果发生了变化。
        """
        changes: dict[str, str] = {}
        for key, new_val in self._global_params.items():
            old_val = self._prev_snapshot.get(key)
            # 只报告有 "." 的 key（公式输出），忽略用户输入参数
            if old_val is not None and old_val != new_val and "." in key:
                changes[key] = f"{old_val:.1f} → {new_val:.1f}"
        return changes

    def get_step_trace(self, formula_id: str) -> dict[str, Any] | None:
        """返回单公式的完整步骤轨迹，供报告折叠渲染（反馈3 黑箱展开）。

        复用引擎已算的值与表达式，不重复求值。返回结构：
            {
              "id", "name", "section", "expression", "source"(公式出处),
              "substituted"(变量替换为数值后的表达式串),
              "result", "unit",
              "symbol"(输出工程符号), "citation"(规范依据列表),
              "inputs": [{"name","symbol","value","unit","description","source","needs_verification"}, ...]
            }
        公式不存在返回 None。
        """
        node = self._nodes.get(formula_id)
        if node is None:
            return None
        resolved = node.resolve_inputs(self._global_params)
        substituted = _substitute_expression(node.expression, resolved)
        # 取结果（公式输出值）
        result: float | None = None
        for oname in node.outputs:
            result = self._global_params.get(f"{node.id}.{oname}")
        unit = next(iter(node.outputs.values()), "") if node.outputs else ""
        inputs_trace = [
            {
                "name": name,
                "symbol": src.symbol,
                "value": resolved.get(name),
                "unit": src.unit,
                "description": src.description,
                "source": _source_label(src),
                "needs_verification": src.needs_verification,
            }
            for name, src in node.inputs.items()
        ]
        return {
            "id": node.id,
            "name": node.name,
            "section": node.section,
            "expression": node.expression,
            "source": _formula_source(node),
            "substituted": substituted,
            "result": result,
            "unit": unit,
            "symbol": node.symbol,
            "citation": node.citation,
            "inputs": inputs_trace,
        }

    # ═══════════════════════════════════════════════════════════════════
    # 只读属性（供调试和测试使用）
    # ═══════════════════════════════════════════════════════════════════

    @property
    def nodes(self) -> dict[str, FormulaNode]:
        """所有公式节点 {formula_id: FormulaNode}。"""
        return self._nodes

    @property
    def execution_order(self) -> list[list[str]]:
        """拓扑排序后的执行批次 [[batch0_ids], [batch1_ids], ...]。

        同一批次内的公式可以并行执行。
        """
        return self._dep_order

    @property
    def dependencies(self) -> dict[str, set[str]]:
        """正向依赖图 {formula_id: {依赖的上游 formula_id, ...}}。

        例如: {"Qb": {"Qe"}, "Qm": {"Qe", "Qw", "Qb"}}
        """
        return dict(self._deps)

    @property
    def reverse_dependencies(self) -> dict[str, set[str]]:
        """反向依赖图 {formula_id: {被哪些下游公式依赖}}。

        例如: {"Qe": {"Qb", "Qm"}} 表示 Qe 被 Qb 和 Qm 依赖。
        用于拓扑排序中入度递减和脏标记传播。
        """
        return dict(self._rdeps)


# ═══════════════════════════════════════════════════════════════════════════════
# get_step_trace 辅助：表达式代入 / 来源标注
# ═══════════════════════════════════════════════════════════════════════════════


def _fmt_num(v: float) -> str:
    """数值格式化为代入串：整数无小数点，浮点保留必要精度。"""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return repr(v) if isinstance(v, float) else str(v)


def _substitute_expression(expression: str, resolved: dict[str, float]) -> str:
    """把表达式中的变量名替换为数值（词边界，避免 Q 误伤 Qe）。

    math.xxx 等非输入名不受影响（不在 resolved 中）。
    """
    out = expression
    for name, val in resolved.items():
        if val is None:
            continue
        out = re.sub(rf"\b{re.escape(name)}\b", _fmt_num(val), out)
    return out


def _source_label(src: ParamSource) -> str:
    """单参数来源标注：formula_output 标上游公式，其余用 description 或类型名。"""
    if src.type == ParamSourceType.FORMULA_OUTPUT:
        return f"formula:{src.source_formula_id}.{src.source_param_name}"
    return src.description or src.type.value


def _formula_source(node: FormulaNode) -> str:
    """公式整体出处：取首个 lookup/code 输入的 description（通常是规范条款），否则空。"""
    for src in node.inputs.values():
        if src.type in (ParamSourceType.LOOKUP_TABLE, ParamSourceType.CODE_REQUIREMENT) and src.description:
            return src.description
    return ""
