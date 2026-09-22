# OntoStudio 动作层与域级实例权限 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 OntoStudio 加一条受治理的写路径——动作在 registry 里声明、经权限与数据范围校验、在 Postgres 事务内落库并记审计，同时经 MCP 暴露给 agent。

**Architecture:** 声明式动作（`registry/*.yaml` 的 `actions:` 段）→ 单条执行管线（解析 → 权限 → 数据范围 → `FOR UPDATE` 锁定 → 前置校验 → UPDATE → 审计行）→ 提交后增量重投影进内核图。Postgres `dg_*` 是唯一真相源，图是派生视图。权限的**策略**在 `config/permissions.yaml`（gateway 为真相源，经 `/api/permissions/scope` 下发序列化 `FilterRule`），**物理绑定**在 registry（`scope_resource` + 可选 `scope_bindings`）。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async + asyncpg（NullPool）/ pydantic v2（`extra="forbid"`）/ pyoxigraph / pytest + pytest-asyncio / httpx

**Spec:** `docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md`

**工作目录约定**：除非另注，所有命令在 `D:\eai\eai-flow-main\ontostudio\backend` 下执行；gateway 侧改动在 `D:\eai\eai-flow-main\backend` 下执行。测试统一 `PYTHONPATH=. uv run pytest <path> -v`（若 `uv run` 在该环境不工作，用 `PYTHONPATH=. ./.venv/Scripts/python.exe -m pytest <path> -v`——Task 1/2 实测可用）。

### ⚠️ 每个 Task 的验证清单必须包含 format 检查（Task 1–2 的教训）

**ontostudio 没有 Makefile，所以没有 `make lint` 替你兜底。** 主仓 `make lint` 是**两条**命令：`ruff check .` **加** `ruff format --check .`。只跑前者会漏掉排版问题——Task 2 就漏了一次（新测试文件是全仓唯一未格式化的文件，被规格审查者抓到）。

所以每个 Task 的 Verify 步骤固定为：

```bash
./.venv/Scripts/python.exe -m ruff check <改动路径>
./.venv/Scripts/python.exe -m ruff format --check <改动路径>   # ← 别省这一条
```

若 `format --check` 报要重排，直接 `ruff format <该文件>` 修掉再提交。**只格式化本次改动的文件**，不要顺手格式化别的（`app/auth.py:272` 有一处既有未格式化，不属任何 Task 的范围）。

**本计划的代码块一律不是 format-clean 的**（Task 1–2 已出现 5 例：`-> "StateChange"` 引号触发 UP037、未用 import 触发 F401、import 顺序触发 I001、紧凑 dict 被重排、以及一条陈旧计数）。**实现者请把「跑 format 后重排」视为本任务的常规步骤，而非偏离**——但仍要在报告的偏离清单里如实计入。

### 派发给实现者的通用要求（每个 Task 一致）

- **若计划给的代码过不了计划给的测试或 lint，不要改测试迁就代码、也不要默默改了了事。** 判明是计划错还是测试错，按"哪个符合本任务声明的意图"定，然后在报告里**点名哪一行、为什么、怎么改的**。Task 1–2 共 5 次这样顶回来，每次都值回票价。
- **偏离清单以「全部偏离」为准，包含 lint/format 驱动的调整。** 只报功能性的偏离会制造"已完全合规"的错觉。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `ontostudio/backend/app/ontology/scope.py`（新建） | `FilterRule` 数据类（wire 编解码）+ `rule_to_sql()` 编译为参数化 WHERE |
| `ontostudio/backend/app/ontology/actions/__init__.py`（新建） | 包标记 |
| `ontostudio/backend/app/ontology/actions/sql_write.py`（新建） | 标识符白名单 + 前置条件 WHERE + UPDATE SET 构造。**唯一拼 SQL 的地方** |
| `ontostudio/backend/app/ontology/actions/executor.py`（新建） | 执行管线：解析 → 鉴权 → 取范围 → 事务 → 审计 → 重投影 |
| `ontostudio/backend/app/ontology/schemas.py`（改） | `Precondition` / `StateChange` / `ActionSpec`；`DomainFile.actions`；`ObjectType.scope_resource` / `scope_bindings` |
| `ontostudio/backend/app/ontology/registry.py`（改） | 加载 `actions:` 段 + 交叉引用校验（target/field 必须已声明） |
| `ontostudio/backend/app/ontology/registry/doc_graph.yaml`（改） | 声明 `review_entity.confirm` / `.reject`；`status` enum 加 `rejected`；`graph_entity.scope_resource: ontology` |
| `ontostudio/backend/app/ontology/kernel/validate.py`（改） | status 枚举 + 提示文案加 `rejected` |
| `ontostudio/backend/app/doc_graph/tables.py`（改） | `DgActionAudit` ORM |
| `ontostudio/backend/app/ontology/routers.py`（改） | `POST /api/extensions/ontology/actions/invoke` |
| `ontostudio/backend/app/ontology/mcp.py`（改） | `invoke_action` / `review_entity` 工具 + `describe_ontology` 附动作清单 |
| `ontostudio/backend/scripts/ontology_lint.py`（改） | scope 绑定校验 |
| `backend/app/extensions/auth/routers.py`（改） | `GET /api/permissions/scope` |
| `backend/app/extensions/auth/authz_cache.py`（新建） | 授权判定的缓存键修正（见 Task 6） |
| `config/permissions.yaml` + `deploy/offline/config/permissions.yaml`（改） | `ontology:action:review` operation + `ontology_all` data_scope |

**实现顺序的理由**：1→4 是纯函数与纯校验（无 IO，最好测），5 才组合它们；6 是 gateway 侧前置（缺它 executor 拿不到范围规则）；7→8 是暴露面；9→10 收口与端到端。

---

## Task 1: `scope.py` —— FilterRule 与 SQL 编译

**Files:**
- Create: `ontostudio/backend/app/ontology/scope.py`
- Test: `ontostudio/backend/tests/test_scope_rule_to_sql.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_scope_rule_to_sql.py
"""FilterRule → 参数化 WHERE 编译。安全要点：字段名走标识符白名单，值一律绑定。"""
import pytest

from app.ontology.scope import FilterRule, ScopeCompileError, rule_to_sql


def test_allow_all_compiles_to_true():
    assert rule_to_sql(FilterRule(operator="allow_all")) == ("TRUE", {})


def test_none_allow_compiles_to_false():
    assert rule_to_sql(FilterRule(operator="none_allow")) == ("FALSE", {})


def test_eq_binds_value_not_interpolates():
    sql, params = rule_to_sql(FilterRule(operator="eq", field="dept_id", value="d1"))
    assert sql == '"dept_id" = :scope_0'
    assert params == {"scope_0": "d1"}


def test_in_uses_any():
    sql, params = rule_to_sql(FilterRule(operator="in", field="id", value=["a", "b"]))
    assert sql == '"id" = ANY(:scope_0)'
    assert params == {"scope_0": ["a", "b"]}


def test_overlap_uses_array_operator():
    sql, _ = rule_to_sql(FilterRule(operator="overlap", field="dept_ids", value=["a"]))
    assert sql == '"dept_ids" && :scope_0'


def test_and_or_not_nest_with_parens():
    left = FilterRule(operator="eq", field="a", value=1)
    right = FilterRule(operator="eq", field="b", value=2)
    sql, params = rule_to_sql(FilterRule(operator="or", children=[left, right]))
    assert sql == '("a" = :scope_0 OR "b" = :scope_1)'
    assert params == {"scope_0": 1, "scope_1": 2}

    sql, _ = rule_to_sql(FilterRule(operator="not", children=[left]))
    assert sql == 'NOT ("a" = :scope_0)'


def test_bindings_override_physical_column():
    sql, _ = rule_to_sql(
        FilterRule(operator="eq", field="user_id", value="u1"),
        bindings={"user_id": "created_by"},
    )
    assert sql == '"created_by" = :scope_0'


def test_unbound_field_raises():
    with pytest.raises(ScopeCompileError, match="unbound"):
        rule_to_sql(FilterRule(operator="eq", field="user_id", value="u1"), bindings={})


@pytest.mark.parametrize("bad", ['a"; DROP TABLE x --', "a b", "1col", ""])
def test_illegal_identifier_rejected(bad):
    """注入用例：字段名不走值绑定，必须走白名单。"""
    with pytest.raises(ScopeCompileError, match="identifier"):
        rule_to_sql(FilterRule(operator="eq", field=bad, value=1))


def test_wire_roundtrip():
    rule = FilterRule(
        operator="or",
        children=[
            FilterRule(operator="eq", field="a", value=1),
            FilterRule(operator="allow_all"),
        ],
    )
    assert FilterRule.from_wire(rule.to_wire()) == rule


def test_none_allow_means_all_fields_none():
    r = FilterRule.from_wire({"operator": "none_allow"})
    assert r.operator == "none_allow" and r.field is None and r.children is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_scope_rule_to_sql.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.ontology.scope'`

- [ ] **Step 3: 实现**

> **⚠️ 下方代码块是初版，已作废。** 两阶段审查修正了 5 处，其中一处是**与网关判定相反的 fail-open**（空 `and`/`not` 曾编译成 `TRUE`，放行全域；网关对同一棵树判 deny）。
> **权威实现是文件本身**：`ontostudio/backend/app/ontology/scope.py`（33 条测试守着）。修正清单见本 Task 末尾的「审查裁定引入的偏离」表。
>
> **不要照抄下面的代码块。** 后续 Task 只依赖这三个**未变更**的接口：
> ```python
> class FilterRule:            # 字段：operator / field / value / children
>     def to_wire(self) -> dict: ...
>     @classmethod
>     def from_wire(cls, data: dict) -> "FilterRule": ...
> class ScopeCompileError(ValueError): ...
> def rule_to_sql(rule: FilterRule, bindings: dict[str, str] | None = None) -> tuple[str, dict]: ...
> ```
> **行为差异须知**：空 `and`/`not` 现在 **raise** 而非返回 `TRUE`；`in`/`not_in` 的裸字符串按单元素集合处理；畸形 wire 一律抛 `ScopeCompileError` 而非 `KeyError`/`TypeError`。

