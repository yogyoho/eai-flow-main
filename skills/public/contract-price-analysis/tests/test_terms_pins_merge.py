"""cluster 相位 pins 装载纯函数（cpa v3 术语, spec 2026-10-14 §2.3）。

merge_pins(terms, legacy): 启用术语优先,legacy config.json merge_pins 过渡兼容;
归一化 canonical 撞车时 legacy 条目丢弃（aliases 已被术语覆盖的先验不再重复喂引擎）。
"""

from scripts.cli import _merge_pins


def test_terms_win_and_legacy_dedupes():
    terms = [
        {"name": "锚杆", "aliases": ["锚杆Φ22", "树脂锚杆"]},
        {"name": "钢绞线", "aliases": ["矿用钢绞线"]},
    ]
    legacy = [
        {"name": "锚杆", "aliases": ["玻璃钢锚杆"]},  # 与术语 canonical 撞车 → 丢
        {"name": "U型卡", "aliases": ["卡缆"]},  # 新 → 保留
    ]
    out = _merge_pins(terms, legacy)
    assert out[0] == {"name": "锚杆", "aliases": ["锚杆Φ22", "树脂锚杆"]}
    assert out[1] == {"name": "钢绞线", "aliases": ["矿用钢绞线"]}
    assert out[2] == {"name": "U型卡", "aliases": ["卡缆"]}
    assert len(out) == 3


def test_legacy_alias_only_collision_dropped():
    # legacy 条目 canonical 是空但别名撞术语 canonical → 也算撞车（去空白归一化比对全体名）
    terms = [{"name": "锚杆", "aliases": []}]
    legacy = [{"name": "锚  杆", "aliases": ["x"]}]  # 归一化后 == 锚杆
    assert _merge_pins(terms, legacy) == terms


def test_empty_terms_passes_legacy_through():
    legacy = [{"name": "U型卡", "aliases": ["卡缆"]}]
    assert _merge_pins([], legacy) == legacy


def test_disabled_terms_not_imported_here():
    # 过滤 enabled 是 _load_terms_pins 的 SQL 职责;纯函数只管合并——文档性断言
    assert _merge_pins([], []) == []


class TestApplyMergePinsSpecAware:
    """2026-10-22 螺纹钢 26 规格错簇修复: pin 并「名称变体」不并「规格家族」。

    走 cluster_items 全链路(术语 pin + 规格 AND 门同开,即生产配置)。"""

    def _cluster(self, samples, pins):
        from scripts.clustering.engine import cluster_items

        return cluster_items(
            samples, eps=0.6, min_samples=1, use_spec=True, use_category=False, merge_pins=pins
        )

    def test_pin_never_merges_across_specs(self):
        # 术语「螺纹钢」命中剥规格身份,但 10mm/12mm 不得被 pin 并回
        samples = [("螺纹钢 HRB400 10mm", {}), ("螺纹钢 HRB400 12mm", {}), ("螺纹钢 HRB400 10mm", {})]
        result = self._cluster(samples, [{"name": "螺纹钢", "aliases": ["螺纹钢 筋"]}])
        labels = result.labels
        assert labels[0] == labels[2] != labels[1]  # 同规格并,异规格分

    def test_pin_merges_name_variants_same_spec(self):
        # 名称变体(OCR 拆字)+同规格 → 并
        samples = [("螺纹钢 HRB400E 10mm", {}), ("螺纹钢 筋 HRB400E 10mm", {})]
        result = self._cluster(samples, [{"name": "螺纹钢", "aliases": ["螺纹钢 筋"]}])
        assert result.labels[0] == result.labels[1] != -1

    def test_pin_empty_spec_only_merges_empty(self):
        # ∅ 规格行只与 ∅ 并,不得混入有规格簇
        samples = [("螺纹钢", {}), ("螺纹钢", {}), ("螺纹钢 HRB400 10mm", {})]
        result = self._cluster(samples, [{"name": "螺纹钢", "aliases": []}])
        assert result.labels[0] == result.labels[1] != result.labels[2]

    def test_legacy_spec_in_name_pin_matches_full_identity(self):
        # 手动合并捕获的带规格 pin(规格在名内)走全名身份,只并同规格
        samples = [
            ("热镀锌无缝钢管 DN32", {}),
            ("热镀锌无缝钢管 DN40", {}),
            ("热镀锌无缝钢管 DN32", {}),
        ]
        result = self._cluster(
            samples, [{"name": "热镀锌无缝钢管 DN32", "aliases": ["热镀锌无缝钢管 DN40"]}]
        )
        # pin 声明了两个别名,但规格不同 → 各自独立(DN32×2 并)
        assert result.labels[0] == result.labels[2] != result.labels[1]

    def test_pin_alias_family_same_spec_merges(self):
        # 术语别名家族(热轧光圆钢筋/盘圆)同规格并、异规格分
        samples = [
            ("热轧光圆钢筋 HPB300 6mm", {}),
            ("盘圆 HPB300 6mm", {}),
            ("热轧光圆钢筋 HPB300 8mm", {}),
        ]
        result = self._cluster(samples, [{"name": "热轧光圆钢筋", "aliases": ["盘圆"]}])
        assert result.labels[0] == result.labels[1] != result.labels[2]


class TestGroupNamingByGates:
    """2026-10-22 用户规则: 分组名称按聚类维度组合——规格门开→名+规格;
    分类门也开→名+规格+分类;都不开→纯名。规格/分类取簇内首个非空。"""

    def _group(self, use_spec, use_category, items):
        from types import SimpleNamespace

        from scripts.cli import _build_groups_db

        result = SimpleNamespace(labels=[0] * len(items), representatives={})
        rows = [
            {
                "goods_name": it[0],
                "spec_model": it[1],
                "category": it[2],
                "unit_price": None,
                "validation_status": "ok",
                "document_id": None,
                "document_name": None,
            }
            for it in items
        ]
        return _build_groups_db(result, rows, use_spec=use_spec, use_category=use_category)[0]["name"]

    def test_name_only_when_gates_off(self):
        assert self._group(False, False, [("螺纹钢", "HRB400 10mm", "建筑工程")]) == "螺纹钢"

    def test_name_plus_spec(self):
        assert self._group(True, False, [("螺纹钢", "HRB400 10mm", "建筑工程")]) == "螺纹钢 HRB400 10mm"

    def test_name_plus_spec_plus_category(self):
        assert (
            self._group(True, True, [("螺纹钢", "HRB400 10mm", "建筑工程")])
            == "螺纹钢 HRB400 10mm 建筑工程"
        )

    def test_spec_takes_first_nonempty_in_cluster(self):
        # 簇内 ∅ 行中性,命名取首个非空规格
        assert (
            self._group(True, False, [("螺纹钢", None, None), ("螺纹钢 筋", "HRB400E 12mm", None)])
            == "螺纹钢 HRB400E 12mm"
        )

    def test_category_only_gate(self):
        assert self._group(False, True, [("钢材", "", "安装工程")]) == "钢材 安装工程"
