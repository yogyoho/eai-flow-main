"""B立项 M4 条目聚类单测(spec §5,2026-11-05):业绩富行归一闸 + clusters.py 确定性聚类三通道 + prompt/baseline。"""

from app.extensions.bid_review.engine.clusters import SIM_MERGE, SIM_SUSPECT, cluster_performance_entries
from app.extensions.bid_review.engine.extract import (
    FIELD_TYPE_CONTRACTS,
    build_performance_baseline,
    build_performance_prompt,
    normalize_performance_entries,
)


def _e(name, c="", amount=None, date=None, page=None):
    return {"name": name, "client": c, "amount": amount, "date": date, "page": page}


class TestContracts:
    def test_m4_paths_have_contracts(self):
        assert "bid.performance_entries" in FIELD_TYPE_CONTRACTS
        assert "bid.performance_groups" in FIELD_TYPE_CONTRACTS


class TestNormalizePerfEntries:
    def test_drops_no_name_and_clamps(self):
        rows = normalize_performance_entries(
            [
                {"name": " 某数据中心 ", "client": " 某集团 ", "amount": 1200, "date": " 2023-05-01 ", "page": 3},
                {"client": "无名"},  # 缺 name 丢行
                "junk",
                {"name": "A", "amount": True, "date": 5, "page": 0},  # 坏形→null
                {"name": "B", "amount": -1, "page": True},
            ]
        )
        assert len(rows) == 3
        assert rows[0] == {"name": " 某数据中心 ", "client": "某集团", "amount": 1200, "date": "2023-05-01", "page": 3}
        assert rows[1]["amount"] is None and rows[1]["date"] is None and rows[1]["page"] is None
        assert rows[2]["amount"] is None and rows[2]["page"] is None

    def test_non_list_returns_empty(self):
        assert normalize_performance_entries(None) == []
        assert normalize_performance_entries("junk") == []


class TestCluster:
    def test_exact_name_fast_path(self):
        groups = cluster_performance_entries([_e("某数据中心EPC", c="某集团"), _e("某数据中心EPC", c="其它单位")])
        assert len(groups) == 1
        assert groups[0]["ok"] is True and groups[0]["group_id"] == "G1"
        assert len(groups[0]["members"]) == 2

    def test_high_ratio_without_corroboration_never_merges(self):
        # ratio≈0.92 ≥0.80 但甲方/金额/日期全不同 → 不并(防同名不同项)
        groups = cluster_performance_entries([_e("某数据中心EPC工程总承包"), _e("某数据中心EPC项目总承包", c="另一集团", amount=1)])
        assert len(groups) == 2

    def test_similar_with_client_corroboration_merges_ok(self):
        groups = cluster_performance_entries([_e("某数据中心EPC工程总承包", c="某集团"), _e("某数据中心EPC项目总承包", c="某集团")])
        assert len(groups) == 1 and groups[0]["ok"] is True

    def test_amount_corroboration_merges(self):
        groups = cluster_performance_entries([_e("某数据中心EPC工程总承包", amount=995), _e("某数据中心EPC项目总承包", amount=995, c="x")])
        assert len(groups) == 1

    def test_suspect_band_merges_flagged_false(self):
        # 道路/管网 ratio≈0.778 ∈[SIM_SUSPECT, SIM_MERGE) + 佐证 → 并组 ok=false(UNKNOWN 人工,禁强行 PARTIAL)
        assert SIM_SUSPECT <= 0.7778 < SIM_MERGE
        groups = cluster_performance_entries([_e("某园区市政道路工程", c="某集团"), _e("某园区市政管网工程", c="某集团")])
        assert len(groups) == 1 and groups[0]["ok"] is False

    def test_suspect_band_without_corroboration_separate(self):
        groups = cluster_performance_entries([_e("某园区市政道路工程"), _e("某园区市政管网工程")])
        assert len(groups) == 2

    def test_below_suspect_band_separate_even_with_client(self):
        groups = cluster_performance_entries([_e("甲项目", c="某集团"), _e("乙工程", c="某集团")])
        assert len(groups) == 2

    def test_suspect_group_stays_suspect_on_confident_join(self):
        # 先疑似并组,后全等名加入 → 组保持 ok=false(有人工未决嫌疑不自动转正)
        groups = cluster_performance_entries([_e("某园区市政道路工程", c="某集团"), _e("某园区市政管网工程", c="某集团"), _e("某园区市政道路工程", c="某集团")])
        assert len(groups) == 1 and groups[0]["ok"] is False and len(groups[0]["members"]) == 3

    def test_singleton_and_empty(self):
        groups = cluster_performance_entries([_e("A")])
        assert groups == [{"group_id": "G1", "ok": True, "members": [_e("A")]}]
        assert cluster_performance_entries([]) == []
        assert cluster_performance_entries(None) == []


class TestPromptAndBaseline:
    def test_prompt_contains_contract_and_rules(self):
        prompt = build_performance_prompt([{"doc_id": "b.pdf", "role": "bid", "text": "x"}])
        assert "业绩条目定位器" in prompt
        assert "[[p." in prompt
        assert "禁止编造" in prompt
        assert "performance_entries" in prompt

    def test_baseline_unwraps_and_normalizes(self):
        def fake_fn(docs):
            return {"performance_entries": [{"name": " A ", "client": " B "}]}

        out = build_performance_baseline([{"doc_id": "b.pdf", "role": "bid", "text": "x"}], fake_fn)
        assert out == [{"name": " A ", "client": "B", "amount": None, "date": None, "page": None}]

    def test_baseline_bare_list_passthrough(self):
        assert build_performance_baseline([], lambda docs: [{"name": "X"}]) == [{"name": "X", "client": "", "amount": None, "date": None, "page": None}]

    def test_baseline_none_signal(self):
        assert build_performance_baseline([], lambda docs: None) == []
