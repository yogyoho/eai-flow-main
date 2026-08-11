"""Test Formula DAG engine against real 给排水计算书 calculation chain.

Validates:
  1. Dependency derivation from formula input sources
  2. Topological sort ordering constraints
  3. Full execution yields correct results
  4. Parameter change → dirty propagation → incremental recalculation
  5. Change summary for audit trail
"""

import math

import pytest
from app.extensions.formula_engine import (
    FormulaGraph,
    FormulaNode,
    ParamSource,
    ParamSourceType,
)


# ── Fixtures: the real 循环水装置 calculation chain from 给排水计算书.docx ──

@pytest.fixture
def water_system_formulas() -> list[FormulaNode]:
    """Build the 4-formula water-balance chain from §6.1 of the real document.

    Dependency chain: Q → Qe → Qb → Qm, plus Q → Qw → Qm
    """
    return [
        FormulaNode(
            id="Qe",
            name="蒸发水量",
            section="6.1.1",
            expression="Q * KZF * delta_t",
            inputs={
                "Q": ParamSource.user(20000, "m3/h"),
                "KZF": ParamSource.lookup(0.001461, "1/℃",
                                          description="GB/T 50746 表3.3.3, 内插法"),
                "delta_t": ParamSource.user(10, "℃"),
            },
            outputs={"Qe": "m3/h"},
        ),
        FormulaNode(
            id="Qw",
            name="风吹损失水量",
            section="6.1.2",
            expression="Q * 0.001",
            inputs={
                "Q": ParamSource.user(20000, "m3/h"),
            },
            outputs={"Qw": "m3/h"},
        ),
        FormulaNode(
            id="Qb",
            name="排污水量",
            section="6.1.3",
            expression="Qe / (N - 1)",
            inputs={
                "Qe": ParamSource.from_formula("Qe", "Qe"),
                "N": ParamSource.user(5, "",
                                      description="浓缩倍数 N=5"),
            },
            outputs={"Qb": "m3/h"},
        ),
        FormulaNode(
            id="Qm",
            name="补充水量",
            section="6.1.4",
            expression="Qe + Qw + Qb",
            inputs={
                "Qe": ParamSource.from_formula("Qe", "Qe"),
                "Qw": ParamSource.from_formula("Qw", "Qw"),
                "Qb": ParamSource.from_formula("Qb", "Qb"),
            },
            outputs={"Qm": "m3/h"},
        ),
    ]


@pytest.fixture
def built_graph(water_system_formulas: list[FormulaNode]) -> FormulaGraph:
    graph = FormulaGraph()
    graph.add_formulas(water_system_formulas)
    graph.build()
    return graph


# ── Dependency derivation ──

class TestDependencyDerivation:
    def test_derives_correct_dependencies(self, built_graph: FormulaGraph):
        deps = built_graph.dependencies
        # Qe depends only on user inputs → no formula deps
        assert deps["Qe"] == set()
        # Qw depends only on user inputs
        assert deps["Qw"] == set()
        # Qb depends on Qe
        assert deps["Qb"] == {"Qe"}
        # Qm depends on Qe, Qw, Qb
        assert deps["Qm"] == {"Qe", "Qw", "Qb"}

    def test_derives_correct_reverse_deps(self, built_graph: FormulaGraph):
        rdeps = built_graph.reverse_dependencies
        assert rdeps["Qe"] == {"Qb", "Qm"}
        assert rdeps["Qw"] == {"Qm"}
        assert rdeps["Qb"] == {"Qm"}
        assert "Qm" not in rdeps  # nothing depends on Qm

    def test_no_circular_deps(self, built_graph: FormulaGraph):
        """Verify build() didn't raise ValueError (no cycles)."""
        assert len(built_graph.execution_order) > 0


# ── Topological order ──

class TestTopologicalSort:
    def test_parallel_batches(self, built_graph: FormulaGraph):
        order = built_graph.execution_order
        # Batch 0: Qe and Qw (independent, can run in parallel)
        # Batch 1: Qb (depends on Qe)
        # Batch 2: Qm (depends on Qe, Qw, Qb)
        assert len(order) == 3, f"Expected 3 batches, got {len(order)}: {order}"

        batch0 = set(order[0])
        batch1 = set(order[1])
        batch2 = set(order[2])

        assert batch0 == {"Qe", "Qw"}, f"Batch 0: {batch0}"
        assert batch1 == {"Qb"}, f"Batch 1: {batch1}"
        assert batch2 == {"Qm"}, f"Batch 2: {batch2}"

    def test_ordering_constraint(self, built_graph: FormulaGraph):
        """Qb must come after Qe; Qm must come last."""
        flat = [nid for batch in built_graph.execution_order for nid in batch]
        qe_idx = flat.index("Qe")
        qb_idx = flat.index("Qb")
        qm_idx = flat.index("Qm")
        assert qe_idx < qb_idx < qm_idx, f"Order violation: Qe@{qe_idx}, Qb@{qb_idx}, Qm@{qm_idx}"


# ── Execution ──

