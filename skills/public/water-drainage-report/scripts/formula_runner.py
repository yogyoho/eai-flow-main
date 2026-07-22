#!/usr/bin/env python3
"""给排水设计专篇 — 公式计算 CLI 工具。

这是 water-drainage-report 技能的核心脚本。技能通过 bash 调用本脚本的三个子命令
来驱动公式 DAG 引擎，实现设计参数→公式计算→增量重算→一致性校验的完整管线。

三个子命令：
    execute — 加载公式定义 + 用户参数 → 构建公式图 → 全量执行 → 输出结果
    update  — 修改单个参数 → 从状态文件恢复上下文 → 增量重算 → 输出变更摘要
    check   — 加载公式定义 + 参数 → 执行 → 规范性校验（容积比、浓缩倍数等）

使用示例:
    # 首次执行：计算全部公式
    python formula_runner.py execute \\
        --formulas references/formulas.json \\
        --params '{"Q": 20000, "delta_t": 10, "N": 5}' \\
        --output /tmp/f_state.json

    # 参数变更：修改 Q 后增量重算
    python formula_runner.py update \\
        --formulas references/formulas.json \\
        --state /tmp/f_state.json \\
        --param Q --value 25000

    # 一致性校验
    python formula_runner.py check \\
        --formulas references/formulas.json \\
        --params '{"Q": 20000, "N": 3}'

依赖:
    - formulas.json: 公式定义集（12 个给排水计算公式，含表达式、输入参数来源、输出单位）
    - FormulaGraph: 通用公式 DAG 引擎（app.extensions.formula_engine.graph）
    - state.json: 上次执行的状态快照，用于 update 命令恢复上下文
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── 路径设置：将 backend 加入 Python 搜索路径 ──
# 本脚本位于 skills/public/water-drainage-report/scripts/ 目录下，
# backend 在项目根目录的 backend/ 下。需向上 5 级到达项目根，再进入 backend。
_BACKEND = Path(__file__).resolve().parents[5] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# 从通用公式引擎导入核心类
from app.extensions.formula_engine import (
    FormulaGraph,
    FormulaNode,
    ParamSource,
    ParamSourceType,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 数据加载与图构建
# ═══════════════════════════════════════════════════════════════════════════════

def load_formulas(path: str) -> list[dict]:
    """从 JSON 文件加载公式定义列表。

    formulas.json 的结构：
        {
            "description": "循环水装置给排水设计计算 — 公式定义集",
            "source": "GB/T 50746-2012 ...",
            "formulas": [
                {
                    "id": "Qe",
                    "name": "蒸发水量",
                    "section": "6.1.1",
                    "expression": "Q * KZF * delta_t",
                    "inputs": {...},
                    "outputs": {"Qe": "m3/h"}
                },
                ...
            ]
        }

    返回 formuas 数组，每个元素是一个公式的完整定义字典。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["formulas"]


def build_graph(formulas_data: list[dict], params: dict) -> FormulaGraph:
    """从 JSON 公式定义 + 用户参数构建 FormulaGraph。

    构建流程：
    1. 遍历 formulas_data 中的每个公式定义
    2. 对每个公式，根据 inputs 中的 type 字段构造对应的 ParamSource
       - user_input/lookup_table/code_requirement: 使用用户参数覆盖默认值
       - formula_output: 建立对上游公式的依赖引用
    3. 调用 graph.build() 推导依赖边 + 拓扑排序 + 初始化全局参数表

    Args:
        formulas_data: load_formulas() 返回的公式定义列表
        params: 用户提供的参数值 {"Q": 20000, "delta_t": 10, ...}

    Returns:
        已 build 的 FormulaGraph 实例，可直接调用 execute()
    """
    graph = FormulaGraph()
    nodes: list[FormulaNode] = []

    for fdef in formulas_data:
        inputs: dict[str, ParamSource] = {}

        for pname, psrc in fdef["inputs"].items():
            # 解析参数来源类型
            src_type = ParamSourceType(psrc["type"])
            value = psrc.get("value")

            # 非公式输出类型的参数 → 优先使用用户提供的值覆盖默认值
            # 这是参数提取层的关键：设计说明书中提取的参数通过 params dict 注入
            if src_type != ParamSourceType.FORMULA_OUTPUT and pname in params:
                value = params[pname]

            inputs[pname] = ParamSource(
                type=src_type,
                value=value,
                unit=psrc.get("unit", ""),
                source_formula_id=psrc.get("source_formula_id", ""),
                source_param_name=psrc.get("source_param_name", ""),
                description=psrc.get("description", ""),
            )

        node = FormulaNode(
            id=fdef["id"],
            name=fdef["name"],
            section=fdef.get("section", ""),
            expression=fdef["expression"],
            inputs=inputs,
            outputs=fdef["outputs"],
        )
        nodes.append(node)

    # 批量添加 → 构建依赖图 → 拓扑排序 → 初始化参数表
    graph.add_formulas(nodes)
    graph.build()
    return graph