```python
# ontostudio/backend/app/ontology/scope.py
"""数据范围规则树：wire 编解码 + 编译为参数化 SQL WHERE。（初版，见上方警告）

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3。
FilterRule 的字段形态**对齐** gateway backend/app/extensions/auth/engine.py::FilterRule——
两侧各自持有数据类（OntoStudio 是独立服务，无法 import app.*），wire 用同名字段。
gateway 侧字段或算子变更时，此处必须同步。

安全：字段名不经值绑定，故走标识符白名单 + 加引号；任何值一律命名参数绑定。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# 叶子算子 → SQL 模板（{c}=列占位，{p}=参数占位）
_LEAF_SQL = {
    "eq": "{c} = {p}",
    "ne": "{c} <> {p}",
    "in": "{c} = ANY({p})",
    "not_in": "NOT ({c} = ANY({p}))",
    "overlap": "{c} && {p}",
}


class ScopeCompileError(ValueError):
    """规则树不合法（未知算子 / 未绑定字段 / 非法标识符）。"""


@dataclass
class FilterRule:
    operator: str = "none_allow"  # allow_all|none_allow|and|or|not|eq|ne|in|not_in|overlap
    field: str | None = None
    value: Any = None
    children: list["FilterRule"] | None = None

    def to_wire(self) -> dict[str, Any]:
        out: dict[str, Any] = {"operator": self.operator}
        if self.field is not None:
            out["field"] = self.field
        if self.value is not None:
            out["value"] = self.value
        if self.children is not None:
            out["children"] = [c.to_wire() for c in self.children]
        return out

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> "FilterRule":
        return cls(
            operator=data["operator"],
            field=data.get("field"),
            value=data.get("value"),
            children=[cls.from_wire(c) for c in data["children"]] if data.get("children") else None,
        )


def _quote(field_name: str, bindings: dict[str, str] | None) -> str:
    """把模板字段名解析为物理列名并加引号。

    ``bindings=None`` 表示不做映射（恒等：模板字段名即列名）；
    ``bindings={...}`` 表示显式映射表——此时**每个**字段都必须命中，未命中即报错。
    两者语义不同（None=恒等，{}=全未绑定），这是刻意的：显式映射下静默退回恒等会让
    registry 里漏配的 scope_bindings 变成"看起来能用"的越权读，故宁可直接失败。
    """
    if bindings is None:
        physical = field_name
    else:
        if field_name not in bindings:
            raise ScopeCompileError(f"unbound field in scope bindings: {field_name!r}")
        physical = bindings[field_name]
    if not _IDENT.match(physical):
        raise ScopeCompileError(f"illegal identifier for scope field {field_name!r}: {physical!r}")
    return f'"{physical}"'


def rule_to_sql(rule: FilterRule, bindings: dict[str, str] | None = None) -> tuple[str, dict[str, Any]]:
    """编译为 (WHERE 片段, 命名参数)。bindings=None 表示不做字段名映射（恒等）。"""
    params: dict[str, Any] = {}
    counter = [0]

    def walk(node: FilterRule) -> str:
        op = node.operator
        if op == "allow_all":
            return "TRUE"
        if op == "none_allow":
            return "FALSE"
        if op in ("and", "or"):
            kids = node.children or []
            if not kids:
                return "TRUE" if op == "and" else "FALSE"
            joiner = " AND " if op == "and" else " OR "
            return "(" + joiner.join(walk(k) for k in kids) + ")"
        if op == "not":
            kids = node.children or []
            if not kids:
                return "TRUE"
            return "NOT (" + walk(kids[0]) + ")"
        if op in _LEAF_SQL:
            if node.field is None:
                raise ScopeCompileError(f"operator {op!r} requires a field")
            key = f"scope_{counter[0]}"
            counter[0] += 1
            params[key] = node.value if op not in ("in", "not_in") else list(node.value or [])
            return _LEAF_SQL[op].format(c=_quote(node.field, bindings), p=f":{key}")
        raise ScopeCompileError(f"unknown operator: {op!r}")

    return walk(rule), params
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_scope_rule_to_sql.py -v`
Expected: PASS（13 项）

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/app/ontology/scope.py ontostudio/backend/tests/test_scope_rule_to_sql.py
git commit -m "feat(ontostudio): 数据范围规则树编译(FilterRule → 参数化 WHERE)"
```

### 审查裁定引入的偏离（2026-09-22，两阶段审查后）

本任务的字面代码块**已被审查裁定修改**，后续读者以实际代码为准：

| 处 | 计划字面 | 实际 | 裁定理由 |
|---|---|---|---|
| `_quote` 的 `bindings` 语义 | `(bindings or {}).get(f, f)` | `bindings is None` → 恒等；否则**未命中即报错** | 计划原文在 `bindings={}` 时静默退回恒等，**通不过计划自己的 `test_unbound_field_raises`**；且那是一个真实 fail-open（registry 漏配 `scope_bindings` → 静默越权读） |
| 空 `and` / 空 `not` | `TRUE`（放行全域） | **`raise ScopeCompileError`** | 网关参考实现 `engine.py:99-129` 对同一棵树判 **deny**——两侧相反且静默。`allow_all` 有独立算子，空复合式无合法含义，拒绝它不会让任何合法规则回归。空 `or` 保持 `FALSE`（本就同向） |
| `in` / `not_in` 的 value | `list(node.value or [])` | **仅当 `op in ("in","not_in")` 时**先特判 `str` → `[str]`，再 `list(...)`；标量算子完全不归一 | 裸字符串会被按字符拆（`"abc"`→`['a','b','c']`），`in` 方向是**放宽**。特判不是新增语义，是复刻 `engine.py:52` 的既有语义（非 list 视为单元素集合）。**注意：审查者给的初版修法是无条件特判 `str`，那会把 `eq` 的标量值也包成列表、打破规格原有的 `test_eq_binds_value_not_interpolates`——实现者收窄了范围，是对的。** |
| `from_wire` / `_quote` 的输入校验 | 直接索引与 `match` | 缺键/非 str/非 dict/`children` 非 list 一律归一为 `ScopeCompileError`；标识符用 `fullmatch` | 原实现下 `KeyError`/`TypeError`/`AttributeError` 会逃出模块声明的错误类型，Task 5 映射错误码时会变 500。`fullmatch` 顺带堵住 `$` 锚点容许尾部换行。`children` 类型校验属实现者自主延伸（同一漏检类，经复审确认不误伤 `children: null` 这一合法形态） |
| `not` 的多余子节点 | 静默取 `children[0]`，其余丢弃 | `raise`（`not expects exactly one child, got N`） | 安全过滤器上静默丢弃输入不可接受；与 `_quote`「宁可直接失败」的姿态一致 |
| `ne` / `not_in` 测试 | 无 | 各补 1 条 | 安全相关算子零覆盖，手工探针不是回归护栏 |

**未采纳**：`not_in` 空集守卫（修复位置定在 gateway 解析层，见 spec §9 风险表）；`counter=[0]` 改 `nonlocal`（风格偏好）。

**本模块的安全属性已被审查者独立实测确认**（非"规格如此"）：SQL 文本中不存在任何调用方值的拼接路径；标识符白名单作用在**映射后的物理列名**上，不是只校验模板字段名。

---

## Task 2: registry 支持 `actions:` 段

**Files:**
- Modify: `ontostudio/backend/app/ontology/schemas.py`
- Modify: `ontostudio/backend/app/ontology/registry.py`
- Test: `ontostudio/backend/tests/test_actions_schema.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_actions_schema.py
"""动作声明 schema + registry 加载路径。

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §1.1。
"""
from __future__ import annotations

import yaml
import pytest
from pydantic import ValidationError

from app.ontology.schemas import ActionSpec, DomainFile, StateChange


def _ot(api_name="graph_entity", domain="doc_graph"):
    return {
        "api_name": api_name, "display_name": "实体", "description": "d", "domain": domain,
        "access": {"path": "postgres_ext", "table": "dg_entities"},
        "pk": {"column": "id", "api_name": "id", "type": "uuid"},
        "properties": [
            {"name": "id", "api_name": "id", "type": "uuid", "description": "pk"},
            {"name": "status", "api_name": "status", "type": "string", "description": "s"},
        ],
    }


def _action(**over):
    base = {
        "id": "review_entity.confirm", "display_name": "确认实体", "description": "d",
        "domain": "doc_graph", "target": "graph_entity",
        "required_permissions": ["ontology:action:review"],
        "preconditions": [{"field": "status", "op": "eq", "value": "pending_review"}],
        "postconditions": [{"field": "status", "set": "active"}],
    }
    base.update(over)
    return base


def test_valid_domain_parses_with_actions():
    d = DomainFile.model_validate({"object_types": [_ot()], "actions": [_action()]})
    assert d.actions[0].id == "review_entity.confirm"
    assert d.actions[0].behavior_type == "COMMAND"


def test_unknown_target_rejected():
    d = DomainFile.model_validate({"object_types": [_ot()], "actions": [_action(target="nope")]})
    with pytest.raises(ValueError, match="unknown action target"):
        d.validate_action_refs()


def test_unknown_field_rejected():
    d = DomainFile.model_validate({
        "object_types": [_ot()],
        "actions": [_action(postconditions=[{"field": "nosuch", "set": 1}])],
    })
    with pytest.raises(ValueError, match="unknown action field"):
        d.validate_action_refs()


def test_empty_postconditions_rejected():
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(postconditions=[]))


def test_illegal_op_rejected():
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(preconditions=[{"field": "status", "op": "drop", "value": 1}]))


def test_set_and_now_mutually_exclusive():
    with pytest.raises(ValidationError, match="set 与 now"):
        ActionSpec.model_validate(_action(postconditions=[{"field": "status", "set": "x", "now": True}]))


def test_required_permissions_must_not_be_empty():
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(_action(required_permissions=[]))


def test_duplicate_action_id_rejected():
    d = DomainFile.model_validate({"object_types": [_ot()], "actions": [_action(), _action()]})
    with pytest.raises(ValueError, match="duplicate action id"):
        d.validate_action_refs()


def test_neither_set_nor_now_rejected():
    """互斥是「二选一」而非「至多一个」：两者同时缺省同样拒绝。

    （计划初稿只测了「同时给出」这一半；`self.now == (self.set is not None)`
    在两者皆缺省时同样为 True，是真分支，必须钉住另一半。）
    """
    with pytest.raises(ValidationError, match="set 与 now"):
        StateChange.model_validate({"field": "status"})


def test_scope_bindings_must_reference_declared_property():
    ot = _ot()
    ot["scope_resource"] = "ontology"
    ot["scope_bindings"] = {"user_id": "nosuch_column"}
    d = DomainFile.model_validate({"object_types": [ot], "actions": []})
    with pytest.raises(ValueError, match="unknown scope binding"):
        d.validate_action_refs()


# ── Registry 加载路径 ────────────────────────────────────────────────────────
# 为什么需要这一组：真实 registry 的 YAML 到 Task 3 才会有 actions: 段，所以
# 全量测试里 RegistryStore 的 `for a in domain.actions:` 循环体一次都不执行——
# 即本任务声称的「核心」（按 id 索引的动作字典 + 跨文件重复守卫）在提交的测试里
# 零覆盖。用临时 registry 目录把它钉住，而不是靠一次性脚本。

