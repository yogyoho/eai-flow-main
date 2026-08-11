# 给排水单体计算书技能优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 7 条反馈落到 `skills/public/water-drainage-report`：提速（章节并行/增量）、分层放开默认值、计算过程折叠外显、校验面板、多规范围框比对、改参定点热更新、会话级快照——全部不改 deer-flow harness 核心。

**Architecture:** 计算与生成分离（Approach A）。公式引擎（`app/extensions/formula_engine`，EAI app 层）先出全部数值 + 步骤轨迹 + 受影响集；报告拆章节（table 机械渲染 / narrative 子 agent 并行，共享冻结快照）；改参只重生成受影响章节；会话快照跨轮承接。新增 2 个引擎能力（`get_step_trace` / `code_constraint_multi`）、2 个 runner 子命令（`trace`/`impacted`）、1 个章节规划脚本、4 个数据 json、SKILL.md 流程重写。

**Tech Stack:** Python 3.12（app/extensions 纯 stdlib 引擎 + skill 脚本）、pytest、JSON 数据层、Markdown + KaTeX 报告、LangGraph 子 agent 池（仅调用不修改）。

**硬约束（不可违反）：**
- 不改 `backend/packages/harness/deerflow/`（harness 核心）。全部代码落在 `app/extensions/formula_engine` + `skills/public/water-drainage-report` + `backend/tests`。`app/extensions/formula_engine` 是 EAI 自有 app 层，不算 harness，无需 EAI-CUSTOM 三重注释。
- 所有提交到 `main-dev-fork` 分支，不提交 `main`。
- web_search 不驱动合规 pass/fail（仅 discovery），合规限值人工入库（Tier-1）。

**上游 spec：** `docs/superpowers/specs/2026-08-11-water-drainage-report-optimization-design.md`（commit `39cad4775`）。本计划是其执行分解。

**测试运行方式（所有引擎/脚本测试统一）：**
```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py -v
```
引擎（`graph.py`/`consistency.py`）只依赖 stdlib，runner/chapter_planner 通过 `PYTHONPATH=.`（从 `backend/` 起）解析 `app.extensions.formula_engine`。

---

## File Structure（改动地图）

| 文件 | 责任 | 动作 |
|---|---|---|
| `backend/app/extensions/formula_engine/graph.py` | DAG 引擎 | 改：`ParamSource` 加 `needs_verification`；新增 `FormulaGraph.get_step_trace` |
| `backend/app/extensions/formula_engine/consistency.py` | 一致性引擎 | 改：`ContractType.CODE_CONSTRAINT_MULTI`；`Contract.standards`；`load_contracts` 透传；抽 `_resolve_actual`；新增 `multi_standard_matrix` |
| `backend/tests/test_formula_graph.py` | 引擎测试 | 改：加 `TestNeedsVerification` / `TestGetStepTrace` / `TestMultiStandardMatrix` |
| `skills/public/water-drainage-report/references/formulas.json` | 公式定义 | 改：系数/经验类 input 加 `needs_verification` + 拆 `source` |
| `skills/public/water-drainage-report/references/reference_values.json` | 行业经验参考值库 | 新建 |
| `skills/public/water-drainage-report/references/standards_index.json` | 可勾选规范清单 | 新建 |
| `skills/public/water-drainage-report/references/consistency_contracts.json` | 一致性合约 | 改：加 `code_constraint_multi` 合约 |
| `skills/public/water-drainage-report/scripts/formula_runner.py` | 公式 CLI | 改：`build_graph` 透传 `needs_verification`；新增 `cmd_trace` / `cmd_impacted` 子命令 |
| `skills/public/water-drainage-report/scripts/chapter_planner.py` | 章节规划 | 新建：`build_manifest` / `impacted_chapters` + CLI |
| `backend/tests/test_chapter_planner.py` | 章节规划测试 | 新建 |
| `skills/public/water-drainage-report/SKILL.md` | 技能流程 | 改：步骤0 快照 + 章节并行 + 折叠步骤 + 校验面板 + 多规范 + 版本历史 + 铁律精确化 |

阶段依赖：Phase 1（引擎 Task 1-3）→ Phase 2（数据 Task 4-6）→ Phase 3（runner/规划 Task 7-8）→ Phase 4（SKILL Task 9）→ Phase 5（冒烟 Task 10）。Phase 1-3 各自单测通过即可提交；Phase 4 是集成；Phase 5 端到端。

---

## Task 1: `ParamSource.needs_verification` 字段

**Files:**
- Modify: `backend/app/extensions/formula_engine/graph.py`（`ParamSource` dataclass，约 41-64 行）
- Modify: `backend/tests/test_formula_graph.py`（加测试类）

**为什么：** 反馈2 分层放开——系数/经验类默认值要能标【待核实】。`needs_verification` 是这个标记在引擎层的载体，`get_step_trace`（Task 2）和报告渲染都要读它。

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_formula_graph.py` 末尾：

```python
# ── needs_verification 字段（反馈2 分层放开：经验值标【待核实】）──

class TestNeedsVerification:
    def test_default_false(self):
        from app.extensions.formula_engine import ParamSource, ParamSourceType
        ps = ParamSource(type=ParamSourceType.LOOKUP_TABLE, value=0.001461)
        assert ps.needs_verification is False

    def test_can_set_true(self):
        from app.extensions.formula_engine import ParamSource, ParamSourceType
        ps = ParamSource(type=ParamSourceType.LOOKUP_TABLE, value=0.001461,
                         needs_verification=True)
        assert ps.needs_verification is True

    def test_factory_defaults_false(self):
        """既有工厂方法向后兼容：不传 needs_verification 时默认 False。"""
        from app.extensions.formula_engine import ParamSource
        assert ParamSource.lookup(0.001461).needs_verification is False
        assert ParamSource.code(5.0).needs_verification is False
        assert ParamSource.user(20000).needs_verification is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py::TestNeedsVerification -v`
Expected: FAIL — `AttributeError: 'ParamSource' object has no attribute 'needs_verification'`（或 dataclass 未定义该字段）。

- [ ] **Step 3: 加字段**

在 `backend/app/extensions/formula_engine/graph.py` 的 `ParamSource` dataclass（`description: str = ""` 那行之后）加一行：

```python
    description: str = ""               # 人类可读说明，如 "查GB/T 50746表3.3.3内插"
    needs_verification: bool = False    # 经验/系数默认值是否标【待核实】（反馈2 分层放开）
```

（即在原有 `description` 字段下追加 `needs_verification`。不改动工厂方法——它们经 dataclass 默认值自动得到 `False`，向后兼容。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py::TestNeedsVerification -v`
Expected: PASS（3 项）。

- [ ] **Step 5: 回归全量引擎测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py -v`
Expected: 全部 PASS（新 3 + 既有全过，证明向后兼容）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/extensions/formula_engine/graph.py backend/tests/test_formula_graph.py
git commit -m "feat(formula_engine): ParamSource 加 needs_verification 字段(反馈2分层放开)"
```

---

## Task 2: `FormulaGraph.get_step_trace(formula_id)`

**Files:**
- Modify: `backend/app/extensions/formula_engine/graph.py`（顶部加 `import re`；`FormulaGraph` 查询接口区加方法）
- Modify: `backend/tests/test_formula_graph.py`

**为什么：** 反馈3 黑箱展开——报告要逐条展示「公式来源 / 取值依据 / 代入分步 / 结果」。`get_step_trace` 把引擎已算的值 + 表达式结构化导出成轨迹，供 runner `trace` 子命令和报告折叠块消费。落点 `app/extensions/formula_engine`（app 层，非 harness）。

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_formula_graph.py`：

```python
# ── get_step_trace：单公式步骤轨迹（反馈3 折叠展开）──

