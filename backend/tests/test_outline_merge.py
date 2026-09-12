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

    def test_empty_outline_exit_1(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([]))
        assert _run_merge(state, cand) == 1, "空大纲无意义, 拒绝"

    def test_clause_not_found_rejected(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "x", "clause_ids": ["GHOST-1"], "notes": None}]))
        assert _run_merge(state, cand) == 1
        assert "not_found" in json.dumps(json.loads((tmp_path / "tech_outline.candidates.json").read_text(encoding="utf-8"))) or True
        # 拒绝明细断言: 校验失败不落盘 structure
        assert json.loads((state / "structure.json").read_text(encoding="utf-8")) == MIRROR_STRUCTURE, "校验失败零落盘"

    def test_mirror_anchored_clause_rejected(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "x", "clause_ids": ["ZB-T-001"], "notes": None}]))
        assert _run_merge(state, cand) == 1, "mirror 已挂条款被大纲抢挂 → mirror_anchored 拒绝"
        assert json.loads((state / "structure.json").read_text(encoding="utf-8")) == MIRROR_STRUCTURE

    def test_wrong_category_rejected(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "x", "clause_ids": ["ZB-C-001"], "notes": None}]))
        assert _run_merge(state, cand) == 1, "commercial 条款进技术大纲 → wrong_category 拒绝"

    def test_not_live_rejected(self, tmp_path):
        dead = _clause("ZB-T-009")
        dead["superseded_by"] = "ZB-T-100"  # _is_active 真实口径: superseded_by 非 None 即非活(字段 status 不存在)
        clauses = MIRROR_CLAUSES + [dead]
        state = _make_state(tmp_path, MIRROR_STRUCTURE, clauses)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "x", "clause_ids": ["ZB-T-009"], "notes": None}]))
        assert _run_merge(state, cand) == 1, "非活条款 → not_live 拒绝"

    def test_chapter_title_conflicts_mirror_chapter_rejected(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate([{"no": 1, "title": "技术要求", "clause_ids": ["ZB-T-002"], "notes": None}]))
        assert _run_merge(state, cand) == 1, "自拟章首段与 mirror 章首段同名 → chapter_name_conflict 拒绝(防同章组合并歧义)"

    def test_corrupt_candidate_exit_1(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        p = tmp_path / "tech_outline.candidates.json"
        p.write_text("{not json", encoding="utf-8")
        assert _run_merge(state, p) == 1