def _write_registry(tmp_path, files: dict[str, str]):
    """最小 registry 目录：manifest + 各域文件。"""
    (tmp_path / "_manifest.yaml").write_text(
        "schema_version: 2\nhot_reload: true\nfiles:\n" + "".join(f"  - file: {n}\n" for n in files),
        encoding="utf-8",
    )
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_registry_exposes_actions_by_id(tmp_path):
    d = _write_registry(tmp_path, {
        "a.yaml": yaml.safe_dump({"object_types": [_ot()], "actions": [_action()]}, allow_unicode=True),
    })
    from app.ontology.registry import RegistryStore

    reg = RegistryStore(registry_dir=d).get()
    assert reg.get_action("review_entity.confirm").target == "graph_entity"
    assert reg.get_action("nope.nope") is None


def test_cross_file_duplicate_action_id_rejected(tmp_path):
    """跨文件重复由 RegistryStore 的合并循环兜住（文件内的由 validate_action_refs 兜）。

    两个域各自声明**不同**对象类型（否则会先在对象类型重复注册处报错），
    但动作 id 相同——必须报「动作 id 跨域重复」。
    """
    d = _write_registry(tmp_path, {
        "a.yaml": yaml.safe_dump({
            "object_types": [_ot(api_name="graph_entity")],
            "actions": [_action(id="dup.check", target="graph_entity")],
        }, allow_unicode=True),
        "b.yaml": yaml.safe_dump({
            "object_types": [_ot(api_name="graph_entity2")],
            "actions": [_action(id="dup.check", target="graph_entity2")],
        }, allow_unicode=True),
    })
    from app.ontology.registry import RegistryError, RegistryStore

    with pytest.raises(RegistryError, match="动作 id 跨域重复"):
        RegistryStore(registry_dir=d).get()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_schema.py -v`
Expected: FAIL —— `ImportError: cannot import name 'ActionSpec'`

- [ ] **Step 3: 实现 —— `schemas.py` 追加**

在 `ontostudio/backend/app/ontology/schemas.py` 末尾（`DomainFile` 之前）插入：

```python
class Precondition(BaseModel):
    """动作前置条件：只允许「列 op 字面量」——不做表达式求值。

    EAI-CUSTOM: 设计 §1.1。对标 M2 行为模型的谓词语法，收窄到可静态校验的子集。
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    op: Literal["eq", "ne", "in", "not_in", "is_null", "not_null"]
    value: Any | None = None


class StateChange(BaseModel):
    """动作后置：受影响列的新值。set 与 now 互斥。"""

    model_config = ConfigDict(extra="forbid")

    field: str
    set: Any | None = None
    now: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> StateChange:  # 不加引号：本文件已有 from __future__ import annotations，引号会触发 ruff UP037
        if self.now == (self.set is not None):
            raise ValueError(f"{self.field}: set 与 now 必须二选一（不可同时给出或同时缺省）")
        return self


class ActionSpec(BaseModel):
    """注册表动作声明（设计 §1.1）。本期只支持 COMMAND。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    display_name: str
    description: str
    domain: str
    target: str  # ObjectType.api_name
    behavior_type: Literal["COMMAND"] = "COMMAND"
    required_permissions: list[str] = Field(min_length=1)
    preconditions: list[Precondition] = Field(default_factory=list)
    postconditions: list[StateChange] = Field(min_length=1)
    version: int = 1
```

把 `from pydantic import BaseModel, ConfigDict, Field` 改为
`from pydantic import BaseModel, ConfigDict, Field, model_validator`。

`ObjectType` 追加两个字段（放在 `etype_classes` 之后）：

```python
    # EAI-CUSTOM (动作层, 设计 §3): 数据范围归属——值取 permissions.yaml 的**模块 key**
    # （ontology / contract_price / spare_parts / bid_quote…），不是 scope id。
    scope_resource: str | None = None
    # 模板字段名 ≠ 本表列名时的覆盖；缺省恒等映射。
    scope_bindings: dict[str, str] | None = None
```

`DomainFile` 追加 `actions` 字段与校验方法：

```python
    actions: list[ActionSpec] = []

    @model_validator(mode="after")
    def _check_refs(self) -> DomainFile:
        """交叉引用校验。fail-closed：任一不满足即拒绝加载。

        分工边界（Task 2 质量审查 M-1）：**列引用**在本校验器；**`scope_resource` 的
        值域**（是否为已知权限模块 key）在 `scripts/ontology_lint.py`（Task 9）——
        别在这里以为漏了。

        不对称说明（M-4）：`actions.target` 只允许**同文件**解析，而 `link_types` 的
        source/target 允许跨文件前向引用（见 registry.py 的 pending 集）。这是有意的：
        动作要落到具体物理表，跨文件引用会让"哪个域拥有这条写路径"变得含糊。
        """
        by_api_name = {ot.api_name: ot for ot in self.object_types}
        props = {name: {p.name for p in ot.properties} for name, ot in by_api_name.items()}

        seen: set[str] = set()
        for a in self.actions:
            if a.id in seen:
                raise ValueError(f"duplicate action id: {a.id}")
            seen.add(a.id)
            if a.target not in by_api_name:
                raise ValueError(f"unknown action target: {a.target!r} (action {a.id})")
            # 域一致性（Task 2 质量审查 M-2，**超出设计 §1.1 三类校验的范围外补强**）：
            # action.domain 会被写进 dg_action_audit.domain，而同行表名来自 target 对象。
            # 两者不一致会产出"domain 与表对不上"的审计行，而审计是这条链路唯一的追溯凭据。
            target_domain = by_api_name[a.target].domain
            if a.domain != target_domain:
                raise ValueError(f"action {a.id}: domain {a.domain!r} 与 target 所属域 {target_domain!r} 不一致")
            declared = props[a.target]
            for cond in list(a.preconditions) + list(a.postconditions):
                if cond.field not in declared:
                    raise ValueError(f"unknown action field: {cond.field!r} on {a.target} (action {a.id})")

        for ot in self.object_types:
            declared = props[ot.api_name]
            for template_field, physical in (ot.scope_bindings or {}).items():
                if physical not in declared:
                    raise ValueError(f"unknown scope binding: {template_field}->{physical} on {ot.api_name}")
```

- [ ] **Step 4: 在 registry.py 加载后调用校验**

把 `ontostudio/backend/app/ontology/registry.py:69-74` 的 `_validate_domain_file` 整体改为：

```python
def _validate_domain_file(path: Path, data: dict) -> DomainFile:
    try:
        return DomainFile.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0] if e.errors() else {}
        loc = ".".join(str(x) for x in err.get("loc", ()))
        raise RegistryError(f"schema 校验失败: {path.name}: {f'{loc}: ' if loc else ''}{err.get('msg', e)}") from e
```

（**原版是两个 try**——第二个专门包 `validate_action_refs` 抛的 `ValueError`。经 Task 2 质量审查裁定改为 `model_validator(mode="after")` 后，该校验并入 `model_validate` 的 `ValidationError`，第二个 try 整块删除。那个被删掉的包装本身**零测试保护**：审查者实测把它整块删掉，264 条测试照样全绿。）

注意三点：

1. **`f'{loc}: ' if loc else ''` 是必需的，不是美化**：pydantic 根级 after-validator 的 `e.errors()[0]["loc"]` 是**空 tuple**，照原样拼会渲染出 `a.yaml: : Value error, ...`（两个冒号）。审查者实测确认。
2. (c) 的跨文件守卫与模型内的文件内查重是**两件事**，别只做一半：文件内重复由 `_check_refs`（模型校验器）挡，跨文件重复由 `RegistryStore` 的合并循环挡。两者各有测试（`test_duplicate_action_id_rejected` 与 `test_cross_file_duplicate_action_id_rejected`）。**跨文件重复的报错不受模型校验器改动影响**——它从不在模型里。
3. **不要再引入"须显式调用的公开校验方法"**。本仓既有模式是 `model_validator(mode="after")`（对照 `app/doc_graph/schemas.py:154` 的 `ExtractionPayload._check_domain_and_refs`，其测试在 `model_validate` 处断言 `ValidationError`）。计划初稿的 `validate_action_refs()` 公开方法**在本仓没有先例**，且它立的"只允许经 `_validate_domain_file` 解析"约定会被本计划后面自己的 Task 9/10 代码绕过（那两处的 `DomainFile.model_validate(...)` 是直接调用）。

**同一文件还需让 `Registry` 承载动作**——`Registry` 是合并快照，**不保存 per-domain 的 `DomainFile`**（`__init__` 只有 `object_types` / `link_types` 两个合并字典），所以不能遍历 domain 找动作。照 `object_types` 的样子加一个合并字典：

(a) `Registry.__init__`（L31-48）追加参数与属性（放在 `formal_by_domain` 之后，保持既有参数顺序不动）：

```python
        actions: dict[str, ActionSpec] | None = None,
```
```python
        self.actions = actions or {}
```

同文件顶部 import 改为 `from app.ontology.schemas import ActionSpec, DomainFile, FormalSection, LinkType, Manifest, ObjectType`。

(b) 追加访问器（放 `Registry.__init__` 之后。**注意：`get()` 在 `RegistryStore` 上，不在 `Registry` 上**——计划初稿说"与 `get()` 同层"措辞不准，实质指令以本行为准）：

```python
    def get_action(self, action_id: str) -> ActionSpec | None:
        return self.actions.get(action_id)
```

(c) 在 `RegistryStore` 的加载函数里汇总动作。**不要新起一遍遍历**——`registry.py:129` 已有第二遍循环 `for name, domain in parsed:`（`parsed: list[tuple[str, DomainFile]]` 在 L119，用 `_validate_domain_file` 产出），把动作合并**并进这个循环**：

```python
    objects: dict[str, ObjectType] = {}
    links: dict[str, LinkType] = {}
    # ...（既有局部变量不动）
    actions: dict[str, ActionSpec] = {}          # ← 新增

    for name, domain in parsed:
        # ...（既有 object_types / link_types 处理不动）
        for a in domain.actions:                  # ← 新增块，放在 link_types 循环之后
            if a.id in actions:
                raise RegistryError(f"{name}: 动作 id 跨域重复: {a.id}")
            actions[a.id] = a
        fingerprints[name] = _read_fingerprint(registry_dir / name)
        _check_cross_refs(registry_dir / name, objects, links, pending - set(objects))