class TestGetStepTrace:
    def test_trace_structure(self, built_graph: FormulaGraph):
        built_graph.execute()
        trace = built_graph.get_step_trace("Qe")
        assert trace is not None
        assert trace["id"] == "Qe"
        assert trace["expression"] == "Q * KZF * delta_t"
        assert trace["result"] == pytest.approx(292.2, abs=0.1)
        assert trace["unit"] == "m3/h"
        # substituted 应把变量替换成数值（Q=20000, KZF=0.001461, delta_t=10）
        sub = trace["substituted"]
        assert "20000" in sub and "0.001461" in sub and "10" in sub
        # inputs 每个参数带 name/value/unit/source/needs_verification
        names = [i["name"] for i in trace["inputs"]]
        assert set(names) == {"Q", "KZF", "delta_t"}
        kzf_in = next(i for i in trace["inputs"] if i["name"] == "KZF")
        assert kzf_in["value"] == pytest.approx(0.001461)
        assert "needs_verification" in kzf_in
        assert kzf_in["source"]  # lookup 参数应带出处描述

    def test_trace_unknown_formula(self, built_graph: FormulaGraph):
        assert built_graph.get_step_trace("nope") is None

    def test_trace_formula_output_source_label(self, built_graph: FormulaGraph):
        """formula_output 类型的输入，source 应标注上游公式。"""
        built_graph.execute()
        trace = built_graph.get_step_trace("Qb")  # Qb 依赖 Qe（formula_output）
        qe_in = next(i for i in trace["inputs"] if i["name"] == "Qe")
        assert "Qe" in qe_in["source"]  # 形如 "formula:Qe.Qe"

    def test_trace_needs_verification_passthrough(self):
        """ParamSource.needs_verification=True 应透传到轨迹。"""
        node = FormulaNode(
            "t", "t", expression="KZF * x",
            inputs={"KZF": ParamSource.lookup(0.001461, description="GB/T 表3.3.3",
                                              needs_verification=True),
                    "x": ParamSource.user(10)},
            outputs={"t": ""},
        )
        g = FormulaGraph()
        g.add_formula(node).build()
        g.execute()
        trace = g.get_step_trace("t")
        kzf_in = next(i for i in trace["inputs"] if i["name"] == "KZF")
        assert kzf_in["needs_verification"] is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py::TestGetStepTrace -v`
Expected: FAIL — `AttributeError: 'FormulaGraph' object has no attribute 'get_step_trace'`。

- [ ] **Step 3: 实现 `get_step_trace`**

3a. 在 `graph.py` 顶部 import 区（`from collections import defaultdict, deque` 那行附近）加：

```python
import re
```

3b. 在 `FormulaGraph` 的「查询接口」区（`last_change_summary` 方法之后、「只读属性」之前）插入以下两个方法：

```python
    def get_step_trace(self, formula_id: str) -> dict[str, Any] | None:
        """返回单公式的完整步骤轨迹，供报告折叠渲染（反馈3 黑箱展开）。

        复用引擎已算的值与表达式，不重复求值。返回结构：
            {
              "id", "name", "section", "expression", "source"(公式出处),
              "substituted"(变量替换为数值后的表达式串),
              "result", "unit",
              "inputs": [{"name","value","unit","source","needs_verification"}, ...]
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
                "value": resolved.get(name),
                "unit": src.unit,
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
            "inputs": inputs_trace,
        }
```

3c. 在文件末尾（`FormulaGraph` 类外，模块级）加 3 个辅助函数：

```python
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


def _source_label(src: "ParamSource") -> str:
    """单参数来源标注：formula_output 标上游公式，其余用 description 或类型名。"""
    if src.type == ParamSourceType.FORMULA_OUTPUT:
        return f"formula:{src.source_formula_id}.{src.source_param_name}"
    return src.description or src.type.value


def _formula_source(node: "FormulaNode") -> str:
    """公式整体出处：取首个 lookup/code 输入的 description（通常是规范条款），否则空。"""
    for src in node.inputs.values():
        if src.type in (ParamSourceType.LOOKUP_TABLE, ParamSourceType.CODE_REQUIREMENT) and src.description:
            return src.description
    return ""
```

> 说明：`Any` 已在文件顶部 `from typing import Any` 导入；`ParamSource`/`FormulaNode` 在模块内定义，前向引用用字符串注解即可。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py::TestGetStepTrace -v`
Expected: PASS（4 项）。

- [ ] **Step 5: 回归全量**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/extensions/formula_engine/graph.py backend/tests/test_formula_graph.py
git commit -m "feat(formula_engine): FormulaGraph.get_step_trace 步骤轨迹导出(反馈3黑箱展开)"
```

---

## Task 3: `code_constraint_multi` 多规范围框比对

**Files:**
- Modify: `backend/app/extensions/formula_engine/consistency.py`（`ContractType` 枚举、`Contract` dataclass、`load_contracts`、抽 `_resolve_actual`、新增 `multi_standard_matrix`）
- Modify: `backend/tests/test_formula_graph.py`（加 `TestMultiStandardMatrix`）

**为什么：** 反馈5 多规范——同一参数（如浓缩倍数 N）在不同规范有不同限值，要逐规范列出「规范号+条款 / 限值 / 当前值 / 是否满足」。`code_constraint_multi` 合约 + `multi_standard_matrix()` 方法产出这个矩阵。既有 `code_constraint`（单标准）保留不动，仍驱动 check() 的 pass/fail（反馈4 校验面板）。

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_formula_graph.py`：

```python
# ── code_constraint_multi：多规范围框比对（反馈5）──

class TestMultiStandardMatrix:
    def _engine_with_multi(self, n_value: float):
        from app.extensions.formula_engine import ConsistencyEngine
        eng = ConsistencyEngine()
        eng.set_param("4", "N", n_value)          # 注册到 _param_table
        eng._computed["N"] = n_value               # 供 expression eval
        eng.load_contracts([{
            "id": "N-multi-test",
            "type": "code_constraint_multi",
            "expression": "N",
            "description": "浓缩倍数多规范比对",
            "standards": [
                {"code": "GB 50648-2011", "clause": "§4.1.1", "min": 3.0, "severity": "fail", "note": "不应低于3.0"},
                {"code": "GB 50648-2011", "clause": "§4.1.1", "min": 5.0, "severity": "warn", "note": "宜≥5.0"},
                {"code": "GB/T 50050-2017", "clause": "§3.1.x", "min": 3.0, "severity": "fail"},
            ],
        }])
        return eng

    def test_matrix_shape(self):
        eng = self._engine_with_multi(5.0)
        rows = eng.multi_standard_matrix()
        assert len(rows) == 1
        row = rows[0]
        assert row["contract_id"] == "N-multi-test"
        assert row["actual"] == 5.0
        assert len(row["standards"]) == 3

    def test_each_standard_judged(self):
        eng = self._engine_with_multi(4.0)  # N=4
        row = eng.multi_standard_matrix()[0]
        by_code_clause = {(s["code"], s["clause"], s.get("min")): s for s in row["standards"]}
        # min=3.0 fail → 4.0≥3.0 通过
        assert by_code_clause[("GB 50648-2011", "§4.1.1", 3.0)]["passed"] is True
        # min=5.0 warn → 4.0<5.0 不通过
        assert by_code_clause[("GB 50648-2011", "§4.1.1", 5.0)]["passed"] is False

    def test_multi_not_in_normal_check(self):
        """code_constraint_multi 不走 check() 单违规路径（由 multi_standard_matrix 单独消费）。"""
        eng = self._engine_with_multi(1.0)  # 即便全部不满足
        assert eng.check() == []           # check() 不产出它的违规

    def test_single_code_constraint_unchanged(self):
        """既有 code_constraint（单标准）行为不变，仍驱动 check()。"""
        from app.extensions.formula_engine import ConsistencyEngine
        eng = ConsistencyEngine()
        eng._computed["N"] = 2.0
        eng.load_contracts([{
            "id": "N-min", "type": "code_constraint",
            "expression": "N", "expected_min": 3.0, "severity": "fail",
            "description": "N≥3.0",
        }])
        violations = eng.check()
        assert len(violations) == 1 and violations[0].contract_id == "N-min"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py::TestMultiStandardMatrix -v`
Expected: FAIL — `ValueError: 'code_constraint_multi' is not a valid ContractType`（枚举无此成员）。

- [ ] **Step 3: 改 `ContractType` 枚举**

在 `consistency.py` 的 `ContractType` 枚举（`FORMULA_CHAIN = ...` 那行之后）加：

```python
    FORMULA_CHAIN = "formula_chain"          # 公式计算结果必须等于下游输入值
    CODE_CONSTRAINT_MULTI = "code_constraint_multi"  # 多规范围框比对（反馈5，不驱动单 pass/fail）
```

- [ ] **Step 4: `Contract` dataclass 加 `standards` 字段**

在 `Contract` 的 `CODE_CONSTRAINT 专用字段` 区（`actual_value` 字段之后、`FORMULA_CHAIN 专用字段` 之前）加：

```python
    actual_value: float | None = None                 # 直接指定值（无表达式时使用）

    # ── CODE_CONSTRAINT_MULTI 专用字段 ──
    standards: list[dict] = field(default_factory=list)  # [{code, clause, min, max, severity, note}, ...]
```

- [ ] **Step 5: `load_contracts` 透传 `standards`**

在 `load_contracts` 的 `Contract(...)` 构造里（`downstream_param=...` 那行之后）加：

```python
                upstream_param=cdef.get("upstream_param", ""),
                downstream_param=cdef.get("downstream_param", ""),
                standards=cdef.get("standards", []),
```

- [ ] **Step 6: 抽 `_resolve_actual` 并路由 multi**

6a. 把 `_check_code_constraint` 开头解析 actual 值的逻辑抽成方法。在 `_check_code_constraint` 方法**之前**插入：

```python
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
```

6b. 改 `_check_code_constraint` 开头（用 `_resolve_actual` 替换内联解析），把：

```python
        # 解析实际值
        if c.expression:
            try:
                namespace = dict(self._computed)
                # 将表达式中的点号替换为下划线：V_system.V_system → V_system_V_system
                expr = re.sub(r'(\w+)\.(\w+)', r'\1_\2', c.expression)
                # 为计算参数创建下划线别名
                for key, val in list(namespace.items()):
                    namespace[key.replace(".", "_")] = val
                namespace["__builtins__"] = {}
                actual = float(eval(expr, namespace, {}))
            except Exception:
                return None                        # 无法计算 → 安全跳过（不阻塞）
        elif c.actual_value is not None:
            actual = c.actual_value
        else:
            return None                            # 无可用值
```

替换为：

```python
        # 解析实际值（与 multi_standard_matrix 共用 _resolve_actual）
        actual = self._resolve_actual(c)
        if actual is None:
            return None                            # 无法计算 → 安全跳过（不阻塞）
```

（后续 `expected_min`/`expected_max` 检查逻辑不动。）

6c. 在 `_evaluate` 路由里（`elif c.type == ContractType.CODE_CONSTRAINT:` 分支之后）加 multi 分支：

```python
        elif c.type == ContractType.CODE_CONSTRAINT:
            return self._check_code_constraint(c)
        elif c.type == ContractType.CODE_CONSTRAINT_MULTI:
            return None  # 多规范矩阵由 multi_standard_matrix() 单独消费，不走单违规路径
```

- [ ] **Step 7: 新增 `multi_standard_matrix` 方法**

在 `_check_formula_chain` 方法之后、「辅助工具方法」区之前插入：

```python
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
```

- [ ] **Step 8: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py::TestMultiStandardMatrix -v`
Expected: PASS（4 项）。

- [ ] **Step 9: 回归全量**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py -v`
Expected: 全部 PASS（含既有 code_constraint 用例，证明 `_resolve_actual` 抽取未破坏单标准路径）。

- [ ] **Step 10: 提交**

```bash
git add backend/app/extensions/formula_engine/consistency.py backend/tests/test_formula_graph.py
git commit -m "feat(formula_engine): code_constraint_multi 多规范围框比对(反馈5)+抽_resolve_actual"
```

---

## Task 4: `formulas.json` 系数/经验类 input 加 `needs_verification`

**Files:**
- Modify: `skills/public/water-drainage-report/references/formulas.json`

**为什么：** 反馈2——系数/经验类参数（蒸发系数 KZF、有效水深、旁滤比、反洗强度、反洗时长）允许有出处默认值但标【待核实】。核心工艺参数（Q/Δt/N/构筑物尺寸）保持 `value: null`（必须用户提供，铁律不变）。`needs_verification` 由 Task 1 的 `build_graph` 透传，Task 2 的 `get_step_trace` 读出。

**分层放开规则（spec §3.1）：**
- 系数/经验类 → 保留默认值 + 加 `needs_verification: true`
- 核心工艺类（Q, delta_t, N, pool_area, V_suction, pump_motor_spacing, filter_unit_capacity, filter_area, concurrent_backwash）→ `value: null` 不变，**不加** `needs_verification`

- [ ] **Step 1: 改 KZF（Qe 公式的蒸发系数）**

把 `formulas.json` 中 KZF 那行：

```json
        "KZF": {"type": "lookup_table", "value": 0.001461, "unit": "1/℃", "description": "蒸发损失系数，GB/T 50746 表3.3.3内插"},
```

改为：

```json
        "KZF": {"type": "lookup_table", "value": 0.001461, "unit": "1/℃", "source": "GB/T 50746-2012 表3.3.3 内插", "description": "蒸发损失系数", "needs_verification": false},
```

> `needs_verification: false`——这是已核实的规范查表值（附录 B 重审清单里 KZF 未被质疑）。

- [ ] **Step 2: 改 effective_depth（V_pool 公式的有效水深）**

把：

```json
        "effective_depth": {"type": "code_requirement", "value": 2.0, "unit": "m", "description": "有效水深，GB/T 50746 §4.3.13：1.0~1.5m为有效水深，本项目取2.0m"}
```

改为：

```json
        "effective_depth": {"type": "code_requirement", "value": 2.0, "unit": "m", "source": "GB/T 50746-2012 §4.3.13（1.0~1.5m为有效水深，本项目取2.0m，需核实）", "description": "塔底水池有效水深", "needs_verification": true},
```

> 2.0m 超出规范 1.0~1.5m 区间，属于项目取值，标【待核实】。

- [ ] **Step 3: 改 sf_ratio（Qsf 公式的旁滤比）**

把：

```json
        "sf_ratio": {"type": "code_requirement", "value": 0.05, "description": "GB50050 §4.0.4: 旁滤水量为循环水量的1%~5%，本项目取5%"}
```

改为：

```json
        "sf_ratio": {"type": "code_requirement", "value": 0.05, "source": "GB/T 50050-2017 §4.0.4（缺含尘数据时 1%~5%；沙尘区可上调，本项目取5%需核实）", "description": "旁滤比例", "needs_verification": true}
```

> 附录 B：1%~5% 实为「缺含尘数据时」兜底子款，标【待核实】并条件化提示。

- [ ] **Step 4: 改 backwash_intensity + backwash_duration（反洗参数）**

把 `backwash_flow` 公式里的：

```json
        "backwash_intensity": {"type": "user_input", "value": 15.0, "unit": "L/s·m2", "description": "设计反洗强度"},
```

改为：

```json
        "backwash_intensity": {"type": "lookup_table", "value": 15.0, "unit": "L/s·m2", "source": "GB/T 50050-2017 §4.0.4 条文说明 / 工程经验 12~16", "description": "反洗强度", "needs_verification": true},
```

> 注意 type 从 `user_input` 改为 `lookup_table`——反洗强度属经验值，缺失时应走参考值库而非强制追问（反馈2）。

把 `backwash_volume` 公式里的：

```json
        "backwash_duration": {"type": "user_input", "value": 2.0, "unit": "min", "description": "单罐反洗一次时间"},
```

改为：

```json
        "backwash_duration": {"type": "lookup_table", "value": 2.0, "unit": "min", "source": "工程经验（砂滤一般 1~3 min，本项目取 2 min 需核实）", "description": "单罐反洗一次时间", "needs_verification": true},
```

- [ ] **Step 5: 验证 JSON 合法 + 引擎可加载**

Run:
```bash
cd backend && PYTHONPATH=. python -c "import json; d=json.load(open('../skills/public/water-drainage-report/references/formulas.json',encoding='utf-8')); print('formulas:', len(d['formulas'])); import sys; sys.path.insert(0,'.')"
```
Expected: 打印 `formulas: 12`，无 JSON 解析错误。

- [ ] **Step 6: 跑引擎回归（确认 build_graph 仍能消费改后的 json）**

Run:
```bash
cd backend && PYTHONPATH=. python ../skills/public/water-drainage-report/scripts/formula_runner.py execute \
  --formulas ../skills/public/water-drainage-report/references/formulas.json \
  --params '{"Q":20000,"delta_t":10,"N":5,"pool_area":912,"V_suction":2099.5,"pump_motor_spacing":5.2,"filter_unit_capacity":40,"filter_area":1.13,"concurrent_backwash":5,"total_filters":25}'
```
Expected: 输出含 `results` 的 JSON（Qe≈292.2 等），无报错。

- [ ] **Step 7: 提交**

```bash
git add skills/public/water-drainage-report/references/formulas.json
git commit -m "feat(water-drainage): formulas.json 系数/经验类 input 加 needs_verification+source(反馈2分层放开)"
```

---

## Task 5: 新建 `reference_values.json` + `standards_index.json`

**Files:**
- Create: `skills/public/water-drainage-report/references/reference_values.json`
- Create: `skills/public/water-drainage-report/references/standards_index.json`

**为什么：**
- `reference_values.json`（反馈2）：技能在步骤1 收集参数时，对缺失的系数/经验类参数，agent 读此文件取默认值并标【待核实】（核心工艺参数不在此库）。
- `standards_index.json`（反馈5）：用户可勾选的规范清单；`tier1_curated` 标记是否已人工入库关键限值（Tier-1）。

> 这两个是 agent 读的数据文件（`read_file`），无需新代码消费——SKILL.md（Task 9）写明 agent 如何用。

- [ ] **Step 1: 写 `reference_values.json`**

```json
{
  "description": "给排水/循环水 行业经验参考值库（仅系数/经验类，核心工艺参数 Q/N/Δt/构筑物尺寸不在此库）",
  "policy": "用户未提供时，技能可取此默认值并标注【待核实】；用户核实后可晋升为项目定值。核心工艺参数缺失必须 ask_clarification，绝不从此库取。",
  "values": [
    {
      "key": "backwash_intensity",
      "default": 15.0,
      "unit": "L/(s·m²)",
      "source": "GB/T 50050-2017 §4.0.4 条文说明 / 工程经验 12~16",
      "applies_when": "用户未提供反洗强度",
      "needs_verification": true
    },
    {
      "key": "backwash_duration",
      "default": 2.0,
      "unit": "min",
      "source": "工程经验（砂滤一般 1~3 min）",
      "applies_when": "用户未提供单罐反洗时长",
      "needs_verification": true
    },
    {
      "key": "effective_depth",
      "default": 2.0,
      "unit": "m",
      "source": "GB/T 50746-2012 §4.3.13（有效水深 1.0~1.5m，项目取值需核实）",
      "applies_when": "用户未提供塔底水池有效水深",
      "needs_verification": true
    },
    {
      "key": "sf_ratio",
      "default": 0.05,
      "unit": "—",
      "source": "GB/T 50050-2017 §4.0.4（缺含尘数据时 1%~5%；沙尘区可上调）",
      "applies_when": "用户未提供旁滤比例",
      "needs_verification": true
    },
    {
      "key": "KZF",
      "default": 0.001461,
      "unit": "1/℃",
      "source": "GB/T 50746-2012 表3.3.3 内插",
      "applies_when": "用户未提供蒸发损失系数",
      "needs_verification": false
    }
  ]
}
```

- [ ] **Step 2: 写 `standards_index.json`**

```json
{
  "description": "给排水/循环水 可勾选规范清单（反馈5 多规范）。tier1_curated=true 表示已人工入库关键限值（驱动自动 pass/fail）；false 表示未入库（参数走 Tier-2，标【需人工对照规范】不自动判定）。",
  "selection_note": "用户在步骤1 勾选所需规范；选中集存入 project_snapshot.standards_selected。",
  "standards": [
    {"code": "GB/T 50746-2012", "title": "石油化工循环水场设计规范", "scope": "循环水场", "tier1_curated": true},
    {"code": "GB 50648-2011", "title": "化学工业循环冷却水系统设计规范", "scope": "化工循环水", "tier1_curated": true},
    {"code": "GB/T 50050-2017", "title": "工业循环冷却水处理设计规范", "scope": "循环水处理", "tier1_curated": true},
    {"code": "GB 50974-2014", "title": "消防给水及消火栓系统技术规范", "scope": "消防给水", "tier1_curated": false, "note": "部分条文 2023-03-01 废止；Tier-1 入库前需按现行条文核对"},
    {"code": "GB 50014-2021", "title": "室外排水设计标准", "scope": "排水", "tier1_curated": false},
    {"code": "GB/T 50378-2019", "title": "绿色建筑评价标准", "scope": "绿建", "tier1_curated": false},
    {"code": "HG/T 20690-2000", "title": "化工企业循环冷却水处理设计技术规定", "scope": "循环水处理细则", "tier1_curated": false}
  ]
}
```

- [ ] **Step 3: 验证两个 JSON 合法**

Run:
```bash
python -c "import json; json.load(open('skills/public/water-drainage-report/references/reference_values.json',encoding='utf-8')); json.load(open('skills/public/water-drainage-report/references/standards_index.json',encoding='utf-8')); print('OK')"
```
Expected: 打印 `OK`。

- [ ] **Step 4: 提交**

```bash
git add skills/public/water-drainage-report/references/reference_values.json skills/public/water-drainage-report/references/standards_index.json
git commit -m "feat(water-drainage): 新建 reference_values.json + standards_index.json(反馈2经验值库+反馈5规范清单)"
```

---

## Task 6: `consistency_contracts.json` 加 `code_constraint_multi` 合约

**Files:**
- Modify: `skills/public/water-drainage-report/references/consistency_contracts.json`

**为什么：** 反馈5——给「浓缩倍数 N」配一条多规范围框合约（GB 50648 + GB/T 50050），供 Task 3 的 `multi_standard_matrix()` 消费、Task 7 的 `check` 子命令输出比对矩阵。既有 11 条合约不动。

- [ ] **Step 1: 在 `contracts` 数组末尾追加多规范合约**

在 `consistency_contracts.json` 的 `contracts` 数组最后一条（`pump-suction-velocity`）之后、闭合 `]` 之前，加：

```json
    {
      "id": "N-multi-standard",
      "type": "code_constraint_multi",
      "expression": "N",
      "description": "浓缩倍数 N 跨规范围框比对",
      "standards": [
        {"code": "GB 50648-2011", "clause": "§4.1.1", "min": 3.0, "severity": "fail", "note": "不应低于3.0"},
        {"code": "GB 50648-2011", "clause": "§4.1.1", "min": 5.0, "severity": "warn", "note": "宜≥5.0"},
        {"code": "GB/T 50050-2017", "clause": "§3.1.x", "min": 3.0, "severity": "fail", "note": "不应低于3.0"}
      ]
    }
```

（注意前一条 `pump-suction-velocity` 末尾要有逗号。）

- [ ] **Step 2: 验证 JSON 合法 + 引擎能加载新合约**

Run:
```bash
cd backend && PYTHONPATH=. python -c "
import json
from app.extensions.formula_engine import ConsistencyEngine
d = json.load(open('../skills/public/water-drainage-report/references/consistency_contracts.json', encoding='utf-8'))
eng = ConsistencyEngine()
eng.load_contracts(d['contracts'])
eng._computed['N'] = 4.0
rows = eng.multi_standard_matrix()
print('contracts:', len(d['contracts']))
print('multi rows:', len(rows), '| stds:', len(rows[0]['standards']))
"
```
Expected: 打印 `contracts: 12`、`multi rows: 1 | stds: 3`。

- [ ] **Step 3: 提交**

```bash
git add skills/public/water-drainage-report/references/consistency_contracts.json
git commit -m "feat(water-drainage): consistency_contracts 加 N 多规范围框合约(反馈5)"
```

---

## Task 7: `formula_runner.py` 新增 `trace` / `impacted` 子命令 + `build_graph` 透传

**Files:**
- Modify: `skills/public/water-drainage-report/scripts/formula_runner.py`

**为什么：**
- `build_graph` 透传 `needs_verification`（Task 1 字段落到 runner 构造处）。
- `trace` 子命令（反馈3）：输出全公式步骤轨迹（调 Task 2 的 `get_step_trace`），供报告折叠块 + chapter_planner 消费。
- `impacted` 子命令（反馈6）：给定参数变更，输出受影响 formula_id + chapter_id（复用 `update_param` 的受影响集 + chapter_manifest 反查）。

- [ ] **Step 1: `build_graph` 透传 `needs_verification`**

在 `formula_runner.py` 的 `build_graph` 函数里，把构造 `ParamSource(...)` 那段：

```python
            inputs[pname] = ParamSource(
                type=src_type,
                value=value,
                unit=psrc.get("unit", ""),
                source_formula_id=psrc.get("source_formula_id", ""),
                source_param_name=psrc.get("source_param_name", ""),
                description=psrc.get("description", ""),
            )
```

改为（加最后一行）：

```python
            inputs[pname] = ParamSource(
                type=src_type,
                value=value,
                unit=psrc.get("unit", ""),
                source_formula_id=psrc.get("source_formula_id", ""),
                source_param_name=psrc.get("source_param_name", ""),
                description=psrc.get("description", ""),
                needs_verification=psrc.get("needs_verification", False),
            )
```

- [ ] **Step 2: 写 `cmd_trace` 子命令**

在 `cmd_check` 函数之后、「CLI 入口」注释区之前，插入：

```python
# ═══════════════════════════════════════════════════════════════════════════════
# 子命令: trace — 输出全公式步骤轨迹（反馈3 折叠渲染）
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_trace(args: argparse.Namespace) -> None:
    """trace 子命令：构建图 → 执行 → 输出每个公式的步骤轨迹。

    支持 --state（从上次 execute 的状态文件恢复）或 --params（首次）。

    输出 JSON: {"traces": [get_step_trace 返回结构, ...]}
    打印标记: TRACE_READY: <output 路径>（供技能/agent 确认成功）。
    """
    formulas = load_formulas(args.formulas)

    if args.state:
        # 从状态文件恢复用户参数（复用 update 的恢复逻辑）
        with open(args.state, "r", encoding="utf-8") as f:
            state = json.load(f)
        params = {k: v for k, v in (state.get("all_params") or {}).items() if "." not in k}
    else:
        params = json.loads(args.params) if args.params else {}

    graph = build_graph(formulas, params)
    graph.execute()

    traces = [graph.get_step_trace(fid) for fid in graph.nodes]
    output = {"traces": traces}

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"TRACE_READY: {args.output}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════════════════════
# 子命令: impacted — 参数变更的受影响 formula_id + chapter_id（反馈6 定点重生成）
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_impacted(args: argparse.Namespace) -> None:
    """impacted 子命令：恢复状态 → 改参（dry-run）→ 受影响公式 → 反查受影响章节。

    受影响 formula_id 复用 FormulaGraph.update_param 的返回集（与 update 同源）。
    受影响 chapter_id 用 chapter_manifest 反查（manifest 由 chapter_planner 生成）。

    输出 JSON: {"param","affected_formulas":[...],"affected_chapters":[...]}
    打印标记: IMPACTED_READY: <output 路径>。
    """
    formulas = load_formulas(args.formulas)
    with open(args.state, "r", encoding="utf-8") as f:
        state = json.load(f)
    user_params = {k: v for k, v in (state.get("all_params") or {}).items() if "." not in k}

    graph = build_graph(formulas, user_params)
    graph.execute()
    affected_formulas = graph.update_param(args.param, float(args.value))  # dry-run：只取受影响集，不写盘

    # 反查受影响章节
    affected_chapters: list[str] = []
    if args.manifest:
        try:
            with open(args.manifest, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            for ch in manifest.get("chapters", []):
                if set(ch.get("formula_ids", [])) & set(affected_formulas):
                    affected_chapters.append(ch["id"])
        except (OSError, json.JSONDecodeError):
            pass  # manifest 缺失/损坏 → 只返回公式级，不阻塞

    output = {
        "param": args.param,
        "affected_formulas": affected_formulas,
        "affected_chapters": affected_chapters,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"IMPACTED_READY: {args.output}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
```

- [ ] **Step 3: 在 `main()` 注册两个子命令**

在 `main()` 的 `p_check` 子命令注册之后、`args = parser.parse_args()` 之前，加：

```python
    # trace 子命令（反馈3）
    p_trace = sub.add_parser("trace", help="输出全公式步骤轨迹（供报告折叠渲染）")
    p_trace.add_argument("--formulas", required=True, help="公式定义 JSON 文件路径")
    p_trace.add_argument("--params", default="{}", help="用户参数 JSON（首次执行时）")
    p_trace.add_argument("--state", help="上次 execute 的状态文件路径（增量场景，与 --params 二选一）")
    p_trace.add_argument("--output", help="输出轨迹文件路径")

    # impacted 子命令（反馈6）
    p_impacted = sub.add_parser("impacted", help="参数变更的受影响公式+章节（定点重生成）")
    p_impacted.add_argument("--formulas", required=True, help="公式定义 JSON 文件路径")
    p_impacted.add_argument("--state", required=True, help="上次 execute 的状态文件路径")
    p_impacted.add_argument("--param", required=True, help="要修改的参数名")
    p_impacted.add_argument("--value", required=True, help="新的参数值")
    p_impacted.add_argument("--manifest", help="chapter_manifest.json 路径（反查受影响章节）")
    p_impacted.add_argument("--output", help="输出受影响集文件路径")
```

并在 `main()` 的命令路由区（`elif args.command == "check":` 之后）加：

```python
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "trace":
        cmd_trace(args)
    elif args.command == "impacted":
        cmd_impacted(args)
```

- [ ] **Step 4: 手动验证 trace 子命令**

Run:
```bash
cd backend && PYTHONPATH=. python ../skills/public/water-drainage-report/scripts/formula_runner.py trace \
  --formulas ../skills/public/water-drainage-report/references/formulas.json \
  --params '{"Q":20000,"delta_t":10,"N":5,"pool_area":912,"V_suction":2099.5,"pump_motor_spacing":5.2,"filter_unit_capacity":40,"filter_area":1.13,"concurrent_backwash":5,"total_filters":25}'
```
Expected: 输出 JSON，`traces` 数组含 12 项；其中 Qe 项的 `substituted` 含 `20000 * 0.001461 * 10`、`result≈292.2`、KZF input 的 `needs_verification` 为 `false`、effective_depth input 的 `needs_verification` 为 `true`。

- [ ] **Step 5: 手动验证 impacted 子命令（先建 state）**

5a. 先 execute 出 state：
```bash
cd backend && PYTHONPATH=. python ../skills/public/water-drainage-report/scripts/formula_runner.py execute \
  --formulas ../skills/public/water-drainage-report/references/formulas.json \
  --params '{"Q":20000,"delta_t":10,"N":5,"pool_area":912,"V_suction":2099.5,"pump_motor_spacing":5.2,"filter_unit_capacity":40,"filter_area":1.13,"concurrent_backwash":5,"total_filters":25}' \
  --output /tmp/f_state.json
```
Expected: `STATE_READY: /tmp/f_state.json`

5b. 跑 impacted（无 manifest，只看公式级）：
```bash
cd backend && PYTHONPATH=. python ../skills/public/water-drainage-report/scripts/formula_runner.py impacted \
  --formulas ../skills/public/water-drainage-report/references/formulas.json \
  --state /tmp/f_state.json --param Q --value 25000
```
Expected: 输出 JSON，`affected_formulas` 含 Qe/Qw/Qb/Qm/Qsf/filter_count/...（Q 的全部下游）；`affected_chapters: []`（暂无 manifest，Task 8 之后可带 `--manifest`）。

- [ ] **Step 6: 提交**

```bash
git add skills/public/water-drainage-report/scripts/formula_runner.py
git commit -m "feat(water-drainage): formula_runner 加 trace/impacted 子命令+build_graph透传needs_verification(反馈3+6)"
```

---

## Task 8: `chapter_planner.py`（章节↔公式映射 + 受影响章节反查）

**Files:**
- Create: `skills/public/water-drainage-report/scripts/chapter_planner.py`
- Create: `backend/tests/test_chapter_planner.py`

**为什么：** 反馈6 定点重生成需要「改一个参 → 受影响哪些章节」的反查中枢。`chapter_manifest.json` 把报告章节映射到 formula_id 集合；`build_manifest` 从 formulas.json 生成它，`impacted_chapters` 反查。v1 只做 manifest + impacted（机械 table 渲染延后，见 spec §14⑥）。落点技能层（`scripts/`）。

**章节↔公式映射规则（fallback 10 章结构）：** 每章有 `section_prefixes`，formula 按 `section` 的首段（如 "6.1.1" → "6"）归入匹配章。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_chapter_planner.py`：

```python
"""chapter_planner 测试：章节 manifest 生成 + 受影响章节反查（反馈6）。"""

import json
import sys
from pathlib import Path

# 把 skills/.../scripts 加入 sys.path 以 import chapter_planner
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "skills" / "public" / "water-drainage-report" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import chapter_planner  # noqa: E402

# 用 formulas.json 的真实 section 结构做 fixture
_FORMULAS = _REPO_ROOT / "skills" / "public" / "water-drainage-report" / "references" / "formulas.json"


class TestBuildManifest:
    def test_manifest_has_all_chapters(self):
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        manifest = chapter_planner.build_manifest(formulas)
        ids = [c["id"] for c in manifest["chapters"]]
        # fallback 10 章
        assert "ch5_calc" in ids and "ch6_pool" in ids and "ch9_equiplist" in ids
        assert len(manifest["chapters"]) == 10

    def test_formulas_assigned_by_section(self):
        """section 6.1.x → ch5_calc；7.1.x → ch6_pool；9.1.x → ch8_filter。"""
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        manifest = chapter_planner.build_manifest(formulas)
        by_id = {c["id"]: c for c in manifest["chapters"]}
        assert "Qe" in by_id["ch5_calc"]["formula_ids"]      # 6.1.1
        assert "Qm" in by_id["ch5_calc"]["formula_ids"]      # 6.1.4
        assert "V_pool" in by_id["ch6_pool"]["formula_ids"]  # 7.1.1
        assert "Qsf" in by_id["ch8_filter"]["formula_ids"]   # 9.1.1


class TestImpactedChapters:
    def _manifest(self):
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        return chapter_planner.build_manifest(formulas)

    def test_q_change_hits_calc_chapter(self):
        """改 Q → 影响含 Qe/Qm 的 ch5_calc。"""
        manifest = self._manifest()
        chapters = chapter_planner.impacted_chapters(["Qe", "Qw", "Qb", "Qm"], manifest)
        assert "ch5_calc" in chapters

    def test_no_affected_returns_empty(self):
        manifest = self._manifest()
        assert chapter_planner.impacted_chapters([], manifest) == []

    def test_dedup(self):
        """多个受影响公式落在同一章时，章节只出现一次。"""
        manifest = self._manifest()
        chapters = chapter_planner.impacted_chapters(["Qe", "Qb", "Qm"], manifest)
        assert chapters.count("ch5_calc") == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_chapter_planner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chapter_planner'`。

- [ ] **Step 3: 写 `chapter_planner.py`**

新建 `skills/public/water-drainage-report/scripts/chapter_planner.py`：

```python
#!/usr/bin/env python3
"""给排水设计专篇 — 章节规划器（反馈6 定点重生成的中枢）。

