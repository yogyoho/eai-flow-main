"""evaluate 编排测试——host 纯逻辑（monkeypatch facts/store/facade）+ DB-gated 真库冒烟.

EAI-CUSTOM: plan docs/superpowers/plans/2026-09-13-ontology-reasoning-rules.md Task 3 Step 3.4。
host 部分不上 DB（load_facts 打桩 + stub RuleStore + spy facade）, 断言域过滤/空态早退/
stale 可观测; DB 部分照 test_doc_graph_ingest.py 探针 skip 模式（host 无库自动 skip,
真库验证在容器内 Task 4）, 冒烟数据 _MARK 唯一命名 + 参数化 DELETE 清理——失败也不误删他人数据。
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.extensions.ontology.doc_graph.reasoning import evaluate as evaluate_mod
from app.extensions.ontology.doc_graph.reasoning import rule_registry
from app.extensions.ontology.doc_graph.reasoning.evaluate import evaluate_rules
from app.extensions.ontology.doc_graph.reasoning.facade import RuleFacade, RuleSyntaxError
from app.extensions.ontology.doc_graph.reasoning.rule_registry import RuleModel

# --- host 纯逻辑（不上 DB）-------------------------------------------------------------


class _SpyFacade(RuleFacade):
    """记录注册/run 调用而不改变行为——断言域过滤与空态早退用。"""

    def __init__(self) -> None:
        super().__init__()
        self.facts_added: list[tuple] = []
        self.rules_registered: list[str] = []
        self.ran = False

    def add_fact(self, *args, **kwargs):
        self.facts_added.append(args)
        return super().add_fact(*args, **kwargs)

    def add_rule(self, name, when_patterns, derive):
        self.rules_registered.append(name)
        return super().add_rule(name, when_patterns, derive)

    def run(self):
        self.ran = True
        return super().run()


def _rule(name: str, domain: str, enabled: bool = True) -> RuleModel:
    """按域生成一条最小合法规则（eia 用 org_develops_project→org_involved_in, bid 用 bidder_of_project 自派生）。"""
    if domain == "eia":
        when, derive = "org_develops_project(?X, ?Y)", "org_involved_in(?X, ?Y)"
    else:
        when = derive = "bidder_of_project(?X, ?Y)"
    return RuleModel(name=name, enabled=enabled, domain=domain, when=[when], derive=derive, note="测试规则")


class _StubStore:
    """替身 RuleStore: 只实现 evaluate_rules 消费的 get()/last_error 面。"""

    def __init__(self, rules: list[RuleModel], last_error: str | None = None) -> None:
        self._rules = rules
        self.last_error = last_error

    def get(self):
        return SimpleNamespace(enabled_rules=[r for r in self._rules if r.enabled])


@pytest.fixture()
def stub_store(monkeypatch):
    """安装替身规则存储（替换进程单例 get_rules_store）, 返回安装函数。"""

    def _install(rules: list[RuleModel], last_error: str | None = None) -> _StubStore:
        store = _StubStore(rules, last_error)
        monkeypatch.setattr(rule_registry, "get_rules_store", lambda: store)
        return store

    return _install


def _install_spy_facade(monkeypatch) -> list[_SpyFacade]:
    """把 evaluate 模块的 RuleFacade 换成 spy 工厂, 返回实例收集列表。"""
    instances: list[_SpyFacade] = []

    def _factory() -> _SpyFacade:
        s = _SpyFacade()
        instances.append(s)
        return s

    monkeypatch.setattr(evaluate_mod, "RuleFacade", _factory)
    return instances


def test_domain_filter_and_fact_registration(monkeypatch, stub_store):
    """domain 不匹配 / enabled=false 的规则不注册; 同域 enabled 规则注册且事实全量入 facade。"""
    stub_store([_rule("eia_on", "eia"), _rule("eia_off", "eia", enabled=False), _rule("bid_on", "bid")])

    async def _facts(domain, min_confidence=0.7):
        assert domain == "eia"
        return [("org_a", "org_develops_project", "proj_x"), ("mine_m", "mine", "mine_m")]

    monkeypatch.setattr(evaluate_mod, "load_facts", _facts)
    spies = _install_spy_facade(monkeypatch)

    out = asyncio.run(evaluate_rules("eia"))

    assert len(spies) == 1
    spy = spies[0]
    assert spy.rules_registered == ["eia_on"], "bid 域规则与 disabled 规则都不注册"
    assert len(spy.facts_added) == 2
    assert out["rules_loaded"] == 1
    assert out["stale_rules"] is False and out["stale_rules_error"] is None
    assert out["truncated"] is False
    assert any(d["subject"] == "org_a" and d["predicate"] == "org_involved_in" for d in out["derived_facts"])
    assert spy.ran is True


def test_empty_facts_early_exit(monkeypatch, stub_store):
    """空事实域合法: 直接零派生返回, 不构建 facade（空态早退, 规则计数仍透出）。"""
    stub_store([_rule("eia_on", "eia")])

    async def _facts(domain, min_confidence=0.7):
        return []

    monkeypatch.setattr(evaluate_mod, "load_facts", _facts)

    def _boom() -> _SpyFacade:
        raise AssertionError("空事实不应构建 facade")

    monkeypatch.setattr(evaluate_mod, "RuleFacade", _boom)

    out = asyncio.run(evaluate_rules("eia"))

    assert out["derived_facts"] == [] and out["activations"] == []
    assert out["rules_loaded"] == 1
    assert out["stats"]["iterations"] == 0 and out["stats"]["facts_total"] == 0
    assert out["truncated"] is False and out["stale_rules"] is False


def test_stale_rules_observability(monkeypatch, stub_store):
    """RuleStore.last_error 非空（热重载失败保旧快照）→ stale_rules=true + 错误摘要透出。"""
    stub_store([_rule("eia_on", "eia")], last_error="eia.yaml: YAML 语法错误")

    async def _facts(domain, min_confidence=0.7):
        return [("m", "mine", "m")]

    monkeypatch.setattr(evaluate_mod, "load_facts", _facts)
    _install_spy_facade(monkeypatch)

    out = asyncio.run(evaluate_rules("eia"))

    assert out["stale_rules"] is True
    assert "eia.yaml" in out["stale_rules_error"]


def test_no_rules_hint_names_known_domains(stub_store):
    """零注册规则短路（不查库）: rules_loaded=0 + hint 命名已知域, 防止空结果被误读为无数据。"""
    stub_store([_rule("eia_on", "eia")])

    out = asyncio.run(evaluate_rules("bid"))

    assert out["rules_loaded"] == 0 and out["derived_facts"] == []
    assert "bid" in out["hint"] and "eia" in out["hint"]
    assert "无注册规则" in out["hint"]


def test_real_repo_rules_end_to_end_on_host(monkeypatch):
    """真仓规则单例（rules/eia.yaml 两条演示规则）+ 打桩事实 → host 全链路前向链:
    笛卡尔积规则对 1 边 × 2 矿派生 2 条 org_involved_in, 单模式规则不误触。"""

    async def _facts(domain, min_confidence=0.7):
        return [
            ("org_a", "org_develops_project", "proj_p"),
            ("mine_1", "mine", "mine_1"),
            ("mine_2", "mine", "mine_2"),
        ]

    monkeypatch.setattr(evaluate_mod, "load_facts", _facts)

    out = asyncio.run(evaluate_rules("eia"))

    assert out["rules_loaded"] == 2  # 真仓两条 eia 演示规则均 enabled
    derived = {(d["subject"], d["predicate"], d["object"], d["rule"]) for d in out["derived_facts"]}
    assert ("org_a", "org_involved_in", "mine_1", "demo_org_involved_in_mine") in derived
    assert ("org_a", "org_involved_in", "mine_2", "demo_org_involved_in_mine") in derived
    assert all(d["rule"] != "demo_project_compile_chain" for d in out["derived_facts"]), "org_compiles_project 无事实, 链式规则不触发"
    assert any(a["rule"] == "demo_org_involved_in_mine" for a in out["activations"])


# --- MCP evaluate_rules 工具（handler 分发层, 不启动 stdio）---------------------------


def test_mcp_evaluate_rules_success_and_no_rules_dir_passthrough(monkeypatch):
    """评审加固: rules_dir 不进 MCP 面——schema 无该属性, agent 硬塞也不透传（防规则注入通道）。"""
    from app.extensions.ontology.doc_graph import mcp as mcp_mod

    spec = next(t for t in mcp_mod.TOOLS if t.name == "evaluate_rules")
    assert "rules_dir" not in spec.inputSchema.get("properties", {})

    async def _fake(domain, rules_dir=None):
        assert rules_dir is None, "agent 提供的 rules_dir 不得透传到 Python API"
        return {"derived_facts": [], "activations": [], "stats": {}, "rules_loaded": 2, "stale_rules": False, "stale_rules_error": None, "truncated": False}

    from app.extensions.ontology.doc_graph.reasoning import evaluate as eval_mod

    monkeypatch.setattr(eval_mod, "evaluate_rules", _fake)
    out = asyncio.run(mcp_mod.call_tool("evaluate_rules", {"domain": "eia", "rules_dir": "/tmp/evil-rules"}))
    assert '"success": true' in out[0].text and '"rules_loaded": 2' in out[0].text


def test_mcp_evaluate_rules_syntax_error_narrow(monkeypatch):
    """RuleSyntaxError 窄捕获 → '规则语法错误' 明确文案（区别于通用 _err 的类型名前缀）。"""
    from app.extensions.ontology.doc_graph import mcp as mcp_mod
    from app.extensions.ontology.doc_graph.reasoning import evaluate as eval_mod

    async def _boom(domain, rules_dir=None):
        raise RuleSyntaxError("malformed rule pattern 'x'")

    monkeypatch.setattr(eval_mod, "evaluate_rules", _boom)
    out = asyncio.run(mcp_mod.call_tool("evaluate_rules", {"domain": "eia"}))
    assert "规则语法错误" in out[0].text and '"success": false' in out[0].text


# --- DB-gated 集成（真库冒烟; host 无库自动 skip）---------------------------------------


def _resolve_url() -> str | None:
    """URL 解析与 connectors._ext_url 同语义: env 优先, 回退 extensions config。"""
    url = os.environ.get("ONTOLOGY_DB_URL")
    if url:
        return url
    try:
        from app.extensions.config import get_extensions_config

        return get_extensions_config().database.url
    except Exception:
        return None


def _tables_ready(url: str) -> bool:
    """探针: dg_entities 可查询才算"库就绪"——连接拒绝/驱动缺失/表未建一律视为不可用。"""

    async def _probe() -> bool:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        engine = create_async_engine(url, poolclass=NullPool, connect_args={"timeout": 2})
        try:
            async with engine.connect() as conn:
                return (await conn.execute(text("SELECT to_regclass('public.dg_entities')"))).scalar() is not None
        except Exception:
            return False
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_probe())
    except Exception:
        return False


_raw_url = _resolve_url()
_URL = _raw_url if _raw_url and _tables_ready(_raw_url) else None


class TestEvaluateRulesAgainstDb:
    pytestmark = pytest.mark.skipif(not _URL, reason="extensions 库未就绪(dg_entities 表不可达/未建)——真库验证在容器内 Task 4")

    _MARK = "smkev" + uuid4().hex[:8]  # 每次运行唯一; normalize 后仍小写, LIKE 圈定安全
    _ORG = f"冒烟开发主体{_MARK}"
    _PROJ = f"冒烟开发项目{_MARK}"
    _MINE = f"冒烟矿井{_MARK}"
    _DOC = "doc-eval-" + _MARK

    def test_ingest_then_evaluate_derives_org_involved_in_mine(self, tmp_path):
        """ingest 一对 EIA 事实（org_develops_project 边 + mine 实体）→ evaluate_rules("eia")
        派生 org_involved_in(org, mine)（demo_org_involved_in_mine 语义）。"""
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.extensions.ontology.doc_graph.ingest import ingest_extraction
        from app.extensions.ontology.doc_graph.schemas import EiaExtraction

        payload = {
            "domain": "eia",
            "thread_id": "t-eval",
            "entities": [
                {"etype": "org", "name": self._ORG, "confidence": 0.9, "mention": {"document_id": self._DOC, "quote": self._ORG}},
                {"etype": "project", "name": self._PROJ, "confidence": 0.9, "mention": {"document_id": self._DOC, "quote": self._PROJ}},
                {"etype": "mine", "name": self._MINE, "confidence": 0.9, "mention": {"document_id": self._DOC, "quote": self._MINE}},
            ],
            "relations": [
                {
                    "predicate": "org_develops_project",
                    "subject": self._ORG,
                    "object": self._PROJ,
                    "mention": {"document_id": self._DOC, "quote": f"{self._ORG}开发{self._PROJ}"},
                }
            ],
        }

        # rules_dir 覆盖为只含冒烟规则的最小目录: 隔离真库其他 org_develops_project 边的
        # 笛卡尔积规模（避免 1000 派生预算挤掉本边）, 同时验证 rules_dir 参数接线
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "manifest.yaml").write_text("schema_version: 1\nfiles:\n  - file: smoke.yaml\n", encoding="utf-8")
        (rules_dir / "smoke.yaml").write_text(
            "rules:\n"
            "  - name: smoke_org_involved_in_mine\n"
            "    enabled: true\n"
            "    domain: eia\n"
            "    when:\n"
            '      - "org_develops_project(?ORG, ?PROJ)"\n'
            '      - "mine(?MINE)"\n'
            '    derive: "org_involved_in(?ORG, ?MINE)"\n'
            '    note: "冒烟规则（DB-gated 集成测试专用, 非业务定案）"\n',
            encoding="utf-8",
        )

        async def _cleanup():
            engine = create_async_engine(_URL, poolclass=NullPool)
            try:
                async with engine.begin() as conn:
                    await conn.execute(text("DELETE FROM dg_mentions WHERE document_id = :doc"), {"doc": self._DOC})
                    await conn.execute(
                        text(
                            "DELETE FROM dg_relations WHERE subject_id IN "
                            "(SELECT id FROM dg_entities WHERE domain='eia' AND norm_name LIKE '%' || :mark || '%') "
                            "OR object_id IN "
                            "(SELECT id FROM dg_entities WHERE domain='eia' AND norm_name LIKE '%' || :mark || '%')"
                        ),
                        {"mark": self._MARK},
                    )
                    await conn.execute(text("DELETE FROM dg_entities WHERE domain='eia' AND norm_name LIKE '%' || :mark || '%'"), {"mark": self._MARK})
            finally:
                await engine.dispose()

        try:
            asyncio.run(ingest_extraction(EiaExtraction.model_validate(payload)))
            out = asyncio.run(evaluate_rules("eia", rules_dir=str(rules_dir)))
        finally:
            asyncio.run(_cleanup())

        if out["truncated"]:
            pytest.skip("真库活跃实体规模超出推理预算（历史数据增长所致, 非代码问题）——真库验证交容器内 Task 4")
        derived = {(d["subject"], d["predicate"], d["object"], d["rule"]) for d in out["derived_facts"]}
        assert (self._ORG, "org_involved_in", self._MINE, "smoke_org_involved_in_mine") in derived
        assert out["rules_loaded"] == 1
        assert out["stale_rules"] is False