```

**注意**：`validate_action_refs()` 已在 `_validate_domain_file` 内跑过（见上一步），它只挡**文件内**重复；**跨文件**重复由上面这个 `actions` 字典兜住。

(d) 把 L152-160 的 `Registry(...)` 调用补一个关键字参数（其余参数一个字不动）：

```python
    return Registry(
        manifest,
        objects,
        links,
        fingerprints,
        registry_version=manifest.registry_version,
        namespaces_by_domain=namespaces_by_domain,
        formal_by_domain=formal_by_domain,
        actions=actions,
    )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_schema.py -v`
Expected: PASS（**12 项**——计划初稿写 9 项，后补 `test_neither_set_nor_now_rejected` 与两条 Registry 加载路径测试，见 Step 1 末尾）

- [ ] **Step 6: 回归既有 registry 测试（确认没打坏加载）**

Run: `PYTHONPATH=. uv run pytest tests/ -k registry -v`
Expected: 全 PASS。若 `eia.yaml` 因 `validate_action_refs` 报错，说明旧文件里有非法绑定——按提示修 YAML，不要放宽校验。

- [ ] **Step 7: 提交**

```bash
git add ontostudio/backend/app/ontology/schemas.py ontostudio/backend/app/ontology/registry.py ontostudio/backend/tests/test_actions_schema.py
git commit -m "feat(ontostudio): registry 支持 actions 段 + 交叉引用校验"
```

### 审查裁定引入的偏离（2026-09-22，两阶段审查后）

本任务的字面代码块**已被审查裁定修改**，后续读者以实际代码为准：

| 处 | 计划字面 | 实际 | 裁定理由 |
|---|---|---|---|
| 校验的挂载方式 | 公开方法 `validate_action_refs()`，须显式调用 | **`@model_validator(mode="after") _check_refs()`** | 本仓既有模式就是后者（`app/doc_graph/schemas.py:154`），"公开方法须显式调用"**无先例**；且计划自立的"只允许经 `_validate_domain_file` 解析"约定会被本计划 Task 9/10 的代码立刻绕过。改完还闭合一个盲区：原 `registry.py` 里为 `ValueError→RegistryError` 写的包装**整块删掉 264 条测试全绿**（零保护），改后该包装消失、错误落回已被 `test_ontology_registry.py:65-77` 覆盖的分支 |
| 空 loc 的渲染 | `f"{loc0}: {msg}"` | `f"{loc}: " if loc else ""` 前缀条件化 | pydantic 根级 after-validator 的 `loc` 是空 tuple，照原样拼出 `a.yaml: : Value error`（双冒号）。审查者实测 |
| `action.domain` 一致性 | 不校验 | **加校验**（须与 target 所属域一致） | **范围外补强**，审查者 M-2：`domain` 会进审计行而表名来自 target，不一致会产出对不上的审计行，审计是唯一追溯凭据 |
| `-> "StateChange"` 的引号 | 带引号 | 去引号 | 文件已有 `from __future__ import annotations`，引号触发 ruff **UP037** |
| 测试 import 顺序 | `yaml` 在 `pytest` 前 | `pytest` 在前 | 触发 ruff **I001** |
| 测试文件头 | 无 docstring / 无 future import | 补齐 | 仓内测试文件惯例 |
| 测试数 | 9 项 | **12 项**（+`test_neither_set_nor_now_rejected`、+两条 Registry 加载路径、+若干变异补测） | 原 9 项漏了互斥校验"同时缺省"那一半；且 `Registry.actions`/`get_action`/跨文件守卫在初始测试里**零覆盖**（真实 YAML 到 Task 3 才有 `actions:` 段，合并循环一次都不执行） |

**未采纳**：`scope_bindings` 有而 `scope_resource` 缺省时的拒绝（M-3，兜底方向 fail-closed，非越权，记为后续项）；跨文件重复 id 的报错带上首次出现的文件名（M-5，需把 `actions` 换成 `dict[str, tuple[str, ActionSpec]]`，波及 `get_action`，不值当）；`actions` 改私有（M-6，与既有 `object_types`/`link_types` 同模式，不新增风险）。

**变异检验的结论请记住**：审查者用"删掉/放宽某段代码看测试是否变红"的方法，在初始 12 条测试里找到 **3 个盲区**——`id` 正则、`preconditions` 那一半校验、以及那个 fail-closed 包装。**这三条都已补测**。后续 Task 的审查者应沿用同一手法。

---

## Task 3: `dg_action_audit` 表 + `status` 加 `rejected`

**Files:**
- Modify: `ontostudio/backend/app/doc_graph/tables.py`
- Modify: `ontostudio/backend/app/ontology/kernel/validate.py:58,61`
- Modify: `ontostudio/backend/app/ontology/registry/doc_graph.yaml`
- Test: `ontostudio/backend/tests/test_action_audit_table.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_action_audit_table.py
"""审计表随 Base.metadata 注册 + status 枚举含 rejected。"""
from app.db import Base
from app.doc_graph.tables import DgActionAudit


def test_audit_table_registered_in_metadata():
    assert "dg_action_audit" in Base.metadata.tables


def test_audit_columns():
    cols = set(DgActionAudit.__table__.columns.keys())
    assert {
        "id", "action_id", "domain", "target_table", "target_pk",
        "actor_id", "actor_role", "params", "before", "after", "source", "created_at",
    } <= cols


def test_status_enum_includes_rejected():
    from pathlib import Path
    src = Path("app/ontology/kernel/validate.py").read_text(encoding="utf-8")
    assert '"rejected"' in src, "status 枚举未加 rejected——SHACL 会判拒绝后实体违规"


def test_registry_doc_graph_status_enum_includes_rejected():
    from pathlib import Path
    yaml_src = Path("app/ontology/registry/doc_graph.yaml").read_text(encoding="utf-8")
    assert "rejected" in yaml_src
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_action_audit_table.py -v`
Expected: FAIL —— `ImportError: cannot import name 'DgActionAudit'`

- [ ] **Step 3: 加表（`tables.py` 末尾追加）**

```python
class DgActionAudit(Base):
    """动作审计（设计 §1.2）。业务状态与审计行同事务落库；图上的 MergeAudit 节点
    降级为本表的投影（属折叠步范围，本表先建）。

    EAI-CUSTOM: 建表沿用既有机制——本模块随 app/ontology/__init__.py 导入注册进
    Base.metadata，由 gateway 启动时的 create_all 建表。无需迁移脚本。
    """

    __tablename__ = "dg_action_audit"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    action_id: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(60), nullable=False)
    target_table: Mapped[str] = mapped_column(String(120), nullable=False)
    target_pk: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_role: Mapped[str | None] = mapped_column(String(120))
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'api'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_dg_action_audit_target_created", "target_pk", "created_at"),
        Index("ix_dg_action_audit_actor_created", "actor_id", "created_at"),
    )
```

（若 `tables.py` 顶部未导入 `Index`，在同行的 sqlalchemy import 中补上。）

- [ ] **Step 4: 加 `rejected` 到 SHACL 枚举**

`ontostudio/backend/app/ontology/kernel/validate.py:58` 改为：

```python
    Collection(g, head, [Literal(v) for v in ("active", "pending_review", "merged", "rejected")])
```

`:61` 的提示改为：

```python
    _severity(g, ps, "status 必须是 active/pending_review/merged/rejected 之一")
```

`ontostudio/backend/app/ontology/registry/doc_graph.yaml` 中 `graph_entity` 的 `status` 属性 `enum` 追加 `rejected`；同一对象的 `etype_classes` 块**之后**加一行：

```yaml
    scope_resource: ontology
```

- [ ] **Step 5: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_action_audit_table.py tests/test_kernel_p4.py -v`
Expected: 全 PASS（P4 是 SHACL 金测试，确认改枚举没打坏既有形状）

- [ ] **Step 6: 提交**

```bash
git add ontostudio/backend/app/doc_graph/tables.py ontostudio/backend/app/ontology/kernel/validate.py ontostudio/backend/app/ontology/registry/doc_graph.yaml ontostudio/backend/tests/test_action_audit_table.py
git commit -m "feat(ontostudio): dg_action_audit 表 + status 枚举加 rejected"
```

---

## Task 4: `sql_write.py` —— 写守卫

**Files:**
- Create: `ontostudio/backend/app/ontology/actions/__init__.py`
- Create: `ontostudio/backend/app/ontology/actions/sql_write.py`
- Test: `ontostudio/backend/tests/test_actions_sql_write.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_actions_sql_write.py
import pytest

from app.ontology.actions.sql_write import (
    WriteGuardError, build_precondition_where, build_update_set, quote_ident,
)
from app.ontology.schemas import Precondition, StateChange


def test_quote_ident_ok():
    assert quote_ident("status") == '"status"'


@pytest.mark.parametrize("bad", ['a"; DROP TABLE t --', "a b", "1a", ""])
def test_quote_ident_rejects(bad):
    with pytest.raises(WriteGuardError, match="identifier"):
        quote_ident(bad)


def test_precondition_eq():
    sql, params = build_precondition_where([Precondition(field="status", op="eq", value="pending_review")])
    assert sql == '"status" = :pre_0'
    assert params == {"pre_0": "pending_review"}


def test_precondition_is_null():
    sql, params = build_precondition_where([Precondition(field="valid_to", op="is_null")])
    assert sql == '"valid_to" IS NULL'
    assert params == {}


def test_precondition_in():
    sql, params = build_precondition_where([Precondition(field="status", op="in", value=["a", "b"])])
    assert sql == '"status" = ANY(:pre_0)'
    assert params == {"pre_0": ["a", "b"]}


def test_empty_preconditions_is_true():
    assert build_precondition_where([]) == ("TRUE", {})


def test_update_set_literal_and_now():
    sql, params = build_update_set(
        [StateChange(field="status", set="active"), StateChange(field="updated_at", now=True)]
    )
    assert sql == '"status" = :set_0, "updated_at" = NOW()'
    assert params == {"set_0": "active"}


def test_update_set_requires_at_least_one():
    with pytest.raises(WriteGuardError, match="no state change"):
        build_update_set([])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_sql_write.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.ontology.actions'`

- [ ] **Step 3: 实现**

```bash
# 空包标记
printf '"""OntoStudio 动作层（设计 §2）。EAI-CUSTOM。"""\n' > ontostudio/backend/app/ontology/actions/__init__.py
```