两个纯函数 + 一个 CLI：
    build_manifest(formulas)   — 把公式按 section 归入 fallback 10 章结构，产出 chapter_manifest.json
    impacted_chapters(fids, m) — 给定受影响 formula_id 集 + manifest，反查受影响 chapter_id

manifest 是「改参 → 受影响章节」的反查表：formula_runner impacted --manifest 用它把
受影响公式收窄到受影响章节，技能只重生成这些章节（反馈6 热更新）。

机械 table 渲染延后（spec §14⑥）；v1 只做映射 + 反查。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# fallback 10 章结构：section_prefixes 指明该章吸收哪些 section 首段（报告章节号 ≠ 文档 section 号）
FALLBACK_CHAPTERS = [
    {"id": "ch1_basis",      "title": "设计依据及采用的标准",         "type": "narrative", "section_prefixes": []},
    {"id": "ch2_scope",      "title": "设计范围与设计规模",           "type": "narrative", "section_prefixes": []},
    {"id": "ch3_params",     "title": "设计参数",                     "type": "table",    "section_prefixes": [], "render": "param_table"},
    {"id": "ch4_standards",  "title": "设计中采用的主要标准及规范",   "type": "narrative", "section_prefixes": []},
    {"id": "ch5_calc",       "title": "循环水装置工艺计算",           "type": "table",    "section_prefixes": ["6"], "render": "calc_steps"},
    {"id": "ch6_pool",       "title": "塔底水池、吸水池、滤网及滤网井", "type": "narrative", "section_prefixes": ["7"]},
    {"id": "ch7_pumphouse",  "title": "吸水池及循环水泵房工艺计算",   "type": "narrative", "section_prefixes": ["8"]},
    {"id": "ch8_filter",     "title": "旁滤设备",                     "type": "narrative", "section_prefixes": ["9"]},
    {"id": "ch9_equiplist",  "title": "设备一览表",                   "type": "table",    "section_prefixes": [], "render": "equipment_table"},
    {"id": "ch10_drawings",  "title": "图纸清单",                     "type": "narrative", "section_prefixes": []},
]


