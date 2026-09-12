"""outline_merge 单测: 大纲候选校验(fail-closed)/精准替换/幂等/重签/消费端。"""

import json
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "skills" / "public" / "bid-proposal-overall" / "scripts"
if str(SCRIPTS_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SCRIPTS_DIR))

import outline_merge  # noqa: E402
import state_guard  # noqa: E402


def _node(node_id, volume, path, slot="group", linked=None, origin=None):
    n = {
        "node_id": node_id,
        "volume": volume,
        "path": path,
        "slot_type": slot,
        "required_format": {"desc": "d", "table_spec": None, "template_text": None},
        "linked_clause_ids": linked or [],
    }
    if origin:
        n["origin"] = origin
    return n


def _clause(clause_id, category="technical"):
    return {
        "clause_id": clause_id,
        "category": category,
        "response_status": "unassigned",  # build_output.load_clauses 逐条硬校验此枚举(L254)——缺失即 rc=1
        "superseded_by": None,  # _is_active 口径: superseded_by is None and not voided
        "voided": False,
        "source_ref": {"anchor": "a", "quote": "q"},
        "class": "mandatory",
        "response_skeleton": {"desc": "s", "evidence_ref": None},
    }


def _make_state(tmp_path, structure, clauses):
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "clauses.json").write_text(json.dumps(clauses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (state / "structure.json").write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (state / "entities_whitelist.json").write_text(json.dumps({"entities": []}, ensure_ascii=False) + "\n", encoding="utf-8")
    state_guard.sign_state_files(state, ["clauses.json", "structure.json", "entities_whitelist.json"])
    return state


MIRROR_STRUCTURE = [
    _node("S-001", "commercial", "投标文件格式/一、投标函"),
    _node("S-002", "technical", "技术要求/3.2 课堂行为识别", slot="text", linked=["ZB-T-001"]),
]
MIRROR_CLAUSES = [_clause("ZB-T-001"), _clause("ZB-T-002"), _clause("ZB-C-001", category="commercial")]


def _candidate(chapters, managed=None, confirmed=True):
    return {"source_pack": "it-full", "confirmed": confirmed, "chapters": chapters, "managed_node_ids": managed or []}


def _write_candidate(tmp_path, cand):
    p = tmp_path / "tech_outline.candidates.json"
    p.write_text(json.dumps(cand, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


GOOD = [{"no": 1, "title": "项目总体理解", "clause_ids": ["ZB-T-002"], "notes": None}]


def _run_merge(state, cand_path, confirm=True):
    argv = ["--state-dir", str(state), "--candidates", str(cand_path)]
    if confirm:
        argv.append("--confirm-outline")
    return outline_merge.main(argv)


class TestCandidateValidation:
    def test_missing_confirm_flag_exit_1(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD, confirmed=False))
        assert _run_merge(state, cand, confirm=False) == 1, "缺 --confirm-outline 拒绝执行(确认纪律)"

    def test_unconfirmed_candidate_rejected(self, tmp_path, capsys):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD, confirmed=False))
        assert _run_merge(state, cand) == 1, "confirmed 非 true, 即使带 --confirm-outline 也拒绝(双重确认门)"
        assert "confirmed" in capsys.readouterr().err

    def test_empty_outline_exit_1(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([]))
        assert _run_merge(state, cand) == 1, "空大纲无意义, 拒绝"

    def test_clause_not_found_rejected(self, tmp_path, capsys):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "x", "clause_ids": ["GHOST-1"], "notes": None}]))
        assert _run_merge(state, cand) == 1
        assert "not_found" in json.dumps(json.loads((tmp_path / "tech_outline.candidates.json").read_text(encoding="utf-8"))) or True
        assert "not_found" in capsys.readouterr().err
        # 拒绝明细断言: 校验失败不落盘 structure
        assert json.loads((state / "structure.json").read_text(encoding="utf-8")) == MIRROR_STRUCTURE, "校验失败零落盘"

    def test_mirror_anchored_clause_rejected(self, tmp_path, capsys):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "x", "clause_ids": ["ZB-T-001"], "notes": None}]))
        assert _run_merge(state, cand) == 1, "mirror 已挂条款被大纲抢挂 → mirror_anchored 拒绝"
        assert "mirror_anchored" in capsys.readouterr().err
        assert json.loads((state / "structure.json").read_text(encoding="utf-8")) == MIRROR_STRUCTURE

    def test_wrong_category_rejected(self, tmp_path, capsys):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "x", "clause_ids": ["ZB-C-001"], "notes": None}]))
        assert _run_merge(state, cand) == 1, "commercial 条款进技术大纲 → wrong_category 拒绝"
        assert "wrong_category" in capsys.readouterr().err

    def test_not_live_rejected(self, tmp_path, capsys):
        dead = _clause("ZB-T-009")
        dead["superseded_by"] = "ZB-T-100"  # _is_active 真实口径: superseded_by 非 None 即非活(字段 status 不存在)
        clauses = MIRROR_CLAUSES + [dead]
        state = _make_state(tmp_path, MIRROR_STRUCTURE, clauses)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "x", "clause_ids": ["ZB-T-009"], "notes": None}]))
        assert _run_merge(state, cand) == 1, "非活条款 → not_live 拒绝"
        assert "not_live" in capsys.readouterr().err

    def test_duplicate_chapter_rejected(self, tmp_path, capsys):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        dup = [
            {"no": 1, "title": "总体方案", "clause_ids": ["ZB-T-002"], "notes": None},
            {"no": 2, "title": "总体方案", "clause_ids": ["ZB-T-002"], "notes": None},
        ]
        cand = _write_candidate(tmp_path, _candidate(dup))
        assert _run_merge(state, cand) == 1, "大纲内章名重复 → duplicate_chapter 拒绝"
        assert "duplicate_chapter" in capsys.readouterr().err

    def test_chapter_title_conflicts_mirror_chapter_rejected(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "技术要求", "clause_ids": ["ZB-T-002"], "notes": None}]))
        assert _run_merge(state, cand) == 1, "自拟章首段与 mirror 章首段同名 → chapter_name_conflict 拒绝(防同章组合并歧义)"

    def test_bool_no_rejected(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": True, "title": "x", "clause_ids": ["ZB-T-002"], "notes": None}]))
        assert _run_merge(state, cand) == 1, "bool 是 int 子类——no=true 必须拒绝"

    def test_non_dict_chapter_rejected(self, tmp_path, capsys):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(["不是对象的章"]))
        assert _run_merge(state, cand) == 1, "chapters 内非对象元素 → problem 化, 不 crash"
        assert "非对象" in capsys.readouterr().err

    def test_non_str_clause_id_rejected(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "x", "clause_ids": [{"k": "v"}], "notes": None}]))
        assert _run_merge(state, cand) == 1, "clause_ids 内嵌对象(unhashable)必须 problem 化, 不得 crash"

    def test_candidates_as_list_rejected(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        p = tmp_path / "tech_outline.candidates.json"
        p.write_text(json.dumps([{"no": 1, "title": "x", "clause_ids": []}]), encoding="utf-8")
        assert _run_merge(state, p) == 1, "候选文件为 JSON 数组(应为对象) → 形态拒绝"

    def test_signed_dict_structure_rejected(self, tmp_path, capsys):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        (state / "structure.json").write_text("{}", encoding="utf-8")
        state_guard.sign_state_files(state, ["structure.json"])  # 篡改后重签 = 合法签名下的坏形状, 仍须拒绝
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        assert _run_merge(state, cand) == 1, "structure.json 为对象(应为数组) → 形态拒绝"
        assert json.loads((state / "structure.json").read_text(encoding="utf-8")) == {}, "校验拒绝零落盘(structure 未被改写)"
        assert "structure.json" in capsys.readouterr().err

    def test_corrupt_candidate_exit_1(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        p = tmp_path / "tech_outline.candidates.json"
        p.write_text("{not json", encoding="utf-8")
        assert _run_merge(state, p) == 1

    def test_duplicate_clause_across_chapters_rejected(self, tmp_path, capsys):
        dup = [
            {"no": 1, "title": "章甲", "clause_ids": ["ZB-T-002"], "notes": None},
            {"no": 2, "title": "章乙", "clause_ids": ["ZB-T-002"], "notes": None},
        ]
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(dup))
        assert _run_merge(state, cand) == 1, "两章抢同一条款 → duplicate_clause 拒绝(双锚定=响应双渲染)"
        assert "duplicate_clause" in capsys.readouterr().err
        assert json.loads((state / "structure.json").read_text(encoding="utf-8")) == MIRROR_STRUCTURE, "拒绝零落盘"


class TestMergeSemantics:
    def _assert_signed(self, state):
        assert state_guard.verify_state_files(state) == [], "merge 后签名必须有效"

    def test_merge_creates_self_created_chapters(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        assert _run_merge(state, cand) == 0
        structure = json.loads((state / "structure.json").read_text(encoding="utf-8"))
        mine = [n for n in structure if n.get("origin") == "self_created" and "大纲自拟章" in n["required_format"]["desc"]]
        assert len(mine) == 1, "一个大纲章 → 一个 group 节点"
        node = [n for n in structure if n["node_id"] != "S-001" and n["node_id"] != "S-002" and n.get("origin") == "self_created"][0]
        assert node["volume"] == "technical" and node["slot_type"] == "group"
        assert node["path"] == "01 项目总体理解", "单段 path: 首段=章键, 前导数字供 _allocate_section_numbers 领号"
        assert node["linked_clause_ids"] == ["ZB-T-002"]
        assert node["required_format"]["desc"], "required_format.desc 记大纲来源(pack slug/自由拟)"
        self._assert_signed(state)

    def test_managed_replacement_is_precise(self, tmp_path):
        structure = MIRROR_STRUCTURE + [_node("S-090", "technical", "99 旧自拟章", linked=["ZB-T-002"], origin="self_created")]
        state = _make_state(tmp_path, structure, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD, managed=["S-090"]))
        assert _run_merge(state, cand) == 0
        out = json.loads((state / "structure.json").read_text(encoding="utf-8"))
        ids = {n["node_id"] for n in out}
        assert "S-090" not in ids, "旧 managed 节点被替换删除"
        assert any(n.get("origin") == "self_created" and n["path"] == "01 项目总体理解" for n in out), "新章落地"
        assert MIRROR_STRUCTURE[1] in out, "mirror 节点零触碰"
        updated = json.loads((tmp_path / "tech_outline.candidates.json").read_text(encoding="utf-8"))
        assert updated["managed_node_ids"] and updated["managed_node_ids"] != ["S-090"], "managed_node_ids 回写候选文件"

    def test_idempotent_rerun_byte_identical(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        assert _run_merge(state, cand) == 0
        first = (state / "structure.json").read_bytes()
        first_cand = cand.read_bytes()
        assert _run_merge(state, cand) == 0
        assert (state / "structure.json").read_bytes() == first, "同候选重跑 structure 字节一致"
        assert cand.read_bytes() == first_cand, "候选回写幂等"

    def test_responses_fallback_node_never_managed(self, tmp_path):
        fb = _node("S-095", "technical", "其他技术要求响应", linked=["ZB-T-002"], origin="self_created")
        structure = MIRROR_STRUCTURE + [fb]
        state = _make_state(tmp_path, structure, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD, managed=[]))
        assert _run_merge(state, cand) == 0
        out = json.loads((state / "structure.json").read_text(encoding="utf-8"))
        assert fb in out, "responses 兜底自创节点不受大纲替换影响(不在 managed 集合)"
        updated = json.loads((tmp_path / "tech_outline.candidates.json").read_text(encoding="utf-8"))
        assert "S-095" not in updated["managed_node_ids"]

    def test_summary_reports_remaining_unanchored(self, tmp_path, capsys):
        clauses = MIRROR_CLAUSES + [_clause("ZB-T-003")]
        state = _make_state(tmp_path, MIRROR_STRUCTURE, clauses)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        assert _run_merge(state, cand) == 0
        summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert summary["remaining_unanchored"] == 1, "merge 后仍无锚点的活技术条款计数进摘要"

    def test_managed_blind_delete_gates(self, tmp_path):
        # managed 指向 mirror 节点 → 拒绝(mirror 零触碰铁律)
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD, managed=["S-002"]))
        assert _run_merge(state, cand) == 1, "managed 指向 mirror 节点 → not_self_created 拒绝"
        # managed 指向不存在的 id → 拒绝
        cand = _write_candidate(tmp_path, _candidate(GOOD, managed=["S-999"]))
        assert _run_merge(state, cand) == 1, "managed unknown id 拒绝"
        # managed 非 list → 拒绝
        cand = _write_candidate(tmp_path, {"source_pack": None, "confirmed": True, "chapters": GOOD, "managed_node_ids": "S-001"})
        assert _run_merge(state, cand) == 1

    def test_managed_external_anchors_rejected(self, tmp_path):
        """旧 managed 节点含 responses merge 外加锚点(不在本轮大纲分配内) → 拒绝删除(防静默丢锚)。"""
        structure = MIRROR_STRUCTURE + [_node("S-090", "technical", "99 旧自拟章", linked=["ZB-T-002", "ZB-T-002X"], origin="self_created")]
        clauses = MIRROR_CLAUSES + [_clause("ZB-T-002X")]
        state = _make_state(tmp_path, structure, clauses)
        cand = _write_candidate(tmp_path, _candidate(GOOD, managed=["S-090"]))
        assert _run_merge(state, cand) == 1, "external_anchors 拒绝——先重跑 responses merge 或确认弃锚"
        assert json.loads((state / "structure.json").read_text(encoding="utf-8")) == structure, "拒绝即零落盘"

    def test_self_created_path_conflict_rejected(self, tmp_path):
        """候选章 path 与既有 responses 兜底自创节点同 path → 拒绝(防双渲染/接管落空)。"""
        fb = _node("S-095", "technical", "01 项目总体理解", linked=["ZB-T-002"], origin="self_created")
        structure = MIRROR_STRUCTURE + [fb]
        state = _make_state(tmp_path, structure, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        assert _run_merge(state, cand) == 1, "self_created_path_conflict 拒绝"

    def test_sign_failure_rolls_back_bytes(self, tmp_path, monkeypatch):
        """重签失败 → 回滚旧字节并恢复签名, exit 1, structure.json 字节不变(spec §6)。"""
        # monkeypatch 必须先于 _make_state 注册: flaky call 1=首签(放行), call 2=merge 重签(炸), call 3=回滚重签(放行)
        real_sign = state_guard.sign_state_files
        calls = {"n": 0}

        def flaky_sign(sd, names):
            calls["n"] += 1
            if calls["n"] == 2:  # 首签(_make_state)放行; merge 的重签炸; 回滚对旧内容的重签(call 3)放行
                raise OSError("模拟签名通道故障")
            return real_sign(sd, names)

        monkeypatch.setattr(state_guard, "sign_state_files", flaky_sign)
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        old_bytes = (state / "structure.json").read_bytes()
        assert _run_merge(state, cand) == 1
        assert (state / "structure.json").read_bytes() == old_bytes, "重签失败回滚——structure.json 字节不变"
        assert state_guard.verify_state_files(state) == [], "回滚后签名恢复(对旧内容重签)"

    def test_candidates_writeback_failure_reports_recovery(self, tmp_path, monkeypatch, capsys):
        """候选回写失败(structure 已更新+签名)→ exit 1, stderr 携带真实恢复路径(新 managed ids)——
        重跑会被 self_created_path_conflict 拒死, 恢复提示不得指向死路。"""
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        real_replace = outline_merge.os.replace

        def flaky_replace(src, dst):
            if str(dst).endswith("tech_outline.candidates.json"):
                raise OSError("模拟候选回写通道故障")
            return real_replace(src, dst)

        monkeypatch.setattr(outline_merge.os, "replace", flaky_replace)
        assert _run_merge(state, cand) == 1
        err = capsys.readouterr().err
        assert "S-003" in err, "恢复提示必须携带新 managed 节点 id(重跑路径已死, 手动回填是唯一出口)"
        assert "managed_node_ids" in err
        out = json.loads((state / "structure.json").read_text(encoding="utf-8"))
        assert any(n["node_id"] == "S-003" for n in out), "structure.json 已更新(半完成态如实可见)"
        assert state_guard.verify_state_files(state) == [], "structure.json 已签名"

    def test_two_chapters_get_sequential_node_ids(self, tmp_path):
        chapters = [
            {"no": 1, "title": "项目总体理解", "clause_ids": ["ZB-T-002"], "notes": None},
            {"no": 2, "title": "网络方案", "clause_ids": ["ZB-T-003"], "notes": None},
        ]
        clauses = MIRROR_CLAUSES + [_clause("ZB-T-003")]
        state = _make_state(tmp_path, MIRROR_STRUCTURE, clauses)
        cand = _write_candidate(tmp_path, _candidate(chapters))
        assert _run_merge(state, cand) == 0
        out = json.loads((state / "structure.json").read_text(encoding="utf-8"))
        new_ids = [n["node_id"] for n in out if n.get("origin") == "self_created"]
        assert new_ids == ["S-003", "S-004"], "逐章顺序取号——build_outline_nodes 漏掉 +nodes 会双 S-003"
        updated = json.loads((tmp_path / "tech_outline.candidates.json").read_text(encoding="utf-8"))
        assert updated["managed_node_ids"] == ["S-003", "S-004"], "回写候选含全部新节点 id"