```python
# ontostudio/backend/app/ontology/actions/sql_write.py
"""动作写路径的 SQL 构造与守卫——**本模块是全库唯一拼写语句的地方**。

EAI-CUSTOM: 设计 §2。安全约定：
- 表名与列名只来自解析后的 ActionSpec（registry 声明），**绝不来自调用方 params**；
- 列名一律过标识符白名单并加引号；
- 值一律命名参数绑定。
读路径的 sqlguard.assert_readonly_select 只放 SELECT，不能复用，故单独成模块。
"""

from __future__ import annotations

import re
from typing import Any

from app.ontology.schemas import Precondition, StateChange

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_PRE_SQL = {
    "eq": "{c} = {p}",
    "ne": "{c} <> {p}",
    "in": "{c} = ANY({p})",
    "not_in": "NOT ({c} = ANY({p}))",
    "is_null": "{c} IS NULL",
    "not_null": "{c} IS NOT NULL",
}


class WriteGuardError(ValueError):
    """动作声明不合法或试图构造越界语句。"""


def quote_ident(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise WriteGuardError(f"identifier rejected: {name!r}")
    return f'"{name}"'


def build_precondition_where(preconditions: list[Precondition]) -> tuple[str, dict[str, Any]]:
    """前置条件合取（AND）。空列表 → TRUE。"""
    if not preconditions:
        return "TRUE", {}
    parts: list[str] = []
    params: dict[str, Any] = {}
    for i, cond in enumerate(preconditions):
        tmpl = _PRE_SQL.get(cond.op)
        if tmpl is None:
            raise WriteGuardError(f"unknown precondition op: {cond.op!r}")
        col = quote_ident(cond.field)
        if cond.op in ("is_null", "not_null"):
            parts.append(tmpl.format(c=col, p=""))
            continue
        key = f"pre_{i}"
        params[key] = list(cond.value or []) if cond.op in ("in", "not_in") else cond.value
        parts.append(tmpl.format(c=col, p=f":{key}"))
    return " AND ".join(parts), params


def build_update_set(changes: list[StateChange]) -> tuple[str, dict[str, Any]]:
    """SET 子句。至少一条，否则拒绝（避免生成空 UPDATE）。"""
    if not changes:
        raise WriteGuardError("no state change declared")
    parts: list[str] = []
    params: dict[str, Any] = {}
    for i, ch in enumerate(changes):
        col = quote_ident(ch.field)
        if ch.now:
            parts.append(f"{col} = NOW()")
            continue
        key = f"set_{i}"
        params[key] = ch.set
        parts.append(f"{col} = :{key}")
    return ", ".join(parts), params
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_sql_write.py -v`
Expected: PASS（11 项）

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/app/ontology/actions/ ontostudio/backend/tests/test_actions_sql_write.py
git commit -m "feat(ontostudio): 动作写守卫(sql_write)——标识符白名单 + 参数化构造"
```

---

## Task 5: `executor.py` —— 执行管线

**Files:**
- Create: `ontostudio/backend/app/ontology/actions/executor.py`
- Test: `ontostudio/backend/tests/test_actions_executor.py`

- [ ] **Step 1: 写失败测试**

测试用 mock 的对象类型 + 假 action，直接调 `invoke_action_core(...)`（把鉴权与取范围规则作为**已解析参数**传入，使本 Task 不依赖 gateway）。真实 DB 走 `_ext_url()`，与 `test_doc_graph_*` 同一套环境。

```python
# ontostudio/backend/tests/test_actions_executor.py
"""执行管线：解析→范围→锁定→前置→UPDATE→审计→重投影。

本文件把「权限判定的结果」与「数据范围规则」作为入参喂给核心函数，
从而与 gateway 解耦（gateway 侧单测在 backend/tests/test_permissions_scope_endpoint.py）。
"""
import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.actions.executor import ActionError, ScopeDenied, invoke_action_core
from app.ontology.connectors import _ext_url
from app.ontology.scope import FilterRule

pytestmark = pytest.mark.integration


async def _seed_entity(status: str = "pending_review") -> uuid.UUID:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    """INSERT INTO dg_entities (domain, etype, canonical_name, norm_name, attrs, confidence, status)
                       VALUES ('doc_graph','mine','测试实体', :norm, '{}'::jsonb, 0.9, :status) RETURNING id"""
                ),
                {"norm": f"测试实体-{uuid.uuid4().hex[:8]}", "status": status},
            )
            return row.scalar_one()
    finally:
        await engine.dispose()


async def _get_status(pk: uuid.UUID) -> str:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(text("SELECT status FROM dg_entities WHERE id = :id"), {"id": pk})
            return row.scalar_one()
    finally:
        await engine.dispose()


async def _audit_rows(pk: uuid.UUID) -> list[dict]:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            rows = await conn.execute(
                text("SELECT action_id, before, after, source FROM dg_action_audit WHERE target_pk = :id"),
                {"id": pk},
            )
            return [dict(r._mapping) for r in rows]
    finally:
        await engine.dispose()


async def test_happy_path_writes_status_and_audit():
    pk = await _seed_entity()
    result = await invoke_action_core(
        "review_entity.confirm", {}, target_pk=pk,
        actor_id=uuid.uuid4(), actor_role="admin", source="mcp",
        scope_rule=FilterRule(operator="allow_all"), project=lambda *a, **k: True,
    )
    assert result["after"] == {"status": "active"}
    assert await _get_status(pk) == "active"
    audit = await _audit_rows(pk)
    assert len(audit) == 1
    assert audit[0]["before"] == {"status": "pending_review"}
    assert audit[0]["source"] == "mcp"


async def test_precondition_violation_returns_409():
    pk = await _seed_entity(status="active")
    with pytest.raises(ActionError) as e:
        await invoke_action_core(
            "review_entity.confirm", {}, target_pk=pk,
            actor_id=uuid.uuid4(), actor_role="admin", source="api",
            scope_rule=FilterRule(operator="allow_all"), project=lambda *a, **k: True,
        )
    assert e.value.status_code == 409
    assert "pending_review" in e.value.detail


async def test_out_of_scope_returns_404():
    pk = await _seed_entity()
    with pytest.raises(ScopeDenied) as e:
        await invoke_action_core(
            "review_entity.confirm", {}, target_pk=pk,
            actor_id=uuid.uuid4(), actor_role="user", source="api",
            scope_rule=FilterRule(operator="none_allow"), project=lambda *a, **k: True,
        )
    assert e.value.status_code == 404


async def test_unknown_action_rejected():
    with pytest.raises(ActionError, match="unknown action"):
        await invoke_action_core(
            "nope.nope", {}, target_pk=uuid.uuid4(),
            actor_id=uuid.uuid4(), actor_role="admin", source="api",
            scope_rule=FilterRule(operator="allow_all"), project=lambda *a, **k: True,
        )


async def test_scope_sql_is_executable_with_list_params():
    """M-8（Task 1 审查遗留）：`= ANY(:p)` 传 Python list 给 asyncpg 的类型推断
    从未被任何测试证明过（`col = ANY($1)` 依赖列类型推出 uuid[]）。
    Task 1 的绿只证明 SQL 文本形态正确，不证明这条通道能跑——故在此显式钉住。

    **只覆盖 `in`。`overlap`（`col && $1`）是另一条绑定路径，本测试证不了它**——
    `&&` 要求操作数是 array 列，而本体面对的表（cpa_*/csp_*/dg_*）无 array 列，
    构造不出用例。**这不是死代码**：`config/permissions.yaml:99` 有真实模板
    `allowed_depts OVERLAP: $identity.dept_ids` 在用。**触发条件**：一旦某对象类型的
    `scope_bindings` 指向 array 列，必须先补一条 overlap 的集成测试再上线。
    """
    pk = await _seed_entity()
    rule = FilterRule(operator="in", field="id", value=[str(pk)])
    result = await invoke_action_core(
        "review_entity.confirm", {}, target_pk=pk,
        actor_id=uuid.uuid4(), actor_role="admin", source="api",
        scope_rule=rule, project=lambda *a, **k: True,
    )
    assert result["after"] == {"status": "active"}


async def test_projection_failure_does_not_rollback():
    """投影失败不回滚业务状态：审计与 UPDATE 已提交，errors 里留痕。"""
    pk = await _seed_entity()
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("projection boom")

    result = await invoke_action_core(
        "review_entity.confirm", {}, target_pk=pk,
        actor_id=uuid.uuid4(), actor_role="admin", source="api",
        scope_rule=FilterRule(operator="allow_all"), project=boom,
    )
    assert result["projected"] is False
    assert result["errors"] and "projection boom" in result["errors"][0]
    assert await _get_status(pk) == "active"
    assert len(await _audit_rows(pk)) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_executor.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.ontology.actions.executor'`

- [ ] **Step 3: 实现**

```python
# ontostudio/backend/app/ontology/actions/executor.py
"""动作执行管线（设计 §2）。

Postgres dg_* 是唯一真相源；提交后的增量重投影失败**不回滚**业务状态，
只记入 errors 并可重放——与 kernel/infer.py 的失败降级取向一致。
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.actions.sql_write import build_precondition_where, build_update_set, quote_ident
from app.ontology.connectors import _ext_url
from app.ontology.registry import get_registry
from app.ontology.scope import FilterRule, rule_to_sql


class ActionError(Exception):
    """动作执行失败。status_code/detail 直接映射到 HTTP 与 MCP 错误体。"""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class ScopeDenied(ActionError):
    """目标行不在调用者的数据范围内。用 404 而非 403——不泄漏行是否存在。"""

    def __init__(self, detail: str = "目标不存在或不在可见范围内") -> None:
        super().__init__(detail, status_code=404)


def _resolve(action_id: str):
    """解析动作声明与其目标对象类型。未知即拒（fail-closed）。

    Registry 是合并快照（actions / object_types 两张扁平字典），不保存 per-domain
    DomainFile——所以这里按 id 直查，不遍历域。
    """
    registry = get_registry()
    action = registry.get_action(action_id)
    if action is None:
        raise ActionError(f"unknown action: {action_id}", 404)
    obj = registry.object_types.get(action.target)
    if obj is None:  # registry 加载时已校验，此处是纵深防御
        raise ActionError(f"action {action_id} target unresolved: {action.target}", 500)
    return action, obj


async def invoke_action_core(
    action_id: str,
    params: dict[str, Any],
    *,
    target_pk: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str | None,
    source: str,
    scope_rule: FilterRule,
    project: Callable[[str, uuid.UUID], None],
) -> dict[str, Any]:
    """管线主体。鉴权与取范围规则由调用方（REST/MCP）完成后传入。

    project(action_id, pk) 在**提交后**调用，用于增量重投影；抛异常不回滚。
    """
    action, obj = _resolve(action_id)
    table = obj.access.table
    if not table:
        raise ActionError(f"action {action_id} target has no physical table", 500)

    bindings = obj.scope_bindings or None
    scope_sql, scope_params = rule_to_sql(scope_rule, bindings)
    pre_sql, pre_params = build_precondition_where(action.preconditions)
    set_sql, set_params = build_update_set(action.postconditions)

    pk_col = quote_ident(obj.pk.column)
    table_q = quote_ident(table)
    where = f"{pk_col} = :pk AND ({scope_sql})"
    params_all = {"pk": target_pk, **scope_params, **pre_params, **set_params}

    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    errors: list[str] = []
    try:
        async with engine.begin() as conn:
            locked = await conn.execute(
                text(f"SELECT * FROM {table_q} WHERE {where} FOR UPDATE"), params_all
            )
            row = locked.mappings().first()
            if row is None:
                raise ScopeDenied()

            ok = await conn.execute(text(f"SELECT ({pre_sql}) AS ok FROM {table_q} WHERE {pk_col} = :pk"), params_all)
            if not ok.scalar_one():
                expected = ", ".join(f"{c.field} {c.op} {c.value!r}" for c in action.preconditions)
                raise ActionError(f"前置条件不满足：需要 {expected}", status_code=409)

            before = {c.field: row.get(c.field) for c in action.postconditions}
            after = {c.field: (None if c.now else c.set) for c in action.postconditions}

            await conn.execute(
                text(f"UPDATE {table_q} SET {set_sql} WHERE {pk_col} = :pk"), params_all
            )
            await conn.execute(
                text(
                    """INSERT INTO dg_action_audit
                       (action_id, domain, target_table, target_pk, actor_id, actor_role, params, before, after, source)
                       VALUES (:action_id, :domain, :tbl, :pk, :actor, :role,
                               CAST(:params AS jsonb), CAST(:before AS jsonb), CAST(:after AS jsonb), :source)"""
                ),
                {
                    "action_id": action.id, "domain": action.domain, "tbl": table, "pk": target_pk,
                    "actor": actor_id, "role": actor_role,
                    "params": _json(params), "before": _json(before), "after": _json(after), "source": source,
                },
            )
    finally:
        await engine.dispose()

    try:
        project(action.id, target_pk)
        projected = True
    except Exception as e:  # 投影失败不回滚业务状态（设计 §2 步骤 5）
        projected = False
        errors.append(f"{type(e).__name__}: {e}")

    return {
        "action_id": action.id, "target": obj.api_name, "pk": str(target_pk),
        "before": before, "after": after, "source": source,
        "projected": projected, "errors": errors,
    }


def _json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, default=str)
```

