"""coal-eia-report v2 交付协议测试（T7 文件⑦）。

三块（D6 交付双通道的机器面 + D12 章树供给）：
  ① mapping.py bind/check（D6 章树绑定协议 × D12 同构断言）：一致 rc=0 落文件；
     树/标题差异 rc=2 不落盘（禁静默错写）；check 双射复核 + 陈旧绑定检出 + --stage 全量复核
  ② seed_gen.py gen+selfcheck（D12：stage→KF 模板 seed 单向生成）：树守恒（Σ节地板=Σ章地板）、
     平台消费方契约断言（TemplateSection 字段集/两级深度/min_word_count 正整数）
  ③ delivered 断点续交幂等（D6 项目路径）：分波回执、中断后续波、幂等重发、拒非 VERIFIED

设计依据: docs/designs/coal-eia-report-v2.md D6/D9/D12 + SKILL.md「交付双通道」。
运行: cd backend && PYTHONPATH=. uv run pytest tests/test_coal_eia_delivery_protocol.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "coal-eia-report"
SCRIPTS = SKILL / "scripts"  # conftest 同名脚本隔离锚
STAGE = SKILL / "references" / "stages" / "planning_eia.json"

SENT = "矿区总体规划与现行环境保护法律法规构成本节评价的依据与边界条件，评价时段与评价分区据此划定。"


def run(*args: object, expect=(0,)) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / str(args[0])), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-400:]}\n{r.stderr[:400]}"
    return r


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


def make_tree(stage: dict, seed: str = "t7-delivery") -> list[dict]:
    """stage 同构的 list_chapters 导出形状（扁平数组 DFS 序，chapter_id=确定性 uuid）。"""
    rows: list[dict] = []
    for cid in chapter_order(stage["chapters"]):
        ch = stage["chapters"][cid]
        rows.append({"chapter_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{seed}/{cid}")), "title": ch.get("title", cid), "level": 1, "status": "draft", "word_count_target": 0, "word_count_current": 0, "assigned_name": ch.get("title", cid)})
        for s in ch.get("sections", []):
            rows.append(
                {"chapter_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{seed}/{s['id']}")), "title": s.get("title", ""), "level": 2, "status": "draft", "word_count_target": 0, "word_count_current": 0, "assigned_name": s.get("title", "")}
            )
    return rows


# ── ① mapping.py bind/check ────────────────────────────────────────────────────


class TestMappingBindCheck:
    @pytest.fixture()
    def mws(self, tmp_path):
        stage = json.loads(STAGE.read_text(encoding="utf-8"))
        tree = tmp_path / "tree.json"
        tree.write_text(json.dumps(make_tree(stage), ensure_ascii=False, indent=1), encoding="utf-8")
        return SimpleNamespace(root=tmp_path, stage=stage, tree=tree, mapping=tmp_path / "state" / "mapping.json")

    def test_bind_consistent_writes_file(self, mws):
        r = run("mapping.py", "bind", "--tree", mws.tree, "--stage", STAGE, "--output", mws.mapping)
        assert "MAPPING_READY: 77 节已绑定" in r.stdout
        mapping = json.loads(mws.mapping.read_text(encoding="utf-8"))
        assert len(mapping) == 77  # 仅 level2 叶子（交付=节级，D9）
        stage_secs = {s["id"] for ch in mws.stage["chapters"].values() for s in ch.get("sections", [])}
        assert set(mapping) == stage_secs
        assert all(str(v).startswith("urn:uuid:") or len(v) == 36 for v in mapping.values())

    def test_bind_mismatch_refuses_to_write(self, mws):
        """rc=2 不一致不落盘（禁静默错写，D6）——树过期/被人工改动须升用户确认。"""
        rows = make_tree(mws.stage, seed="t7-delivery")
        rows[3]["title"] = "被人工改动的节题"  # 第一个 level2 行
        bad_tree = mws.root / "tree_bad.json"
        bad_tree.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        r = run("mapping.py", "bind", "--tree", bad_tree, "--stage", STAGE, "--output", mws.mapping, expect=(2,))
        assert r.returncode == 2 and "MAPPING_MISMATCH" in r.stdout and "标题不符" in r.stdout
        assert not mws.mapping.exists()  # 不落盘

    def test_bind_row_count_mismatch(self, mws):
        rows = make_tree(mws.stage, seed="t7-delivery")[:-1]  # 缺最后一节行
        bad_tree = mws.root / "tree_short.json"
        bad_tree.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        r = run("mapping.py", "bind", "--tree", bad_tree, "--stage", STAGE, "--output", mws.mapping, expect=(2,))
        assert "行数" in r.stdout

    def test_check_valid_binding_full_recheck(self, mws):
        run("mapping.py", "bind", "--tree", mws.tree, "--stage", STAGE, "--output", mws.mapping)
        r = run("mapping.py", "check", "--mapping", mws.mapping, "--tree", mws.tree, "--stage", STAGE)
        assert "MAPPING_OK: 77 节绑定" in r.stdout and "stage 全量复核一致" in r.stdout

    def test_check_detects_stale_uuid(self, mws):
        """树重建/重导入换 uuid → check 立刻暴露陈旧绑定（rc=2 绑定失效）。"""
        run("mapping.py", "bind", "--tree", mws.tree, "--stage", STAGE, "--output", mws.mapping)
        rows = make_tree(mws.stage, seed="rebuilt-tree")  # 全新 uuid 集
        new_tree = mws.root / "tree_rebuilt.json"
        new_tree.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        r = run("mapping.py", "check", "--mapping", mws.mapping, "--tree", new_tree, expect=(2,))
        assert "MAPPING_INVALID" in r.stdout and ("陈旧绑定" in r.stdout or "未绑定" in r.stdout)

    def test_check_shape_guards(self, mws):
        (mws.root / "empty.json").write_text("{}", encoding="utf-8")
        r = run("mapping.py", "check", "--mapping", mws.root / "empty.json", "--tree", mws.tree, expect=(1,))
        assert "非空平面字典" in r.stdout


# ── ② seed_gen.py gen + selfcheck ──────────────────────────────────────────────


class TestSeedGen:
    def test_gen_and_selfcheck_pass(self, tmp_path):
        """gen 落盘 + 自动装载冒烟 PASS（真模型不可寻址时按 schema 字段断言，不静默）。"""
        seed_out = tmp_path / "kf_seed_planning_eia.json"
        r = run("seed_gen.py", "gen", "--stage", STAGE, "--output", seed_out)
        assert "SEED_READY" in r.stdout and "SEED_SELFCHECK: PASS" in r.stdout
        assert "SEED_PYDANTIC: TemplateSection 真模型验证 PASS" in r.stdout or "SEED_PYDANTIC: SKIP" in r.stdout
        seed = json.loads(seed_out.read_text(encoding="utf-8"))
        assert seed["kind"] == "kf_template_seed"
        sections = seed["root_sections_json"]["sections"]
        assert len(sections) == 13
        n_secs = sum(len(s.get("children", [])) for s in sections)
        assert n_secs == 77
        totals = seed["metadata"]["totals"]
        assert totals["chapters"] == 13 and totals["sections"] == 77
        # 分摊守恒：Σ节地板 = Σ章地板（最大余数法零漂移）
        assert totals["floor_chars_total"] == sum(s["content_contract"]["min_word_count"] for s in sections)
        for s in sections:
            assert sum(c["content_contract"]["min_word_count"] for c in s["children"]) == s["content_contract"]["min_word_count"]
        # D12 边界：D3 三偏差不进 seed（scope_note 声明）；章=level1、节=level2
        assert "三偏差" in seed["metadata"]["scope_note"]
        assert all(s["level"] == 1 and c["level"] == 2 and not c.get("children") for s in sections for c in s["children"])

    def test_selfcheck_subcommand(self, tmp_path):
        seed_out = tmp_path / "seed.json"
        run("seed_gen.py", "gen", "--stage", STAGE, "--output", seed_out)
        r = run("seed_gen.py", "selfcheck", "--seed", seed_out)
        assert r.returncode == 0 and "SEED_SELFCHECK: PASS" in r.stdout

    def test_selfcheck_detects_broken_seed(self, tmp_path):
        """Σ节≠Σ章 的守恒破坏 → selfcheck FAIL rc=1（平台消费方契约是硬断言）。"""
        seed_out = tmp_path / "seed.json"
        run("seed_gen.py", "gen", "--stage", STAGE, "--output", seed_out)
        seed = json.loads(seed_out.read_text(encoding="utf-8"))
        seed["root_sections_json"]["sections"][0]["children"][0]["content_contract"]["min_word_count"] += 7
        broken = tmp_path / "seed_broken.json"
        broken.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
        r = run("seed_gen.py", "selfcheck", "--seed", broken, expect=(1,))
        assert "SEED_SELFCHECK: FAIL" in r.stdout and "守恒" in r.stdout


# ── ③ delivered 断点续交幂等 ───────────────────────────────────────────────────


class TestDeliveredResume:
    @pytest.fixture()
    def dws(self, tmp_path):
        """ch1 全节 VERIFIED 的工作区（交付起点=一致性 PASS 后的章门产物）。"""
        root = tmp_path / "ws"
        data, state = root / "data", root / "state"
        data.mkdir(parents=True)
        state.mkdir(parents=True)
        run("progress.py", "init", "--stage", STAGE, "--state-dir", state, "--data-dir", data)
        run("progress.py", "run-stage", "freeze", "--state-dir", state, expect=(0, 3))
        stage = json.loads(STAGE.read_text(encoding="utf-8"))
        sids = [s["id"] for s in stage["chapters"]["ch1"]["sections"]]
        run("progress.py", "mark", "--sections", ",".join(sids), "DRAFTED", "--state-dir", state)
        depth = root / "depth_ch1.json"
        depth.write_text(json.dumps({"chapters": {"ch1": {"floor_chars": 800}}}, ensure_ascii=False), encoding="utf-8")
        for i, s in enumerate(stage["chapters"]["ch1"]["sections"], 1):
            (state / "sections").mkdir(exist_ok=True)
            (state / "sections" / f"{s['id']}.md").write_text(f"### 1.{i} {s['title']}\n\n" + SENT * 4 + "\n", encoding="utf-8")
        run("progress.py", "mark", "ch1", "DRAFTED", "--state-dir", state)
        run("progress.py", "gate", "--state-dir", state, "--targets", depth)
        return SimpleNamespace(root=root, state=state, sids=sids)

    def _doc(self, state: Path) -> dict:
        return json.loads((state / "progress.json").read_text(encoding="utf-8"))

    def test_wave_receipt_fields(self, dws):
        r = run("progress.py", "delivered", "--sections", f"{dws.sids[0]},{dws.sids[1]}", "--wave", "1", "--state-dir", dws.state)
        assert "DELIVERED_BATCH: wave=1 fresh=2 idempotent=0" in r.stdout
        secs = {s["id"]: s for s in self._doc(dws.state)["chapters"]["ch1"]["sections"]}
        assert secs[dws.sids[0]]["delivered"] is True and secs[dws.sids[0]]["delivery_wave"] == 1
        assert secs[dws.sids[2]]["delivered"] is False  # 未波及节保持待交

    def test_idempotent_retransmit(self, dws):
        """write_chapter 全量覆盖语义下 delivered 幂等：重复回执 no-op 不重复计数。"""
        run("progress.py", "delivered", "--sections", dws.sids[0], "--wave", "1", "--state-dir", dws.state)
        r = run("progress.py", "delivered", "--sections", dws.sids[0], "--wave", "1", "--state-dir", dws.state)
        assert "fresh=0 idempotent=1" in r.stdout

    def test_refuse_non_verified(self, dws):
        r = run("progress.py", "delivered", "--sections", "ch2_S01", "--wave", "1", "--state-dir", dws.state, expect=(1,))
        assert "仅 VERIFIED 节可交付" in r.stderr

    def test_interrupt_then_resume_next_wave(self, dws):
        """断点续交：波 1 只交 2 节即中断 → 续交余下 9 节（波 2）→ 全章 delivered 清零欠账。"""
        run("progress.py", "delivered", "--sections", ",".join(dws.sids[:2]), "--wave", "1", "--state-dir", dws.state)
        r = run("progress.py", "delivered", "--sections", ",".join(dws.sids[2:]), "--wave", "2", "--state-dir", dws.state)
        assert "fresh=9" in r.stdout
        secs = {s["id"]: s for s in self._doc(dws.state)["chapters"]["ch1"]["sections"]}
        assert all(s["delivered"] is True for s in secs.values())
        assert {secs[sid]["delivery_wave"] for sid in dws.sids[:2]} == {1}
        assert {secs[sid]["delivery_wave"] for sid in dws.sids[2:]} == {2}
        r = run("progress.py", "status", "--state-dir", dws.state)
        assert "已交付 11" in r.stdout