class TestExecution:
    def test_full_execution_matches_document(self, built_graph: FormulaGraph):
        """Verify results match the values from the real 给排水计算书."""
        results = built_graph.execute()

        # Document values: Qe=292.2, Qw=20, Qb=73(Qe/(N-1)≈292.2/4=73.05→73),
        # Qm=366 (N=5 case from document)
        qe = results["Qe"]["Qe"]
        qw = results["Qw"]["Qw"]
        qb = results["Qb"]["Qb"]
        qm = results["Qm"]["Qm"]

        assert qe == pytest.approx(292.2, abs=0.1), f"Qe={qe}, expected 292.2"
        assert qw == pytest.approx(20.0, abs=0.1), f"Qw={qw}, expected 20"
        assert qb == pytest.approx(73.05, abs=0.1), f"Qb={qb}, expected ~73"
        assert qm == pytest.approx(385.25, abs=0.2), f"Qm={qm}, expected ~385.2 (Qe+Qw+Qb)"

    def test_global_params_after_execution(self, built_graph: FormulaGraph):
        built_graph.execute()
        params = built_graph.get_all_params()

        # User inputs
        assert params["Q"] == 20000
        assert params["delta_t"] == 10
        assert params["KZF"] == 0.001461

        # Computed outputs (stored as formula_id.output_name)
        assert params["Qe.Qe"] == pytest.approx(292.2, abs=0.1)
        assert params["Qw.Qw"] == pytest.approx(20.0, abs=0.1)
        assert params["Qb.Qb"] == pytest.approx(73.05, abs=0.1)
        assert params["Qm.Qm"] == pytest.approx(385.25, abs=0.2)

    def test_idempotent_execution(self, built_graph: FormulaGraph):
        """Second execution without changes should produce same results."""
        r1 = built_graph.execute()
        r2 = built_graph.execute()
        assert r1 == r2


# ── Parameter change & recalculation ──

class TestParamChange:
    def test_update_param_triggers_full_recalc(self, built_graph: FormulaGraph):
        """Changing Q from 20000→25000 should recalculate all formulas."""
        built_graph.execute()

        affected = built_graph.update_param("Q", 25000)
        assert len(affected) == 4, f"Expected all 4 formulas affected, got {len(affected)}: {affected}"

    def test_update_param_recalc_values(self, built_graph: FormulaGraph):
        """Verify new values after Q change."""
        built_graph.execute()

        built_graph.update_param("Q", 25000)
        results = built_graph.execute()

        # Qe = Q * KZF * delta_t = 25000 * 0.001461 * 10 = 365.25
        assert results["Qe"]["Qe"] == pytest.approx(365.25, abs=0.1)
        # Qw = Q * 0.001 = 25000 * 0.001 = 25
        assert results["Qw"]["Qw"] == pytest.approx(25.0, abs=0.1)
        # Qb = Qe / (N-1) = 365.25 / 4 = 91.31
        assert results["Qb"]["Qb"] == pytest.approx(91.31, abs=0.1)
        # Qm = Qe + Qw + Qb = 365.25 + 25 + 91.31 = 481.56
        assert results["Qm"]["Qm"] == pytest.approx(481.56, abs=0.2)

    def test_change_summary(self, built_graph: FormulaGraph):
        """Change summary correctly reports old→new transitions."""
        built_graph.execute()
        built_graph.update_param("Q", 25000)
        built_graph.execute()

        summary = built_graph.last_change_summary()
        assert "Qe.Qe" in summary
        assert "Qw.Qw" in summary
        assert "Qb.Qb" in summary
        assert "Qm.Qm" in summary
        # Check format: "old → new"
        assert "→" in summary["Qe.Qe"]

    def test_recalc_only_affected(self, built_graph: FormulaGraph):
        """When only N changes, Qe and Qw should stay the same (they don't depend on N)."""
        built_graph.execute()

        # Change N from 5 to 3 — only Qb and Qm should change
        built_graph.update_param("N", 3)
        results = built_graph.execute()

        # Qe and Qw unchanged
        assert results["Qe"]["Qe"] == pytest.approx(292.2, abs=0.1)
        assert results["Qw"]["Qw"] == pytest.approx(20.0, abs=0.1)
        # Qb = Qe / (N-1) = 292.2 / 2 = 146.1
        assert results["Qb"]["Qb"] == pytest.approx(146.1, abs=0.1)
        # Qm = 292.2 + 20 + 146.1 = 458.3
        assert results["Qm"]["Qm"] == pytest.approx(458.3, abs=0.2)


# ── Edge cases ──