> **注**：`before`/`after` 里的 datetime 等非 JSON 类型由 `default=str` 兜底；`after` 中 `now=True` 的列记 `None`，表示"由 DB 决定"，真实值以重投影后的图为准（这是有意的：避免在事务外再查一次）。

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_executor.py -v`
Expected: PASS（5 项）。若报 `dg_action_audit` 不存在，说明 gateway 尚未重启建表——先跑 `docker compose -p eai-docker -f docker-compose-dev.yaml restart gateway`。

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/app/ontology/actions/executor.py ontostudio/backend/tests/test_actions_executor.py
git commit -m "feat(ontostudio): 动作执行管线(事务/前置/审计/容错重投影)"
```

---

## Task 6: gateway 侧 —— 授权缓存键修正 + `/api/permissions/scope` + 权限声明

**Files:**
- Modify: `backend/app/extensions/auth/routers.py`
- Create: `backend/app/extensions/auth/authz_cache.py`
- Modify: `config/permissions.yaml`, `deploy/offline/config/permissions.yaml`
- Modify: `ontostudio/backend/app/auth.py`（缓存键同步修正）
- Test: `backend/tests/test_permissions_scope_endpoint.py`

> **必须先修的既有缺陷**：OntoStudio 的 `_authz_cache: dict[user_id, (bool, float)]` **只按用户做键**，值的含义却是"该用户对**某一次查询的那个权限**是否放行"。目前只用一个权限（`system:access`）所以没暴露；本设计要按动作查第二个权限（`ontology:action:review`），**同一用户在 30s 内查两个权限会命中错误缓存**。两处都要改成 `(user_id, permission)` 复合键，并各加一条回归测试。

- [ ] **Step 1: 写失败测试（缓存键 + 端点）**

```python
# backend/tests/test_permissions_scope_endpoint.py
"""数据范围端点 + 授权缓存键回归。"""
import uuid

import pytest

from app.extensions.auth.authz_cache import AuthzCache


def test_authz_cache_keys_by_user_and_permission():
    """同一用户查两个权限不得互相污染——历史实现只按 user_id 做键。"""
    c = AuthzCache(ttl_seconds=30.0)
    uid = uuid.uuid4()
    c.put(uid, "system:access", True)
    c.put(uid, "ontology:action:review", False)
    assert c.get(uid, "system:access") is True
    assert c.get(uid, "ontology:action:review") is False


def test_authz_cache_expires():
    c = AuthzCache(ttl_seconds=0.0)
    uid = uuid.uuid4()
    c.put(uid, "p", True)
    assert c.get(uid, "p") is None


def test_authz_cache_invalidate_user_drops_all_permissions():
    c = AuthzCache(ttl_seconds=30.0)
    uid = uuid.uuid4()
    c.put(uid, "a", True)
    c.put(uid, "b", False)
    c.invalidate_user(uid)
    assert c.get(uid, "a") is None and c.get(uid, "b") is None
```

以及端点测试（沿用现网 `admin_client` / `user_client` 装置；若不存在则用 `TestClient(app)` + 登录 helper）：

```python
@pytest.mark.asyncio
async def test_scope_endpoint_returns_none_allow_without_scopes(admin_client):
    ""'ontology' 模块未授 ontology_all 的角色 → none_allow。"""
    r = await admin_client.get("/api/permissions/scope", params={"resource": "ontology"})
    assert r.status_code == 200
    assert r.json()["rule"]["operator"] in ("none_allow", "allow_all")


@pytest.mark.asyncio
async def test_scope_endpoint_unknown_resource_is_none_allow(admin_client):
    r = await admin_client.get("/api/permissions/scope", params={"resource": "no_such_module"})
    assert r.status_code == 200
    assert r.json()["rule"]["operator"] == "none_allow"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_permissions_scope_endpoint.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.extensions.auth.authz_cache'`

- [ ] **Step 3: 实现 `authz_cache.py`**

```python
# backend/app/extensions/auth/authz_cache.py
"""授权判定结果缓存。

EAI-CUSTOM (2026-09-22): 键必须是 (user_id, permission) 复合键。
历史实现只按 user_id 做键、值的语义却是"某一次查询的那个权限"——
在只查单一权限（system:access）时未暴露；本体动作层引入第二个权限后
会造成跨权限串味（把一个权限的放行结果当成另一个的）。见
docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3。
"""

from __future__ import annotations

import threading
import time
import uuid


class AuthzCache:
    """进程内 TTL 缓存。部署为单实例，进程内即可；失败方向恒为 fail-closed。"""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._data: dict[tuple[uuid.UUID, str], tuple[bool, float]] = {}
        self._lock = threading.Lock()

    def get(self, user_id: uuid.UUID, permission: str) -> bool | None:
        with self._lock:
            hit = self._data.get((user_id, permission))
            if hit is None:
                return None
            allowed, expires_at = hit
            if time.monotonic() >= expires_at:
                self._data.pop((user_id, permission), None)
                return None
            return allowed

    def put(self, user_id: uuid.UUID, permission: str, allowed: bool) -> None:
        with self._lock:
            self._data[(user_id, permission)] = (allowed, time.monotonic() + self._ttl)

    def invalidate_user(self, user_id: uuid.UUID) -> None:
        with self._lock:
            for key in [k for k in self._data if k[0] == user_id]:
                self._data.pop(key, None)
```

- [ ] **Step 4: 接入 `routers.py` 并加 `/scope` 端点**

在 `backend/app/extensions/auth/routers.py` 中：

(a) 把 `/me` 所在 router 的 `@router.get("/me", ...)` **之前**插入新端点：

```python
@router.get("/scope")
async def get_data_scope(
    resource: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """返回当前用户对某资源的数据范围规则（序列化 FilterRule）。

    EAI-CUSTOM (2026-09-22): 供 OntoStudio 动作层做实例级权限判定。
    只读、无副作用；resource 为 permissions.yaml 的**模块 key**。
    未知资源或角色无 scope → none_allow（fail-closed）。
    """
    from app.extensions.auth.datascope import DataScopeEngine
    from app.extensions.auth.identity import AttributeSet

    engine = DataScopeEngine.from_registry()
    identity = AttributeSet.from_current_user(current_user)
    rule = engine.get_data_scope(identity, resource)
    return {"resource": resource, "rule": rule.to_wire()}
```

**已验证：这两个方法都不存在，必须新增**（`engine.py` 的 `FilterRule` 是纯 dataclass 无任何方法；`identity.py` 的 `AttributeSet` 只有 `to_dict` / `get_attr`）。

在 `backend/app/extensions/auth/engine.py` 的 `FilterRule` 类内追加：

```python
    def to_wire(self) -> dict[str, Any]:
        """序列化给 OntoStudio（独立服务，无法 import 本模块）。

        形态必须与 ontostudio/backend/app/ontology/scope.py::FilterRule.to_wire 逐字段一致；
        经 FastAPI 返回时 uuid.UUID 由 jsonable_encoder 转为字符串，对端按字符串处理。
        """
        out: dict[str, Any] = {"operator": self.operator}
        if self.field is not None:
            out["field"] = self.field
        if self.value is not None:
            out["value"] = self.value
        if self.children is not None:
            out["children"] = [c.to_wire() for c in self.children]
        return out
```

在 `backend/app/extensions/auth/identity.py` 的 `AttributeSet` 类内追加：

```python
    @classmethod
    def from_current_user(cls, user, *, member_projects: list[str] | None = None) -> "AttributeSet":
        """由 gateway CurrentUser 构造授权身份（供 /api/permissions/scope 使用）。

        字段面与既有 rule_template 的 `$identity.*` 引用面一致
        （user_id / role_code / dept_ids / member_projects）。
        member_projects 需调用方查库后传入；缺省空表会让
        `id IN $identity.member_projects` 解析为 none_allow（fail-closed，安全方向）。
        """
        return cls(
            user_id=str(user.id),
            role_code=user.role_name,
            dept_ids=[str(user.dept_id)] if getattr(user, "dept_id", None) else [],
            member_projects=member_projects or [],
        )
```

> **必须验证的一处**：`DataScopeEngine` 用 `identity.role_code` 去查 `_role_data_scopes`，而该字典由 `registry.list_role_codes()` 建键——是角色 **code**；而 `CurrentUser.role_name` 拿到的可能是角色 **名称**。**两者若不同名，角色永远匹配不到任何 scope，结果恒为 `none_allow`（动作全部 404）**。在 Step 7 前先跑一次实证：
> ```bash
> cd backend && PYTHONPATH=. uv run python -c "
> from app.extensions.auth.registry import get_permission_registry as g
> print('list_role_codes:', g().list_role_codes()[:5])
> print('a role data_scopes:', g().get_data_scopes_for_role('admin'))
> "
> ```
> 若键与 `CurrentUser.role_name` 不一致，改用能对上的那个字段（可能是 `user.role_id` 反查），并在 `from_current_user` 的 docstring 里写明依据。**不要靠猜。**