# ═══════════════════════════════════════════════════════════════════════════════
# 子命令: execute — 全量执行所有公式
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_execute(args: argparse.Namespace) -> None:
    """execute 子命令：加载公式定义 + 用户参数 → 构建图 → 全量执行。

    输出 JSON 包含:
    - results: {公式ID: {输出参数名: 计算值}}  如 {"Qe": {"Qe": 292.2}}
    - execution_order: 拓扑排序批次 [[batch0], [batch1], ...]
    - dependencies: 正向依赖图 {公式ID: [依赖的上游ID, ...]}
    - all_params: 全局参数表（用户输入 + 全部公式计算结果）

    如果指定了 --output，将完整状态写入文件并打印 STATE_READY: <路径>。
    下游（技能/agent）通过检查 stdout 中的 STATE_READY 标记确认执行成功。
    """
    formulas = load_formulas(args.formulas)
    params = json.loads(args.params) if args.params else {}

    graph = build_graph(formulas, params)
    results = graph.execute()

    output: dict = {
        "results": results,
        "execution_order": graph.execution_order,
        "dependencies": {k: sorted(v) for k, v in graph.dependencies.items()},
        "all_params": graph.get_all_params(),
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"STATE_READY: {args.output}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════════════════════
# 子命令: update — 修改单个参数并增量重算
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_update(args: argparse.Namespace) -> None:
    """update 子命令：从状态文件恢复上下文 → 修改参数 → 增量重算 → 输出变更摘要。

    与 execute 的区别：
    - execute 是"从零开始"，适用于首次计算
    - update 是"修改后重算"，从上次的状态文件恢复参数上下文
      这样用户不需要重新提供全部参数，只改需要改的那一个

    流程:
    1. 加载公式定义
    2. 从状态文件 (--state) 中恢复用户参数（过滤掉公式输出，只保留用户输入）
    3. 用恢复的参数重新构建公式图 + 执行一次（恢复到修改前的状态）
    4. 调用 graph.update_param() 修改目标参数 → 自动传播脏标记
    5. 再次执行 → 仅重算受影响的公式
    6. 输出变更摘要（如 "Qe.Qe: 292.2 → 365.2"）

    输出 JSON 包含:
    - affected_formulas: 受影响的公式 ID 列表（拓扑执行顺序）
    - changes: 变更摘要 {formula_id.output: "旧值 → 新值"}
    - results: 重算后的全部公式结果
    """
    formulas = load_formulas(args.formulas)

    # 从状态文件恢复参数上下文
    with open(args.state, "r", encoding="utf-8") as f:
        state = json.load(f)

    # 从 all_params 中提取用户输入参数（key 中不含 "." 的为原始输入参数）
    # 公式输出的 key 格式为 "formula_id.output_name"，含 "." → 过滤掉
    user_params: dict = {}
    for key, val in (state.get("all_params") or {}).items():
        if "." not in key:                     # 用户输入参数的特征
            user_params[key] = val

    # 用恢复的参数重建图 → 首次执行恢复到快照状态
    graph = build_graph(formulas, user_params)
    graph.execute()

    # 修改目标参数 → 脏标记传播 → 增量重算
    affected = graph.update_param(args.param, float(args.value))
    results = graph.execute()
    changes = graph.last_change_summary()

    output: dict = {
        "affected_formulas": affected,
        "results": results,
        "changes": changes,
        "execution_order": graph.execution_order,
        "all_params": graph.get_all_params(),
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"STATE_READY: {args.output}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════════════════════
# 子命令: check — 执行公式 + 规范性校验
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_check(args: argparse.Namespace) -> None:
    """check 子命令：执行公式计算后，进行规范性校验。

    当前实现的校验项:
    1. 系统容积比: V_system / Q 应在 1/3 ~ 1/2 之间 (GB/T 50746 §6.1.9)
       - < 1/3 → warn（循环水量过大，系统缓冲不足）
       - > 1/2 → warn（系统容积过大，药剂停留时间可能超限）
    2. 浓缩倍数 N:
       - < 3.0 → fail（低于 GB 50648 §4.1.1 最低要求，必须修正）
       - < 5.0 → warn（低于推荐值，建议提高浓缩倍数以节约用水）

    输出 JSON:
        {
            "issues": [
                {"severity": "fail|warn|pass", "check": "检查项名", "detail": "..."}
            ],
            "all_params": {...}
        }

    注意：这是简化的内联校验。完整的 11 条合约校验由 ConsistencyEngine 负责，
    对应的合约文件在 references/consistency_contracts.json。
    """
    formulas = load_formulas(args.formulas)

    # 加载参数并执行公式计算
    params = json.loads(args.params) if args.params else {}
    graph = build_graph(formulas, params)
    graph.execute()

    issues: list[dict] = []

    # ── 校验 1: 系统容积比 ──
    v_ratio = graph.get_param("V_ratio_check", "V_ratio_check")
    if v_ratio is not None:
        if v_ratio < 1 / 3:
            issues.append({
                "severity": "warn",
                "check": "容积比",
                "detail": f"系统容积比 {v_ratio:.3f} 低于 1/3，不满足 GB/T 50746 §6.1.9"
            })
        elif v_ratio > 1 / 2:
            issues.append({
                "severity": "warn",
                "check": "容积比",
                "detail": f"系统容积比 {v_ratio:.3f} 超过 1/2"
            })
        else:
            issues.append({
                "severity": "pass",
                "check": "容积比",
                "detail": f"系统容积比 {v_ratio:.3f}，满足 GB/T 50746 §6.1.9 (1/3~1/2)"
            })

    # ── 校验 2: 浓缩倍数 ──
    N = params.get("N")
    if N is not None:
        if N < 3:
            issues.append({
                "severity": "fail",
                "check": "浓缩倍数",
                "detail": f"N={N}，低于 GB 50648 §4.1.1 最低要求 3.0"
            })
        elif N < 5:
            issues.append({
                "severity": "warn",
                "check": "浓缩倍数",
                "detail": f"N={N}，宜≥5.0 (GB 50648 §4.1.1)"
            })
        else:
            issues.append({
                "severity": "pass",
                "check": "浓缩倍数",
                "detail": f"N={N}，满足要求"
            })

    output = {"issues": issues, "all_params": graph.get_all_params()}

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"CHECK_READY: {args.output}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """CLI 主入口：解析子命令并路由到对应的处理函数。

    三个子命令:
        execute  — 全量执行（首次计算）
        update   — 增量重算（参数变更后）
        check    — 规范性校验（合规检查）
    """
    parser = argparse.ArgumentParser(
        description="给排水设计专篇 — 公式计算 CLI 工具"
    )
    sub = parser.add_subparsers(dest="command")

    # execute 子命令
    p_exec = sub.add_parser("execute", help="构建公式图并全量执行")
    p_exec.add_argument("--formulas", required=True,
                        help="公式定义 JSON 文件路径（如 references/formulas.json）")
    p_exec.add_argument("--params", default="{}",
                        help="用户参数 JSON（如 '{\"Q\": 20000, \"N\": 5}'）")
    p_exec.add_argument("--output",
                        help="输出状态文件路径（供 update 命令使用）")

    # update 子命令
    p_update = sub.add_parser("update", help="修改参数并增量重算")
    p_update.add_argument("--formulas", required=True,
                          help="公式定义 JSON 文件路径")
    p_update.add_argument("--state", required=True,
                          help="上次 execute 输出的状态文件路径")
    p_update.add_argument("--param", required=True,
                          help="要修改的参数名（如 Q, N, delta_t）")
    p_update.add_argument("--value", required=True,
                          help="新的参数值")
    p_update.add_argument("--output",
                          help="输出更新后的状态文件路径")

    # check 子命令
    p_check = sub.add_parser("check", help="执行公式后运行规范性校验")
    p_check.add_argument("--formulas", required=True,
                         help="公式定义 JSON 文件路径")
    p_check.add_argument("--params", default="{}",
                         help="用户参数 JSON")
    p_check.add_argument("--output",
                         help="输出校验结果文件路径")

    args = parser.parse_args()

    if args.command == "execute":
        cmd_execute(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "check":
        cmd_check(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
