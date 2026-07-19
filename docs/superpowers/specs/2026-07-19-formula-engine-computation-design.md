# 公式引擎计算库选型设计

日期: 2026-07-19
状态: 已确认
分支: main-dev-fork

## 背景

当前公式引擎 (`app/extensions/formula_engine/graph.py`) 使用 Python `eval()` + `math` 标准库执行公式表达式。命名空间仅包含 `math`、`abs`、`round`、`min`、`max`、`sqrt`、`pow`。

这能覆盖给排水计算书中 80% 的纯代数公式（如 `Qe = Q * KZF * delta_t`），但工程设计中还涉及：
- 迭代试算（管径选择、换热器温差收敛）
- 查表内插（KZF 蒸发系数、摩擦因子）
- 方程组联立（管径-流速-水头损失）

## 讨论过程

### 评估的计算引擎

| 引擎 | 类型 | 评估结论 |
|------|------|---------|
| **Wolfram/Mathematica** | 符号+数值 | 付费API，不能离线部署。不适用 |
| **MathGPT** | LLM+符号 | 在线服务，化工关联式无内置。不适用 |
| **SymPy** | Python符号计算 | 过度设计。工程设计公式来自规范，不需推导/化简。方程"求解"实际是离散选型非连续求根。不引入 |
| **eval()+math** | 纯数值 | 当前方案，处理80%公式 ✅ |
| **scipy** | 数值计算 | 迭代求解、插值查表。需要时引入 |
| **pint** | 单位校验 | 轻量级，防止m³/h和L/s混用。按需引入 |

### 关键决策

**不引入符号计算引擎。** 理由：
1. 工程设计公式来自 GB/HG 规范，工程师照抄标准公式，不推导新公式
2. 所谓"方程求解"实际是离散选型（管径只能选 DN200/250/300，不是连续求根）
3. 公式简化不是需求——标准公式已是最简形式
4. 单位校验可以用更轻量的 `pint` 实现

**复杂计算走 MCP 工具，不内嵌到引擎。** 理由：
1. 引擎保持轻量——DAG编排 + 表达式求值
2. 迭代求解、插值等封装为独立 MCP 工具，可被任何 agent/skill 复用
3. 符合 DeerFlow 的 extension-MCP 架构

## 架构

```
                    FormulaGraph (编排层 — 不变)
                    依赖推导 · 拓扑排序 · 脏传播 · 参数传递
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ 代数求值  │  │ MCP 工具  │  │ MCP 工具  │
        │ eval()   │  │ 迭代求解  │  │ 插值查表  │
        │ + math   │  │ optimize  │  │ interp    │
        └──────────┘  └──────────┘  └──────────┘
        已有，不动      按需新增       按需新增
```

## 实施计划

### Phase 1: namespace 扩展（零依赖，立即实施）

扩展 `_execute_node()` 中的命名空间：

```python
namespace = {
    # 现有
    "math": math, "abs": abs, "round": round, "min": min, "max": max,
    "sqrt": math.sqrt, "pow": pow,
    # 新增工程常用函数
    "log": math.log, "log10": math.log10, "exp": math.exp,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "pi": math.pi, "e": math.e,
}
```

### Phase 2: MCP 计算工具（按需，scipy 依赖）

当遇到具体需求时实现：

| MCP 工具 | 底层库 | 触发场景 |
|---------|--------|---------|
| `formula_iterate` | `scipy.optimize.newton` | 管径试算、换热器收敛 |
| `formula_interpolate` | `scipy.interpolate.interp1d` | 查表内插（KZF等） |
| `formula_solve_linear` | `numpy.linalg.solve` | 线性方程组 |

### Phase 3: 步骤追溯（零依赖）

每个公式执行时记录：

```json
{
  "formula_id": "Qe",
  "step": "Qe = Q * KZF * delta_t = 20000 * 0.001461 * 10 = 292.20 m³/h",
  "inputs": {"Q": 20000, "KZF": 0.001461, "delta_t": 10},
  "output": 292.2
}
```

### 不实施

- ❌ SymPy 符号计算 → 过度设计
- ❌ Wolfram/MathGPT → 不能离线 + 付费
- ❌ FormulaNode.type 字段 → 保持引擎简单，复杂逻辑走 MCP

## 不变的内容

- `FormulaGraph` 核心逻辑（依赖推导、拓扑排序、脏传播、增量重算）
- `FormulaNode` 数据结构（expression + inputs + outputs）
- `formula_runner.py` CLI 接口（execute/update/check 三命令）
- `formulas.json` 格式