(b) 用 `AuthzCache` 替换 `routers.py` 中模块级的 `_authz_cache` dict，并把 `get/put` 调用改为传 `(user.id, permission)`。

- [ ] **Step 5: 声明权限点与数据范围**

`config/permissions.yaml` 的 `ontology:` 模块（约 L259）内：

- `pages[0].operations` 追加 `- { id: "ontology:action:review", display_name: "审核抽取实体" }`
- 模块级追加 `data_scopes`（该模块当前是 `data_scopes: []`）：

```yaml
    data_scopes:
      - { id: "ontology_all", display_name: "全部本体数据", rule_template: {} }
```

- 给需要审核权的角色补上（至少 `admin` 与 `superadmin`）：
  `ontology:action:review` 加到其 `permissions`；`ontology_all` 加到其 `data_scopes`。

`deploy/offline/config/permissions.yaml` **做完全相同的三处改动**——漏掉则离线部署恒 404。

- [ ] **Step 6: 同步修正 OntoStudio 侧的缓存键**

`ontostudio/backend/app/auth.py`：把 `_authz_cache: dict[uuid.UUID, tuple[bool, float]]` 及 `_gateway_authorizes` 的读写改为 `(user.id, permission)` 复合键。在 `ontostudio/backend/tests/test_main.py` 补一条与 Step 1 同形的回归测试（同用户两权限不串味）。

- [ ] **Step 7: 跑测试确认通过**

Run:
```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_permissions_scope_endpoint.py -v
cd ../ontostudio/backend && PYTHONPATH=. uv run pytest tests/test_main.py -v
```
Expected: 全 PASS

- [ ] **Step 8: 提交**

```bash
git add backend/app/extensions/auth/ backend/tests/test_permissions_scope_endpoint.py config/permissions.yaml deploy/offline/config/permissions.yaml ontostudio/backend/app/auth.py ontostudio/backend/tests/test_main.py
git commit -m "feat(auth): 数据范围端点 + 授权缓存键改 (user,permission) 复合键

缓存键缺陷: 原实现只按 user_id 做键, 值语义却是某一次查询的权限——
单权限时未暴露, 本体动作层引入第二个权限后会造成跨权限串味。
ontology 模块补 ontology_all 数据范围与 ontology:action:review 操作权限。"
```

---

## Task 7: REST 暴露面

**Files:**
- Modify: `ontostudio/backend/app/ontology/routers.py`
- Test: `ontostudio/backend/tests/test_actions_rest.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_actions_rest.py
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_invoke_requires_auth():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/extensions/ontology/actions/invoke",
                         json={"action_id": "review_entity.confirm", "pk": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_invoke_unknown_action_is_404(auth_headers):
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post("/api/extensions/ontology/actions/invoke",
                         json={"action_id": "nope.nope", "pk": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_rest.py -v`
Expected: FAIL —— 404（路由不存在）

- [ ] **Step 3: 实现（`routers.py` 追加）**

```python
@router.post("/actions/invoke")
async def invoke_action_endpoint(
    body: ActionInvokeRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("system:access")),
):
    """执行一个已声明的动作（设计 §2）。

    权限分两层：操作权限（required_permissions，经 request_action 判定）
    与数据范围（scope_resource → FilterRule）。两者任一不过即拒。
    """
    from app.ontology.actions.executor import ActionError, invoke_action_core
    from app.ontology.scope import FilterRule

    try:
        action, scope_rule = await _authz_for_action(request, user, body.action_id)
        return await invoke_action_core(
            body.action_id,
            body.params,
            target_pk=uuid.UUID(body.pk),
            actor_id=user.id,
            actor_role=user.role_name,
            source="api",
            scope_rule=scope_rule,
            project=lambda aid, pk: _project_incrementally(aid, pk),
        )
    except ActionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
```

配套在本文件内新增：

```python
class ActionInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    pk: str
    params: dict[str, Any] = Field(default_factory=dict)


async def _authz_for_action(request: Request, user: CurrentUser, action_id: str) -> tuple[Any, "FilterRule"]:
    """解析动作 → 逐条校验 required_permissions → 取 scope_resource 的范围规则。"""
    from app.ontology.actions.executor import ActionError, _resolve
    from app.ontology.scope import FilterRule

    action, obj = _resolve(action_id)
    for perm in action.required_permissions:
        if not await authorize(request, user, perm):
            raise ActionError(f"缺少权限：{perm}", status_code=403)

    if not obj.scope_resource:
        return action, FilterRule(operator="allow_all")
    rule = await fetch_scope_rule(request, obj.scope_resource)
    return action, rule


def _project_incrementally(action_id: str, pk: uuid.UUID) -> None:
    """增量重投影：只刷新受影响行对应的三元组（设计 §2 步骤 5）。

    当前实现委托给既有的全量入口（P1-7 收敛为独立任务）；此处保证异常向外抛，
    由 executor 记入 errors——不吞异常。
    """
    from app.ontology.kernel.service import get_kernel
    get_kernel().refresh()
```

`authorize(...)` / `fetch_scope_rule(...)` 放在 `ontostudio/backend/app/auth.py`：前者是对既有 `_gateway_authorizes` 的公开包装（含复合键缓存），后者调用 gateway 的 `/api/permissions/scope` 并把 `rule` 反序列化为本地 `FilterRule`；二者失败均 fail-closed（`False` / `none_allow`）。

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_rest.py -v`
Expected: PASS（2 项）

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/app/ontology/routers.py ontostudio/backend/app/auth.py ontostudio/backend/tests/test_actions_rest.py
git commit -m "feat(ontostudio): POST /actions/invoke + 动作级授权(权限+数据范围双层)"
```

---

## Task 8: MCP 暴露面

**Files:**
- Modify: `ontostudio/backend/app/ontology/mcp.py`
- Test: `ontostudio/backend/tests/test_actions_mcp.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_actions_mcp.py
import pytest

from app.ontology.mcp import TOOLS


def _tool(name):
    return next((t for t in TOOLS if t.name == name), None)


def test_invoke_action_tool_registered():
    t = _tool("invoke_action")
    assert t is not None
    assert set(t.inputSchema["required"]) == {"action_id", "pk"}


def test_review_entity_tool_registered():
    t = _tool("review_entity")
    assert t is not None
    assert set(t.inputSchema["required"]) == {"pk", "decision"}
    assert set(t.inputSchema["properties"]["decision"]["enum"]) == {"confirm", "reject"}


def test_action_ids_match_registry():
    """工具暴露的动作 id 必须与 registry 声明一致（防手写清单漂移）。"""
    from app.ontology.registry import get_registry
    declared = set(get_registry().actions)
    assert "review_entity.confirm" in declared
    assert "review_entity.reject" in declared
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_mcp.py -v`
Expected: FAIL —— `invoke_action` 为 None

- [ ] **Step 3: 加工具声明（`_TOOLS_SPEC` 追加两项）**

```python
    (
        "invoke_action",
        "执行一个已声明的受治理动作（写回业务数据并记审计）。先用 describe_ontology 查看可用 action_id 清单与参数。权限与数据范围在服务端强制。",
        {
            "type": "object",
            "properties": {
                "action_id": {"type": "string", "description": "如 review_entity.confirm"},
                "pk": {"type": "string", "description": "目标对象主键(uuid)"},
                "params": {"type": "object", "description": "动作参数(按 describe_ontology 声明的形状)"},
            },
            "required": ["action_id", "pk"],
        },
    ),
    (
        "review_entity",
        "审核抽取实体的快捷入口（高频动作的具名包装，内部走同一条动作执行体）。decision=confirm 置 active，reject 置 rejected。",
        {
            "type": "object",
            "properties": {
                "pk": {"type": "string", "description": "实体主键(uuid)"},
                "decision": {"type": "string", "enum": ["confirm", "reject"]},
            },
            "required": ["pk", "decision"],
        },
    ),
```

- [ ] **Step 4: 加分派与处理函数**

在 `call_tool` 的 `handlers` 字典中加入：

```python
        "invoke_action": _invoke_action,
        "review_entity": _review_entity,
```

并在本文件内实现（与既有 handler 同形，返回 `list[TextContent]`）：

```python
async def _invoke_action(arguments: dict):
    from app.ontology.actions.executor import ActionError, run_action_for_mcp
    try:
        return _ok(await run_action_for_mcp(arguments.get("action_id", ""), arguments.get("pk", ""), "mcp"))
    except ActionError as e:
        return _err(e)


async def _review_entity(arguments: dict):
    from app.ontology.actions.executor import ActionError, run_action_for_mcp
    mapping = {"confirm": "review_entity.confirm", "reject": "review_entity.reject"}
    action_id = mapping.get(arguments.get("decision"))
    if action_id is None:
        return _err(ValueError(f"decision must be one of {sorted(mapping)}"))
    try:
        return _ok(await run_action_for_mcp(action_id, arguments.get("pk", ""), "mcp"))
    except ActionError as e:
        return _err(e)
```

`_ok(...)` 是本文件内与既有 `_err(...)` 对称的小助手（`_err` 已存在）：`return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]`。

`run_action_for_mcp` 放在 `actions/executor.py`（**不是** routers.py）——MCP 层不应依赖 REST 层。它需要在该文件顶部补 `from app.ontology.kernel.service import get_kernel`（`_resolve` 同文件已有）：

```python
async def run_action_for_mcp(action_id: str, pk: str, source: str) -> dict[str, Any]:
    """MCP 侧入口：MCP 走共享头鉴权而非 cookie，故数据范围按服务身份取（域级）。

    EAI-CUSTOM: 设计 §3「今日实际形态」——无身份列时范围只可能是
    allow_all / none_allow 二态，与调用者身份无关；故 MCP 通道直接取
    registry 声明的 scope_resource 对应模块的**服务级**范围（当前恒 allow_all），
    待行级具备归属轴后再按调用者解析。
    """
    from app.ontology.actions.executor import invoke_action_core
    from app.ontology.scope import FilterRule
    action, _obj = _resolve(action_id)
    return await invoke_action_core(
        action_id, {}, target_pk=uuid.UUID(pk),
        actor_id=uuid.UUID(int=0), actor_role="mcp", source=source,
        scope_rule=FilterRule(operator="allow_all"),
        project=lambda aid, p: get_kernel().refresh(),
    )
```