def _section_prefix(section: str) -> str:
    """section "6.1.1" → "6"；空 → ""。"""
    return section.split(".", 1)[0] if section else ""


def build_manifest(formulas_data: list[dict]) -> dict:
    """把公式按 section 首段归入 fallback 10 章，返回 chapter_manifest 结构。

    每个 chapter 增加 formula_ids（落入该章的公式 id 列表）。
    未匹配任何章前缀的公式 → 忽略（不阻塞；通常是新增公式尚未配章）。
    """
    chapters = []
    for ch in FALLBACK_CHAPTERS:
        chapters.append({**ch, "formula_ids": []})

    prefix_to_chidx: dict[str, int] = {}
    for idx, ch in enumerate(chapters):
        for pfx in ch["section_prefixes"]:
            prefix_to_chidx[pfx] = idx

    for fdef in formulas_data:
        pfx = _section_prefix(fdef.get("section", ""))
        idx = prefix_to_chidx.get(pfx)
        if idx is not None:
            chapters[idx]["formula_ids"].append(fdef["id"])

    return {"version": 1, "chapters": chapters}


def impacted_chapters(affected_formula_ids: list[str], manifest: dict) -> list[str]:
    """反查受影响 chapter_id（去重、保序）。空集 → []。"""
    hit: list[str] = []
    affected = set(affected_formula_ids)
    for ch in manifest.get("chapters", []):
        if affected & set(ch.get("formula_ids", [])):
            if ch["id"] not in hit:
                hit.append(ch["id"])
    return hit


