"""跨服务 wire 契约的 golden 定义（产出侧单一来源）。

EAI-CUSTOM (2026-09-23): ``GET /api/permissions/scope`` 的响应体是 gateway 与 OntoStudio
之间的**线格式契约**，而两侧各自持有 FilterRule 数据类（独立服务，无法共享代码）。

**为什么需要一个共读的 golden 文件**：审查者的变异 M1b 实测——把产出侧的 ``children``
键改名 ``kids``，**主仓 6 绿 + OntoStudio 354 绿，两侧全绿**。原因是两侧的测试都只验证
"自己那半边"（gateway 验自己发的形状、OntoStudio 验自己收的形状），**没有任何一处同时看
两边**。运行期后果还只在对端才炸（``or`` 丢 children 会静默编译成 FALSE = 全拒）。

golden 就是那个唯一的交叉点：产出侧改了形状 → 与 golden 对不上 → 红；把 golden 更新成新
形状 → 消费侧编译不出来 → 红。**所以 golden 必须钉产出侧**：``scope.py::from_wire`` 刻意
宽容（``children: null`` 与 ``[]`` 都吃），只钉接受侧会掩盖漂移。

- 产出侧断言：``backend/tests/test_permissions_scope_endpoint.py::test_wire_golden_matches_producer_output``
- 消费侧断言：``ontostudio/backend/tests/test_scope_wire_contract.py``

**再生成**：``cd backend && PYTHONPATH=tests ./.venv/Scripts/python.exe -c "import _wire_golden as w; w.write()"``
**不得手写 golden**——手写的 golden 只能证明写它的人当时的想法，证明不了产出侧真的这么发。

形态取的是**真实合成路径**（``DataScopeEngine.get_data_scope`` / ``FilterRule.from_template``），
不是手搓的等价物；只有 ``eq``/``in``/``in_empty``/``overlap`` 直取 ``from_template``，其余走
引擎，且引擎用局部构造的 scope（不读 permissions.yaml，避免 golden 随模板编辑而漂移）。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.extensions.auth.datascope import DataScopeEngine
from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.registry import DataScope

GOLDEN_PATH = Path(__file__).resolve().parent / "data" / "permissions_scope_wire_golden.json"

_D1 = "11111111-1111-1111-1111-111111111111"
_D2 = "22222222-2222-2222-2222-222222222222"

# 两个身份：带 dept_ids 的、与不带 dept_ids 的（后者产出可达的空集 `in`）。
_IDENT = AttributeSet(user_id="U-deadbeef", username="tester", role_code="user", dept_ids=[_D1, _D2], member_projects=["P-33333333"])
_IDENT_NO_DEPT = AttributeSet(user_id="U-deadbeef", username="tester", role_code="user")

_S_ALL = DataScope(id="s_all", display_name="all", rule_template={})
_S_DEPT = DataScope(id="s_dept", display_name="dept", rule_template={"dept_id IN": "$identity.dept_ids"})


def _engine(granted: list[str]) -> DataScopeEngine:
    return DataScopeEngine(scopes_by_resource={"res": [_S_ALL, _S_DEPT]}, role_data_scopes={"user": granted})


def build_cases() -> dict[str, FilterRule]:
    """各形态 → 用产出侧的真实构造路径得到 FilterRule（键名即 golden 的 case 名）。"""
    return {
        "allow_all": _engine(["s_all"]).get_data_scope(_IDENT, "res"),
        "none_allow": _engine([]).get_data_scope(_IDENT, "res"),
        "in": _engine(["s_dept"]).get_data_scope(_IDENT, "res"),
        # 有 deny scope 时 get_data_scope 合成 and[allow, not(deny)] —— and+not 的真实来源
        "and_not": _engine(["s_all"]).get_data_scope(_IDENT, "res", deny_scope_ids={"s_dept"}),
        "eq": FilterRule.from_template({"user_id": "$identity.user_id"}, _IDENT),
        # 可达的空集：身份没有 dept_ids 时 IN 分支产出 value=[]（asyncpg 元素类型推断的靶子）
        "in_empty": FilterRule.from_template({"dept_id IN": "$identity.dept_ids"}, _IDENT_NO_DEPT),
        # M-4 的靶子：from_template 会把 dept_ids 强转成 uuid.UUID，to_wire 必须归一为字符串
        "overlap": FilterRule.from_template({"allowed_depts OVERLAP": "$identity.dept_ids"}, _IDENT),
    }


def build() -> dict:
    return {
        "schema": "permissions-scope-wire/v1",
        "produced_by": "backend/app/extensions/auth/engine.py::FilterRule.to_wire",
        "consumed_by": "ontostudio/backend/app/ontology/scope.py::FilterRule.from_wire",
        "regenerate_with": 'cd backend && PYTHONPATH=tests python -c "import _wire_golden as w; w.write()"（不得手写）',
        "cases": {name: rule.to_wire() for name, rule in build_cases().items()},
    }


def load() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def write() -> None:
    GOLDEN_PATH.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()
    print(f"wrote {GOLDEN_PATH}")