> **这是一处有意的简化**，用 `ponytail:` 注释在代码里标明：MCP 通道当前不区分调用者身份（域级二态下没有可区分的维度）。待行级归属轴落地的任务里必须改成按调用者解析——**这是已知的、被记录的天花板，不是遗漏**。

- [ ] **Step 5: `describe_ontology` 附动作清单**

在 `_describe` 的返回值中追加（与既有字段并列）：

```python
        "actions": [
            {
                "id": a.id, "display_name": a.display_name, "description": a.description,
                "target": a.target, "required_permissions": a.required_permissions,
                "preconditions": [c.model_dump() for c in a.preconditions],
                "postconditions": [c.model_dump() for c in a.postconditions],
            }
            for a in get_registry().actions.values()
        ],
```

- [ ] **Step 6: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_actions_mcp.py -v`
Expected: PASS（3 项）

- [ ] **Step 7: 提交**

```bash
git add ontostudio/backend/app/ontology/mcp.py ontostudio/backend/app/ontology/actions/executor.py ontostudio/backend/tests/test_actions_mcp.py
git commit -m "feat(ontostudio): MCP invoke_action + review_entity 具名包装(共用执行体)"
```

---

## Task 9: lint 扩展 —— scope 绑定校验

**Files:**
- Modify: `ontostudio/backend/scripts/ontology_lint.py`
- Test: `ontostudio/backend/tests/test_lint_scope_bindings.py`

- [ ] **Step 1: 写失败测试**

```python
# ontostudio/backend/tests/test_lint_scope_bindings.py
from app.ontology.schemas import DomainFile


def _ot(**over):
    base = {
        "api_name": "graph_entity", "display_name": "实体", "description": "d", "domain": "doc_graph",
        "access": {"path": "postgres_ext", "table": "dg_entities"},
        "pk": {"column": "id", "api_name": "id", "type": "uuid"},
        "properties": [{"name": "id", "api_name": "id", "type": "uuid", "description": "p"}],
    }
    base.update(over)
    return base


def test_object_without_scope_resource_is_fine():
    DomainFile.model_validate({"object_types": [_ot()]})

def test_scope_resource_requires_known_module():
    """scope_resource 必须是已知模块 key（离线模板也要有）。"""
    from scripts.ontology_lint import check_scope_resources
    d = DomainFile.model_validate({"object_types": [_ot(scope_resource="no_such_module")]})
    problems = check_scope_resources(d, known_modules={"ontology", "contract_price"})
    assert problems and "no_such_module" in problems[0]


def test_scope_resource_known_module_passes():
    from scripts.ontology_lint import check_scope_resources
    d = DomainFile.model_validate({"object_types": [_ot(scope_resource="ontology")]})
    assert check_scope_resources(d, known_modules={"ontology"}) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_lint_scope_bindings.py -v`
Expected: FAIL —— `ImportError: cannot import name 'check_scope_resources'`

- [ ] **Step 3: 实现（`ontology_lint.py` 追加）**

```python
def check_scope_resources(domain_file, known_modules: set[str]) -> list[str]:
    """每个 scope_resource 必须是已知模块 key。

    EAI-CUSTOM: 设计 §3。模块 key 取自 config/permissions.yaml 的顶层 modules。
    未知模块会让 DataScopeEngine 返回 none_allow → 动作恒 404。
    """
    problems: list[str] = []
    for ot in domain_file.object_types:
        if ot.scope_resource and ot.scope_resource not in known_modules:
            problems.append(
                f"{ot.api_name}: scope_resource {ot.scope_resource!r} 不是已知权限模块"
                f"（可选：{sorted(known_modules)}）"
            )
    return problems
```

并在 `main()` 中用 yaml 解析 `config/permissions.yaml` 的 `modules` 顶层键取得 `known_modules`，对每个域文件调用 `check_scope_resources`，非空则计入失败并以非零码退出。

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_lint_scope_bindings.py -v && PYTHONPATH=. uv run python scripts/ontology_lint.py`
Expected: PASS + lint 退出码 0（真实 registry 全绿）

- [ ] **Step 5: 提交**

```bash
git add ontostudio/backend/scripts/ontology_lint.py ontostudio/backend/tests/test_lint_scope_bindings.py
git commit -m "chore(ontostudio): lint 校验 scope_resource 指向已知权限模块"
```

---

## Task 10: 端到端验收

**Files:**
- Create: `ontostudio/backend/tests/test_actions_e2e.py`

- [ ] **Step 1: 写验收测试（对应 spec §7 的 6 条）**

```python
# ontostudio/backend/tests/test_actions_e2e.py
"""spec §7 端到端验收。需要 ONTOSTUDIO_GATEWAY_URL 可达（容器网络内跑）。"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.connectors import _ext_url
from app.ontology.kernel.service import get_kernel

pytestmark = pytest.mark.integration


async def _seed(status="pending_review") -> uuid.UUID:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            r = await conn.execute(
                text("""INSERT INTO dg_entities (domain,etype,canonical_name,norm_name,attrs,confidence,status)
                        VALUES ('doc_graph','mine','E2E', :n, '{}'::jsonb, 0.9, :s) RETURNING id"""),
                {"n": f"E2E-{uuid.uuid4().hex[:8]}", "s": status},
            )
            return r.scalar_one()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_01_confirm_then_shacl_clean():
    """① pending_review → confirm → active，审计有行，重投影后 SHACL 无违规。"""
    pk = await _seed()
    get_kernel().refresh()                      # 投影前
    # 通过 run_action_for_mcp 走完整链路
    from app.ontology.actions.executor import run_action_for_mcp
    result = await run_action_for_mcp("review_entity.confirm", str(pk), "mcp")
    assert result["after"] == {"status": "active"}

    from app.ontology.kernel.conformance import run_conformance
    from app.ontology.registry import get_registry
    checks = run_conformance(get_kernel().store, get_registry())
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]


@pytest.mark.asyncio
async def test_02_precondition_violation_is_409():
    pk = await _seed(status="active")
    from app.ontology.actions.executor import ActionError, run_action_for_mcp
    with pytest.raises(ActionError) as e:
        await run_action_for_mcp("review_entity.confirm", str(pk), "mcp")
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_04_projection_failure_recorded_not_rolled_back():
    """④ 投影失败：业务状态已提交、errors 有记录。"""
    pk = await _seed()
    from app.ontology.actions.executor import invoke_action_core
    from app.ontology.scope import FilterRule

    def boom(*a, **k):
        raise RuntimeError("proj boom")

    r = await invoke_action_core(
        "review_entity.confirm", {}, target_pk=pk, actor_id=uuid.uuid4(),
        actor_role="admin", source="api", scope_rule=FilterRule(operator="allow_all"), project=boom,
    )
    assert r["projected"] is False and r["errors"]


@pytest.mark.asyncio
async def test_05_lint_reports_unbound_scope_field():
    """⑤ lint 对"模板字段无绑定"报错（用一个构造出的坏绑定）。"""
    from app.ontology.schemas import DomainFile
    with pytest.raises(ValueError, match="unknown scope binding"):
        DomainFile.model_validate({
            "object_types": [{
                "api_name": "x", "display_name": "x", "description": "d", "domain": "d",
                "access": {"path": "postgres_ext", "table": "t"},
                "pk": {"column": "id", "api_name": "id", "type": "uuid"},
                "properties": [{"name": "id", "api_name": "id", "type": "uuid", "description": "p"}],
                "scope_bindings": {"user_id": "missing_col"},
            }],
        }).validate_action_refs()
```

③（无 `ontology:action:review` → 403）与 ⑥（lint 真实 registry 全绿）在 Task 6 与 Task 9 已各自覆盖，此处不重复；验收时把两处测试的通过结果一并记录。

- [ ] **Step 2: 跑验收**

Run:
```bash
cd ontostudio/backend && PYTHONPATH=. uv run pytest tests/test_actions_e2e.py -v
```
Expected: PASS（4 项）

- [ ] **Step 3: 重启容器并做一次真人路径验证**

```bash
cd ../../docker
docker compose -p eai-docker -f docker-compose-dev.yaml restart gateway ontostudio-backend
# 建表（gateway create_all）+ 内核重载
docker exec -w /app ontostudio-backend /app/.venv/bin/python -c "from app.ontology.kernel.service import get_kernel; print(get_kernel().refresh())"
```
Expected: `dg_action_audit` 出现在 `\dt` 列表；refresh 的 `errors=[]`

- [ ] **Step 4: 提交**

```bash
git add ontostudio/backend/tests/test_actions_e2e.py
git commit -m "test(ontostudio): 动作层端到端验收(spec §7)"
```

---

## 收尾（不属任何单个 Task）

- [ ] **⚠️ 本计划全部测试在 CI 里不会被执行**（Task 1 审查实测发现）：`.github/workflows/backend-unit-tests.yml:118-120` 明写 ontology 域 CI 职责"由 ontostudio 侧后续自建"，而 `.github/workflows/` 下**没有任何 ontostudio workflow**。叠加 `pytestmark = pytest.mark.integration`（需外部 PG，多数环境 skip），实际效果是 **ontostudio 的 33 条单测 + 集成测试都只在人手执行时跑**。这使本计划里所有"回归护栏"的承诺降级为"人手护栏"。**是否补 CI 需单独决策**（新增 workflow 是仓库级改动，不属本计划范围）；但**决策前不要假设这些测试会在 PR 上自动拦住回归**。

- [ ] **`scope.py` 的 docstring 措辞需收窄**（Task 1 复审 Minor）：类 docstring 写"**所有**畸形输入都归一到这里"，被深层嵌套证伪——实测 3000 层 → `RecursionError` 且 `isinstance(e, ScopeCompileError)` 为 `False`。但该路径**经 HTTP 不可达**（`json.loads` 对同深度 payload 先抛 `RecursionError`，请求层比 `from_wire` 先死），故不需代码改动，只需把措辞收窄为"所有**形状**畸形输入"，或注明"深度递归由请求边界兜底"。**要点是别让 Task 5 读到绝对承诺而以为不必兜 `RecursionError`。**


- [ ] 全量回归：`cd ontostudio/backend && PYTHONPATH=. uv run pytest tests/ -v` 与 `cd backend && PYTHONPATH=. uv run pytest tests/ -k "auth or permissions" -v`
- [ ] `ruff check . && ruff format --check .`（ontostudio/backend 与 backend 各跑一次）
- [ ] 更新 `.wolf/anatomy.md`（新增 4 个文件）与 `.wolf/memory.md`
- [ ] **未纳入本计划**（属 spec §4 的折叠步）：`merge_entities` / `unmerge` 折叠为动作、删除旧实现。**必须另起计划**，且在本计划全部 Task 绿之后才能开工。