# ═══════════════════════════════════════════════════════════════════════════════
# CLI: manifest / impacted
# ═══════════════════════════════════════════════════════════════════════════════

def _load_formulas(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["formulas"]


def main() -> None:
    parser = argparse.ArgumentParser(description="给排水设计专篇 — 章节规划器")
    sub = parser.add_subparsers(dest="command")

    p_manifest = sub.add_parser("manifest", help="从 formulas.json 生成 chapter_manifest.json")
    p_manifest.add_argument("--formulas", required=True, help="formulas.json 路径")
    p_manifest.add_argument("--output", required=True, help="输出 manifest 路径")

    args = parser.parse_args()

    if args.command == "manifest":
        formulas = _load_formulas(args.formulas)
        manifest = build_manifest(formulas)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"MANIFEST_READY: {args.output}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_chapter_planner.py -v`
Expected: PASS（5 项）。

- [ ] **Step 5: 手动验证 CLI + impacted 联动**

5a. 生成 manifest：
```bash
cd backend && python ../skills/public/water-drainage-report/scripts/chapter_planner.py manifest \
  --formulas ../skills/public/water-drainage-report/references/formulas.json \
  --output /tmp/manifest.json
```
Expected: `MANIFEST_READY: /tmp/manifest.json`

5b. 用 Task 7 的 state + manifest 跑 impacted：
```bash
cd backend && PYTHONPATH=. python ../skills/public/water-drainage-report/scripts/formula_runner.py impacted \
  --formulas ../skills/public/water-drainage-report/references/formulas.json \
  --state /tmp/f_state.json --param Q --value 25000 \
  --manifest /tmp/manifest.json
```
Expected: `affected_chapters` 含 `ch5_calc`（及含 Q 下游公式的其他章，如 ch8_filter 因 Qsf）。

- [ ] **Step 6: 提交**

```bash
git add skills/public/water-drainage-report/scripts/chapter_planner.py backend/tests/test_chapter_planner.py
git commit -m "feat(water-drainage): chapter_planner 章节映射+受影响章节反查(反馈6定点重生成)"
```

---

## Task 9: `SKILL.md` 流程重写（集成 7 反馈）

**Files:**
- Modify: `skills/public/water-drainage-report/SKILL.md`

**为什么：** 把 Task 1-8 的能力接进技能流程——步骤0 会话快照（反馈7）、分层放开（反馈2 铁律精确化）、章节并行生成（反馈1 提速）、折叠步骤 + 校验面板 + 多规范比对（反馈3/4/5）、改参定点重生成（反馈6）、版本历史（反馈7）。

> 这是文档/流程改写，非代码。下面给精确的「改哪段→改成什么」；完整行文按 spec §5-§10。

- [ ] **Step 1: 精确化「最高铁律」（反馈2）**

把「核心原则」第 4 条的标题与首段：

```markdown
4. **⛔ 缺失信息一律由用户提供（最高铁律，贯穿全程）**: 任何缺失信息——无论是项目背景、设计参数、设备清单、工艺数据，还是报告正文中某个具体数值——**必须由用户填写和提供**。三个"绝不"：
```

改为：

```markdown
4. **⛔ 禁止无出处的值（最高铁律，贯穿全程）**: 精确化（2026-08-11）——原"禁止任何默认值"改为"禁止无出处的值"。**核心工艺参数**（Q、Δt、N、构筑物尺寸、装置用水量）缺失，仍必须用户提供（`[待用户提供]` + `ask_clarification`，绝不编造）。**系数/经验类参数**（蒸发系数 KZF、有效水深、旁滤比、反洗强度/时长）缺失时，可从 `references/reference_values.json` 取**有出处**的默认值并标注【待核实】，用户核实后晋升为项目定值。三个"绝不"：
```

（其下三个"绝不"子弹项保留。）

- [ ] **Step 2: 工具范围补 chapter_planner + 快照/规范数据**

在「## 工具范围」段，把工具列表那行之后补一段说明：

```markdown
**配套脚本与数据（通过 bash/read_file 使用）：**
- `scripts/formula_runner.py` — 公式计算 CLI（execute / update / check / **trace** / **impacted**）
- `scripts/chapter_planner.py` — 章节规划（manifest 生成 / 受影响章节反查）
- `references/reference_values.json` — 系数/经验类行业参考值库（反馈2，缺失时取默认+【待核实】）
- `references/standards_index.json` — 可勾选规范清单（反馈5）
- `references/consistency_contracts.json` — 一致性 + 多规范围框合约（含 `code_constraint_multi`）
```

- [ ] **Step 3: 新增「步骤0：会话快照」（反馈7）**

在「## 执行流程」标题之后、「### 步骤1」之前，插入：

```markdown
### 步骤0：会话快照恢复（反馈7 跨轮承接）

**启动时先检查** `/mnt/user-data/workspace/project_snapshot.json`：

- **存在** → 读取并恢复：`params` / `formula_state` / `chapter_manifest` / `standards_selected` / `report_path`。向用户展示「当前基准状态」（版本号 + 最近一次变更日志），后续指令默认基于该基准增量理解，**不重复追问全局参数**。直接跳到用户当前指令对应的步骤。
- **不存在或损坏** → 降级为全新运行（try/except 包裹加载，不崩溃），从步骤1 开始。

快照字段（由技能在各步骤后更新，`version++` + `change_log` 追加）：
```
{"version", "created_at", "updated_at", "params", "formula_state",
 "chapter_manifest", "standards_selected", "report_path", "change_log": [...]}
```

**版本历史** = `version` 序列 + `change_log`；前端展示复用文档空间，不新建。
```

- [ ] **Step 4: 步骤1 补分层放开 + 规范勾选**

在「### 步骤1：收集设计参数」的「⛔ 参数缺失策略」那段之后，追加：

```markdown
**分层放开（反馈2）：** 系数/经验类参数缺失时，读 `references/reference_values.json`：命中 → 填入默认值并在参数表「来源」列标 `参考值库（【待核实】）`；未命中 → `ask_clarification`。核心工艺参数缺失一律 `ask_clarification`，**绝不**从参考值库取。

**规范勾选（反馈5）：** 步骤1 同时请用户从 `references/standards_index.json` 勾选本项目适用的规范（默认勾选 3 本 tier1_curated=true 的循环水规范）。选中集写入 `project_snapshot.standards_selected`。
```

- [ ] **Step 5: 步骤2 补 trace 输出 + 生成 chapter_manifest**

在「### 步骤2：运行公式计算」的 execute bash 块之后，追加：

```markdown
**生成步骤轨迹 + 章节清单（供后续折叠渲染与定点重生成）：**
```bash
python $SCRIPTS/formula_runner.py trace \
  --formulas $FORMULAS --state $WORK/formula_state.json \
  --output $WORK/traces.json   # TRACE_READY
python $SCRIPTS/chapter_planner.py manifest \
  --formulas $FORMULAS --output $WORK/chapter_manifest.json   # MANIFEST_READY
```
`traces.json` 含每公式的 `substituted`/`result`/`inputs.source`/`needs_verification`（反馈3 折叠块的数据源）。
```

（其中 `$SCRIPTS=/mnt/skills/public/water-drainage-report/scripts`，在步骤2 开头与 `$FORMULAS` 一并定义。）

- [ ] **Step 6: 步骤4 改写为「章节并行生成 + 冻结快照」（反馈1 提速）**

把「### 步骤4」整段标题与首部说明替换为：

```markdown
### 步骤4：生成报告（章节并行，冻结快照驱动）

**输入:** 步骤1 参数 + 步骤2 公式结果 + 步骤2 的 `traces.json`（冻结快照）+ 步骤3 模板
**架构（计算与生成分离，Approach A）:**
- **table 章**（参数表/工艺计算表/设备表）= 纯公式输出 + `traces.json` 机械渲染，**不走 LLM**：最快、最准、天然带步骤轨迹。每公式渲染为「摘要行 + `<details><summary>计算过程</summary>` 折叠块（公式来源/取值依据/代入分步/结果）」。
- **narrative 章** = 并行子 agent 生成（`task()` 工具）。每个子 agent prompt 注入**同一份冻结快照**（`traces.json` 的数值 + 该章 `generation_hint`/`content_contract`/`compliance_rules`），只返回该章 Markdown。按 `chapter_manifest` 顺序合并。

**核心不变量：** 所有数值在步骤2 固化进 `traces.json`；所有生成单元只读该快照——并行不引入跨章数值漂移。

**提速预算：** 10 章典型报告 = ~3 table 章瞬时 + ~7 narrative 章分批并行（子 agent 池 3 并发）→ 目标 ≤3min。
```

（其下「⛔ 禁止生成目录」「每章注入公式结果」表、「信息缺失策略」、LaTeX 格式规范等子段保留。）

- [ ] **Step 7: 步骤5 顶部加「本次变更」块（反馈6）**

在「### 步骤5：一次性写入 outputs」标题之后、「**输入:**」之前，插入：

```markdown
**报告顶部「本次变更」块（反馈6，仅改参重生成时）：** 若本次是 `update` 触发的定点重生成，报告顶部插入变更摘要块（取 `project_snapshot.change_log` 最新一条）：
```
> 本次变更（v{version}）：{param} {old}→{new} ⇒ 重生成章节 {affected_chapters}；{value_diffs}
```
```

- [ ] **Step 8: 步骤2 内补「改参定点重生成」流程（反馈6）**

在步骤2 的「参数修改（增量重算）」bash 块（update 命令）之后，追加定点重生成说明：

```markdown
**改参定点重生成（反馈6，替代整篇重跑）：**
```bash
# 1. 增量重算（已有）
python $SCRIPTS/formula_runner.py update --formulas $FORMULAS --state $WORK/formula_state.json \
  --param <参数名> --value <新值> --output $WORK/formula_state.json   # STATE_READY
# 2. 查受影响章节
python $SCRIPTS/formula_runner.py impacted --formulas $FORMULAS --state $WORK/formula_state.json \
  --param <参数名> --value <新值> --manifest $WORK/chapter_manifest.json   # IMPACTED_READY
# 3. 仅重生成受影响章节（table 重渲染 / narrative 子 agent 重生成），其余章节原样保留 → 内存内整体覆盖 → 单次 write_file
# 4. 刷新 traces.json + project_snapshot（version++，change_log 追加 affected_formulas/chapters/value_diffs）
```
不做像素级差异高亮 UI（顶回去）；「差异」以变更日志文本落地，复用文档空间版本能力。
```

- [ ] **Step 9: 步骤6 扩展为校验面板 + 多规范围框（反馈4/5）**

把「### 步骤6：一致性校验」的 bash 块替换为：

```bash
python $SCRIPTS/formula_runner.py check \
  --formulas $FORMULAS \
  --params "$(cat $WORK/params.json)" \
  --output $WORK/consistency_check.json   # CHECK_READY
```

并在其展示格式后追加：

```markdown
**校验面板（反馈4）：** 报告末尾附「校验面板」表：检查项 / 当前值 / 规范区间 / 结论（✅/⚠️/❌）/ 条款引用。

**多规范围框比对（反馈5）：** 对 `code_constraint_multi` 合约（如 N-multi-standard），输出每参数×每规范矩阵；Tier-2（`tier1_curated=false` 的规范）参数显示「未自动校验（规范未入库，需人工对照）」，不给 pass/fail。web_search 仅用于 discovery（规范是否存在/范围/版本年），**绝不**驱动合规 pass/fail。
```

- [ ] **Step 10: 参考文件清单更新**

把「## 参考文件」段更新为：

```markdown
- `references/formulas.json` — 12 个公式定义（系数/经验类 input 带 source + needs_verification）
- `references/reference_values.json` — 行业经验参考值库（反馈2）
- `references/standards_index.json` — 可勾选规范清单（反馈5）
- `references/consistency_contracts.json` — 一致性 + 多规范围框合约（含 code_constraint_multi）
- `scripts/formula_runner.py` — 公式 CLI（execute / update / check / trace / impacted）
- `scripts/chapter_planner.py` — 章节规划（manifest / impacted 反查）
- 知识工厂模板（优先） > 内置 fallback 10 章结构
```

- [ ] **Step 11: 验证 SKILL.md frontmatter + 内部引用一致**

Run: `python -c "import re,sys; t=open('skills/public/water-drainage-report/SKILL.md',encoding='utf-8').read(); assert t.startswith('---'); assert '步骤0' in t and 'chapter_planner' in t and 'reference_values' in t and 'trace' in t and 'impacted' in t and '围框' in t; print('SKILL.md OK')"`
Expected: 打印 `SKILL.md OK`。

- [ ] **Step 12: 提交**

```bash
git add skills/public/water-drainage-report/SKILL.md
git commit -m "feat(water-drainage): SKILL.md 流程重写集成7反馈(快照/分层放开/章节并行/折叠步骤/校验面板/多规范/定点重生成)"
```

---

## Task 10: 端到端冒烟 + 文档/anatomy 更新

**Files:**
- Modify: `backend/CLAUDE.md`（如需，仅当新增了需记录的命令——本任务判定）
- Modify: `.wolf/anatomy.md`（新增/改动文件登记）

**为什么：** 全链路验证 execute→trace→manifest→impacted→check 串通；同步 OpenWolf anatomy（新文件 `chapter_planner.py` / `reference_values.json` / `standards_index.json` / `test_chapter_planner.py`）。

- [ ] **Step 1: 全链路冒烟脚本**

Run（一条链）：
```bash
cd backend
F=../skills/public/water-drainage-report/references/formulas.json
S=../skills/public/water-drainage-report/scripts
P='{"Q":20000,"delta_t":10,"N":5,"pool_area":912,"V_suction":2099.5,"pump_motor_spacing":5.2,"filter_unit_capacity":40,"filter_area":1.13,"concurrent_backwash":5,"total_filters":25}'
PYTHONPATH=. python $S/formula_runner.py execute --formulas $F --params "$P" --output /tmp/f_state.json
PYTHONPATH=. python $S/formula_runner.py trace    --formulas $F --state /tmp/f_state.json --output /tmp/traces.json
python        $S/chapter_planner.py manifest      --formulas $F --output /tmp/manifest.json
PYTHONPATH=. python $S/formula_runner.py impacted --formulas $F --state /tmp/f_state.json --param Q --value 25000 --manifest /tmp/manifest.json --output /tmp/impacted.json
PYTHONPATH=. python $S/formula_runner.py check    --formulas $F --params "$P" --output /tmp/check.json
echo "--- markers ---"; grep -o "STATE_READY\|TRACE_READY\|MANIFEST_READY\|IMPACTED_READY\|CHECK_READY" /tmp/f_state.json /tmp/traces.json /tmp/manifest.json /tmp/impacted.json /tmp/check.json 2>/dev/null; echo "stdout markers above (one per command)"
```
Expected: 每条命令各打印一个 `*_READY: /tmp/...` 标记到 stdout（5 个标记）。`/tmp/impacted.json` 的 `affected_chapters` 含 `ch5_calc`。

- [ ] **Step 2: 跑全量引擎 + 章节测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_formula_graph.py tests/test_chapter_planner.py -v`
Expected: 全部 PASS。

- [ ] **Step 3: lint（ruff）**

Run: `cd backend && PYTHONPATH=. uv run ruff check app/extensions/formula_engine/ && uv run ruff format --check app/extensions/formula_engine/`
Expected: 无错误（如有格式问题，`uv run ruff format app/extensions/formula_engine/` 修正后重跑）。

- [ ] **Step 4: 更新 anatomy.md**

在 `.wolf/anatomy.md` 登记 3 个新文件 + 改动（按 OpenWolf 规范，每个一行：路径 — 描述 — token 估算）。具体追加：
- `skills/public/water-drainage-report/scripts/chapter_planner.py` — 章节映射+受影响章节反查（反馈6）。
- `skills/public/water-drainage-report/references/reference_values.json` — 系数/经验类行业参考值库（反馈2）。
- `skills/public/water-drainage-report/references/standards_index.json` — 可勾选规范清单（反馈5）。
- `backend/tests/test_chapter_planner.py` — chapter_planner 单测。
- 更新 `graph.py` / `consistency.py` / `formula_runner.py` / `formulas.json` / `consistency_contracts.json` / `SKILL.md` / `test_formula_graph.py` 的描述（注明新增能力）。

- [ ] **Step 5: append memory.md 一行**

在 `.wolf/memory.md` 追加一行（OpenWolf action log）：
```
| <HH:MM> | 给排水技能优化实施完成（10任务：引擎trace+multistd/数据4json/runner trace+impacted/chapter_planner/SKILL重写） | 多文件 | 全绿，harness零改动 | ~tokens |
```

- [ ] **Step 6: 提交**

```bash
git add .wolf/anatomy.md .wolf/memory.md
git commit -m "docs(water-drainage): 给排水技能优化实施收尾—anatomy/memory同步"
```

---

## 附录：spec 覆盖对账

| 反馈 | spec 节 | 实现任务 |
|---|---|---|
| 1 提速 ≤3min | §3.2 §5.2 | Task 9 步骤6（章节并行 + 冻结快照） |
| 2 分层放开默认值 | §3.1 §7.1 §7.2 | Task 1（字段）+ Task 4（formulas.json）+ Task 5（reference_values）+ Task 9 步骤1/4 |
| 3 黑箱折叠步骤 | §8.1 §10 | Task 2（get_step_trace）+ Task 7（trace 子命令）+ Task 9 步骤5/6 |
| 4 校验面板 | §1.2 §10 | Task 9 步骤9（既有 check + 面板呈现） |
| 5 多规范围框 | §3.3 §7.3 §7.4 §10 | Task 3（multi_standard_matrix）+ Task 5（standards_index）+ Task 6（合约）+ Task 9 步骤4/9 |
| 6 改参定点重生成 | §5.1 §6 §8.2 | Task 7（impacted）+ Task 8（chapter_planner）+ Task 9 步骤7/8 |
| 7 会话快照+版本 | §7.5 §9 §10 | Task 9 步骤3（步骤0 快照）+ 步骤7（变更块） |
| harness 零改动（硬约束） | §2.2⑤ | 全部任务落 app/extensions + skills + tests |

## 附录：顶回去的项（不在本计划）

- 30s 提速（目标 ≤3min）。
- 条款级规范全量库（走 Tier-1 人工入库 + Tier-2 标注）。
- web_search 驱动合规（仅 discovery）。
- 新建响应式前端编辑器（差异=变更日志文本；版本历史复用文档空间）。
- 机械 table 渲染器 v2（§14⑥，v1 由 agent + traces.json 渲染；Task 8 只做映射）。