class TestEdgeCases:
    def test_circular_dependency_detection(self):
        """A → B → A should raise ValueError."""
        a = FormulaNode("A", "formula A", expression="x", inputs={}, outputs={"a": ""})
        b = FormulaNode(
            "B", "formula B", expression="a", inputs={"a": ParamSource.from_formula("A", "a")}, outputs={"b": ""},
        )
        # Overwrite A to depend on B
        a.inputs = {"b": ParamSource.from_formula("B", "b")}

        graph = FormulaGraph()
        graph.add_formulas([a, b])
        with pytest.raises(ValueError, match="循环依赖"):
            graph.build()

    def test_empty_graph(self):
        graph = FormulaGraph()
        graph.build()
        assert graph.execute() == {}
        assert graph.execution_order == []

    def test_single_formula(self):
        node = FormulaNode("x", "lonely", expression="a + b",
                           inputs={"a": ParamSource.user(1), "b": ParamSource.user(2)},
                           outputs={"x": ""})
        graph = FormulaGraph()
        graph.add_formula(node)
        graph.build()

        assert graph.execution_order == [["x"]]
        assert graph.execute() == {"x": {"x": 3.0}}

    def test_math_functions_in_expression(self):
        node = FormulaNode("math_test", "math", expression="sqrt(pow(a, 2) + pow(b, 2))",
                           inputs={"a": ParamSource.user(3), "b": ParamSource.user(4)},
                           outputs={"c": ""})
        graph = FormulaGraph()
        graph.add_formula(node)
        graph.build()
        assert graph.execute()["math_test"]["c"] == pytest.approx(5.0)

    def test_lookup_params(self):
        """Verify lookup_table values are treated as user inputs (not recomputed)."""
        node = FormulaNode("lk", "lookup", expression="KZF * x",
                           inputs={"KZF": ParamSource.lookup(0.001461), "x": ParamSource.user(10)},
                           outputs={"y": ""})
        graph = FormulaGraph()
        graph.add_formula(node)
        graph.build()
        assert graph.execute()["lk"]["y"] == pytest.approx(0.01461)

    def test_namespace_log_exp(self):
        """对数指数函数：log, log10, exp"""
        node = FormulaNode("test", "test", expression="log(E) + log10(100) + exp(0)",
                           inputs={"E": ParamSource.user(math.e)},
                           outputs={"r": ""})
        graph = FormulaGraph()
        graph.add_formula(node)
        graph.build()
        # log(e)=1, log10(100)=2, exp(0)=1 → 1+2+1=4
        assert graph.execute()["test"]["r"] == pytest.approx(4.0)

    def test_namespace_trig(self):
        """三角函数 sin/cos/tan"""
        node = FormulaNode("test", "test", expression="sin(pi/6) + cos(0)",
                           outputs={"r": ""})
        graph = FormulaGraph()
        graph.add_formula(node)
        graph.build()
        # sin(π/6)=0.5, cos(0)=1 → 1.5
        assert graph.execute()["test"]["r"] == pytest.approx(1.5)

    def test_namespace_degrees_radians(self):
        """角度弧度转换：radians + sin 配合使用"""
        node = FormulaNode("test", "test", expression="sin(radians(30))",
                           outputs={"r": ""})
        graph = FormulaGraph()
        graph.add_formula(node)
        graph.build()
        # sin(30°) = 0.5
        assert graph.execute()["test"]["r"] == pytest.approx(0.5)

    def test_namespace_hyperbolic(self):
        """双曲函数 sinh/cosh"""
        node = FormulaNode("test", "test", expression="sinh(0) + cosh(0)",
                           outputs={"r": ""})
        graph = FormulaGraph()
        graph.add_formula(node)
        graph.build()
        # sinh(0)=0, cosh(0)=1 → 1
        assert graph.execute()["test"]["r"] == pytest.approx(1.0)

    def test_namespace_atan2(self):
        """atan2 四象限反正切（工程坐标转换常用）"""
        node = FormulaNode("test", "test", expression="degrees(atan2(1, 1))",
                           outputs={"r": ""})
        graph = FormulaGraph()
        graph.add_formula(node)
        graph.build()
        # atan2(1,1)=π/4=45°
        assert graph.execute()["test"]["r"] == pytest.approx(45.0)


# ── Cross-formula group test (verifies independent groups run in parallel) ──

class TestParallelGroups:
    def test_two_independent_chains(self):
        """Chain A: a1→a2. Chain B: b1→b2. No cross-deps.

        Should produce: batch0={a1,b1}, batch1={a2,b2}.
        """
        a1 = FormulaNode("a1", "a1", expression="x", inputs={"x": ParamSource.user(1)}, outputs={"a1": ""})
        a2 = FormulaNode("a2", "a2", expression="a1 + 1",
                         inputs={"a1": ParamSource.from_formula("a1", "a1")}, outputs={"a2": ""})
        b1 = FormulaNode("b1", "b1", expression="y", inputs={"y": ParamSource.user(2)}, outputs={"b1": ""})
        b2 = FormulaNode("b2", "b2", expression="b1 + 1",
                         inputs={"b1": ParamSource.from_formula("b1", "b1")}, outputs={"b2": ""})

        graph = FormulaGraph()
        graph.add_formulas([a1, a2, b1, b2])
        graph.build()

        order = graph.execution_order
        assert len(order) == 2
        assert set(order[0]) == {"a1", "b1"}
        assert set(order[1]) == {"a2", "b2"}


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
