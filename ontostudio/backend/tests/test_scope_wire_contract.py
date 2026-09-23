"""跨服务 wire 契约的**消费侧**钉子（golden 共读）。

EAI-CUSTOM (2026-09-23, I-2): ``GET /api/permissions/scope`` 的响应体是 gateway 与
OntoStudio 之间的线格式契约，而两侧各自持有 FilterRule 数据类（独立服务，无法共享代码）。

**为什么需要它**：审查者的变异 M1b 实测——把产出侧的 ``children`` 键改名 ``kids``，
**两侧测试全绿**（主仓 6 绿 + OntoStudio 354 绿）。两侧都只验证"自己那半边"，没有任何一处
同时看两边；而运行期后果只在对端才炸（``or`` 丢 children 会静默编译成 ``FALSE`` = 全拒）。

golden（``backend/tests/data/permissions_scope_wire_golden.json``）是唯一的交叉点：
- 产出侧 ``backend/tests/test_permissions_scope_endpoint.py`` 断 ``to_wire == golden``；
- **本文件** 断 ``from_wire(golden)`` 仍能编译成预期的参数化片段。

**为什么 golden 必须由产出侧拥有**：本侧 ``from_wire`` 刻意宽容（``children: null`` 与 ``[]``
都吃，见 scope.py），只钉接受侧会掩盖产出侧的漂移——所以 golden 由产出侧代码生成、本侧
只做回读断言。

**本文件不断言产出侧会怎么改**：它只断言"今天这份 golden 我读得懂、编译得出预期形状"。
两侧同时红才算抓住一次真漂移，任一侧单独红都说明契约动了。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ontology.scope import FilterRule, ScopeCompileError, rule_to_sql

# golden 路径：从本文件向上找同时含 backend/ 与 ontostudio/ 的仓库根。
# 为什么不用固定层数：本套件在宿主跑（ontostudio/backend/.venv），但换棵工作树/换层数就失效；
# 向上搜索与"golden 属产出侧、消费侧只读"的约定一致。
_GOLDEN_REL = Path("backend/tests/data/permissions_scope_wire_golden.json")


def _golden_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _GOLDEN_REL
        if candidate.exists():
            return candidate
    pytest.skip(f"跨服务契约 golden 不在本机：向上未找到 {_GOLDEN_REL}。本套件需与主仓同树（宿主上跑 ontostudio/backend/.venv 时天然满足）；容器内未挂载主仓，则该守卫**未执行**——不是通过。")


# 消费侧编译预期：golden 各形态 → (WHERE 片段, 命名参数)。
# 这些字符串是**本侧编译器**的产出（scope.py::rule_to_sql，bindings=None 即恒等映射、
# 字段加双引号），硬编码是有意的：它把"消费侧怎么理解这份线格式"也钉住——产出侧改形状、
# 或本侧改编译，都会在这里露出来。
_EXPECTED: dict[str, tuple[str, dict]] = {
    "allow_all": ("TRUE", {}),
    "none_allow": ("FALSE", {}),
    "eq": ('"user_id" = :scope_0', {"scope_0": "U-deadbeef"}),
    "in": (
        '"dept_id" = ANY(:scope_0)',
        {"scope_0": ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]},
    ),
    # 可达的空集：身份无 dept_ids 时产出 IN value=[]（asyncpg 元素类型推断的靶子，
    # 消费侧有真库测试证明它跑得通且 fail-closed；这里只钉它**编译得出**）。
    "in_empty": ('"dept_id" = ANY(:scope_0)', {"scope_0": []}),
    # 复合树：get_data_scope 有 deny 时合成 and[allow_all, not(in)]
    "and_not": (
        '(TRUE AND NOT ("dept_id" = ANY(:scope_0)))',
        {"scope_0": ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]},
    ),
    # M-4：产出侧在 to_wire 内把 uuid 归一为字符串，故本侧读到的是字符串数组
    "overlap": (
        '"allowed_depts" && :scope_0',
        {"scope_0": ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]},
    ),
}


def _golden() -> dict:
    return json.loads(_golden_path().read_text(encoding="utf-8"))


def test_golden_covers_exactly_the_expected_shapes():
    """形态集合必须与消费侧预期表逐一对齐——golden 增删形态时本侧必须同步表态。

    没有这条，产出侧加一个新形态（比如将来接上 ``ne``）本侧会静默不覆盖。
    """
    assert set(_golden()["cases"]) == set(_EXPECTED), "golden 与消费侧预期表的形态集合不一致"


@pytest.mark.parametrize("case", sorted(_EXPECTED))
def test_consumer_compiles_every_golden_case(case: str):
    """逐形态回读：``from_wire(golden)`` 编译出的片段与参数必须与预期逐字相等。"""
    wire = _golden()["cases"][case]
    rule = FilterRule.from_wire(wire)
    fragment, params = rule_to_sql(rule)
    assert (fragment, params) == _EXPECTED[case]


def test_golden_is_round_trippable_and_renamed_children_would_break():
    """反向哨兵：把 golden 的 ``children`` 键改名 → 本侧必须编译不出预期形状。

    这条是 M1b 的**本地复现**（那次的变异在产出侧，结果是两侧全绿）。这里把同一个变异施加在
    golden 上，证明"消费侧确实看得见这个键"——否则本文件对 children 类漂移就是盲的。
    """
    golden = _golden()
    mangled = json.loads(json.dumps(golden))  # 深拷贝，别动真 golden
    for wire in mangled["cases"].values():
        if "children" in wire:
            wire["kids"] = wire.pop("children")

    and_not = FilterRule.from_wire(mangled["cases"]["and_not"])
    with pytest.raises(ScopeCompileError):  # 空 and 被拒（fail-closed，优于静默编译成 FALSE）
        rule_to_sql(and_not)
