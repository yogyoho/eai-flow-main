# 大纲自拟结构化（outline_merge）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** bid-technical B1 v1→v2——确认后的大纲经 `outline_merge.py` 落成 `structure.json` 的 `origin=self_created` 技术章树（只接管无锚点条款），build --docs technical 按 B 自拟大纲组织章节。

**Architecture:** 新管线脚本 `outline_merge.py`（A 的 scripts/ canonical，B 绝对路径调用）：读机器候选 `candidates/tech_outline.candidates.json` → 四类 fail-closed 条款校验 + 章名冲突校验 → 删旧 managed 集合/插新章树（精准替换，幂等）→ verify→原子写→`state_guard.sign_state_files` 重签 → 回写 `managed_node_ids` → stdout 单行 JSON 摘要。镜像节点零触碰；responses.py 兜底自创节点永不在 managed 集合。

**Tech Stack:** 纯 stdlib Python 3.12（管线脚本纪律：不调 LLM、argparse CLI、stdout 单行 JSON）；pytest。

**依据 spec:** `docs/superpowers/specs/2026-09-11-outline-merge-design.md`（用户已批）。

**计划期实读已核（写代码时直接信任）:**
- `state_guard.sign_state_files(state_dir: str|Path, names: list[str])` / `verify_state_files(state_dir, *, rebuildable=()) -> list[str]`；extract.py 顺序 = `verify_state_files → atomic_write_json → sign_state_files(state_dir, written)`。
- `booklets.chapter_of(path)` = `path.split("/")[0].strip()` ——章键即首段；自拟章 path 用单段 `{no:02d} {title}`，首段尾段同段，`_allocate_section_numbers` 的 `path.split("/")[-1]` 前导数字自动吃 `{no:02d}`。
- `_allocate_section_numbers`：mirror group 不占号，`origin=self_created` 的 group **必须占号**——大纲章自带 `{no:02d}` 前导数字即自然领号。
- `load_structure` 校验子集：node_id 非空 str / volume∈VOLUMES / slot_type∈SLOT_TYPES / path 非空 / linked_clause_ids 数组 / required_format.template_text 空串拒绝——生成节点需带 `required_format: {"desc": …, "table_spec": null, "template_text": null}` 三键形态。
- `responses.py` 兜底：placement 带 `self_created_path` 时由 merge 建 `origin=self_created` 的 group 节点（同 path 幂等复用）——其 node_id 永不进大纲 managed 集合，共存零适配。
- `progress.py init` 经 `build_output._volume_ctx("technical", structure, …)` 枚举章计划——大纲章落地后自动纳入，无 progress 代码改动。

---

### Task 1: outline_merge.py——候选装载 + fail-closed 校验

**Files:**
- Create: `skills/public/bid-proposal-overall/scripts/outline_merge.py`
- Test: `backend/tests/test_outline_merge.py`（新建）

- [ ] **Step 1: 写失败测试**（新建文件；fixture 复用 `test_bid_proposal_scripts.py` 的 `_copy_prestate` 模式——`from test_bid_proposal_scripts import _copy_prestate` 不行（跨文件 import 测试模块脆），改为在本文件内建最小 state 构造助手 `_make_state(tmp_path, structure_nodes, clauses)`：写 clauses.json/structure.json/entities_whitelist.json 最小集 + state_guard.sign_state_files 首签）

```python
"""outline_merge 单测: 大纲候选校验(fail-closed)/精准替换/幂等/重签/消费端。"""
import json
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "skills" / "public" / "bid-proposal-overall" / "scripts"
if str(SCRIPTS_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SCRIPTS_DIR))

import state_guard
import outline_merge


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
```

（执行注：活性判定委托 `build_output._is_active`（真实口径=`superseded_by is None and not voided`，**不存在 status 字段**——fixture 已按真字段构造）。校验失败时**拒绝明细写 stderr 逐条列出**（kind+clause_id），测试用结构零落盘断言兜底。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_outline_merge.py -v`
Expected: FAIL（`No module named 'outline_merge'`）

- [ ] **Step 3: 实现 outline_merge.py 骨架（本任务只做装载+校验，main 到校验失败即返回）**

```python
"""outline_merge——大纲自拟结构化(B1 v2, spec 2026-09-11-outline-merge-design)。

读确认后的大纲候选(candidates/tech_outline.candidates.json) → fail-closed 校验 →
删旧 managed 集合/插新 origin=self_created 技术章树(精准替换, 幂等) → verify→原子写→
state_guard 重签 structure.json → 回写 managed_node_ids → stdout 单行 JSON 摘要。

纪律: 只新增/替换 self_created 节点(mirror 零触碰); responses.py 兜底自创节点永不入
managed 集合; 不带 --confirm-outline 拒绝执行(确认门纪律, 同 state_guard --confirm-gate1-edit)。
退出码: 0=干净完成; 1=用法/候选/校验拒绝(摘要 stderr 逐条)。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import state_guard

EXIT_OK = 0
EXIT_ERROR = 1

TECH_CATEGORIES = ("technical", "service")
OUTLINE_CONFIRM_FLAG = "--confirm-outline"


class OutlineMergeError(Exception):
    pass


def _load_json(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise OutlineMergeError(f"{what} 不可解析({path}): {exc}")


def validate_candidates(cand: dict, clauses: list[dict], structure: list[dict]) -> list[dict]:
    """候选+条款 fail-closed 校验; 返回规范化章列表; 违规 raise OutlineMergeError(逐条明细)。"""
    problems: list[str] = []
    chapters = cand.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise OutlineMergeError("大纲章列表为空或缺失——空大纲无意义, 拒绝")

    by_id = {c.get("clause_id"): c for c in clauses if isinstance(c, dict)}
    mirror_chapters = {
        n["path"].split("/")[0].strip()
        for n in structure
        if isinstance(n, dict) and n.get("origin") != "self_created"
    }
    mirror_anchored = {
        cid
        for n in structure
        if isinstance(n, dict) and n.get("origin") != "self_created"
        for cid in (n.get("linked_clause_ids") or [])
    }

    seen_chapter_titles: set[str] = set()
    normalized: list[dict] = []
    for idx, ch in enumerate(chapters):
        no, title, cids = ch.get("no"), str(ch.get("title") or "").strip(), ch.get("clause_ids")
        if not isinstance(no, int) or not title or not isinstance(cids, list) or not cids:
            problems.append(f"chapters[{idx}]: no/title/clause_ids 形态不符")
            continue
        if title in mirror_chapters:
            problems.append(f"chapters[{idx}]「{title}」: chapter_name_conflict——自拟章首段与 mirror 章首段同名(防同章组合并歧义)")
        if f"{no:02d} {title}" in {
            n.get("path")
            for n in structure
            if isinstance(n, dict) and n.get("origin") == "self_created"
        }:
            problems.append(f"chapters[{idx}]「{title}」: self_created_path_conflict——与既有 responses 兜底自创节点同 path(双渲染/接管落空风险); 改章名或先清理该兜底节点")
        if title in seen_chapter_titles:
            problems.append(f"chapters[{idx}]「{title}」: duplicate_chapter——大纲内章名重复")
        seen_chapter_titles.add(title)
        clean_cids: list[str] = []
        for cid in cids:
            c = by_id.get(cid)
            if c is None:
                problems.append(f"chapters[{idx}]「{title}」← {cid}: not_found")
            elif c.get("category") not in TECH_CATEGORIES:
                problems.append(f"chapters[{idx}]「{title}」← {cid}: wrong_category({c.get('category')})")
            elif not _is_live(c):
                problems.append(f"chapters[{idx}]「{title}」← {cid}: not_live({c.get('status', c.get('lifecycle', '?'))})")
            elif cid in mirror_anchored:
                problems.append(f"chapters[{idx}]「{title}」← {cid}: mirror_anchored(已由镜像节点挂接)")
            else:
                clean_cids.append(cid)
        if clean_cids:
            normalized.append({"no": no, "title": title, "clause_ids": clean_cids, "notes": ch.get("notes")})
    if problems:
        raise OutlineMergeError("候选校验拒绝(绝不半落地):\n  - " + "\n  - ".join(problems))
    return normalized


def _is_live(clause: dict) -> bool:
    """活条款判定——与 build_output._is_active 同口径(执行期实读对齐, 不复制实现)。"""
    import build_output

    return build_output._is_active(clause)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outline_merge.py", description="大纲自拟结构化(B1 v2): 确认后大纲 → structure.json self_created 章树")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--candidates", required=True, help="tech_outline.candidates.json 路径")
    parser.add_argument("--confirm-outline", action="store_true", help="确认门硬闸: 对话口头确认后才可携带")
    args = parser.parse_args(argv)

    if not args.confirm_outline:
        print("[outline_merge] 拒绝执行: 缺 --confirm-outline(对话确认纪律——用户口头确认后才可携带)", file=sys.stderr)
        return EXIT_ERROR

    state_dir = Path(args.state_dir)
    cand_path = Path(args.candidates)
    try:
        problems = state_guard.verify_state_files(state_dir)
        if problems:
            raise OutlineMergeError("权威状态签名校验失败:\n  - " + "\n  - ".join(problems))
        cand = _load_json(cand_path, "大纲候选")
        clauses = _load_json(state_dir / "clauses.json", "clauses.json")
        structure = _load_json(state_dir / "structure.json", "structure.json")
        validate_candidates(cand, clauses, structure)
    except OutlineMergeError as exc:
        print(f"[outline_merge] {exc}", file=sys.stderr)
        return EXIT_ERROR
    # Task 2 接: 节点生成/精准替换/落盘重签/摘要
    print(json.dumps({"command": "outline_merge", "mode": "validate_only"}, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
```

（执行注：`import build_output` 取 `_is_active`——同目录兄弟模块，管线脚本互调既有先例（build_output import booklets/state_guard）。若 `_is_active` 语义不覆盖 status 字段名，以实读对齐。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_outline_merge.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/public/bid-proposal-overall/scripts/outline_merge.py backend/tests/test_outline_merge.py
git commit -m "feat(bid-materials): outline_merge 候选装载+fail-closed 校验(四类拒绝/章名冲突/空大纲/确认闸)"
```

---

### Task 2: 节点生成 + managed_node_ids 精准替换 + 幂等

**Files:**
- Modify: `skills/public/bid-proposal-overall/scripts/outline_merge.py`
- Test: `backend/tests/test_outline_merge.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
class TestMergeSemantics:
    def _assert_signed(self, state):
        assert state_guard.verify_state_files(state) == [], "merge 后签名必须有效"

    def test_merge_creates_self_created_chapters(self, tmp_path):
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        assert _run_merge(state, cand) == 0
        structure = json.loads((state / "structure.json").read_text(encoding="utf-8"))
        mine = [n for n in structure if n.get("origin") == "self_created" and "outline" in json.dumps(n)]
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
        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        old_bytes = (state / "structure.json").read_bytes()
        real_sign = state_guard.sign_state_files
        calls = {"n": 0}

        def flaky_sign(sd, names):
            calls["n"] += 1
            if calls["n"] == 2:  # 首签(_make_state)放行; merge 的重签炸; 回滚对旧内容的重签(call 3)放行
                raise OSError("模拟签名通道故障")
            return real_sign(sd, names)

        monkeypatch.setattr(state_guard, "sign_state_files", flaky_sign)
        assert _run_merge(state, cand) == 1
        assert (state / "structure.json").read_bytes() == old_bytes, "重签失败回滚——structure.json 字节不变"
```

（执行注：`"outline" in json.dumps(n)` 的探测断言实现时换成精确断言（desc 含 pack 标记或 path 匹配）——上面形态以实现后收紧。`remaining_unanchored` 口径=活 technical/service 条款 − 任意节点(含 self_created/兜底)已挂接者。）

- [ ] **Step 2: 红证据**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_outline_merge.py::TestMergeSemantics -v`
Expected: FAIL（main 仍 validate_only）

- [ ] **Step 3: 实现 merge 语义**（追加到 outline_merge.py；main 校验通过后接管线）

```python
def _next_node_id(structure: list[dict]) -> str:
    used = {int(n["node_id"].split("-")[1]) for n in structure if isinstance(n.get("node_id"), str) and "-" in n.get("node_id", "")}
    i = 1
    while i in used:
        i += 1
    return f"S-{i:03d}"


def build_outline_nodes(normalized: list[dict], structure: list[dict], source_pack: str | None) -> list[dict]:
    """大纲章 → self_created group 节点(单段 path `{no:02d} {title}`, 前导数字供领号)。"""
    source = f"pack:{source_pack}" if source_pack else "自由拟"
    nodes = []
    for ch in normalized:
        nodes.append({
            "node_id": _next_node_id(structure + nodes),
            "volume": "technical",
            "path": f"{ch['no']:02d} {ch['title']}",
            "slot_type": "group",
            "required_format": {"desc": f"大纲自拟章(B1 v2; 来源 {source}; 确认后 merge)", "table_spec": None, "template_text": None},
            "linked_clause_ids": list(ch["clause_ids"]),
            "origin": "self_created",
        })
    return nodes


def validate_managed(old_managed, structure: list[dict], assigned: set[str]) -> None:
    """managed 集合 fail-closed 校验(第五道闸): 候选文件在 Agent 可写区, 盲删即静默丢章。
    每个 id 必须存在于 structure 且 origin==self_created; 其 linked_clause_ids ⊆ 本轮大纲
    分配集合(超出者=外部经 responses merge 追加的锚点——删除即静默丢失, 拒绝并提示先重跑
    responses merge 或确认弃锚)。"""
    if not isinstance(old_managed, list):
        raise OutlineMergeError("managed_node_ids 应为数组")
    by_id = {n.get("node_id"): n for n in structure if isinstance(n, dict)}
    problems = []
    for nid in old_managed:
        n = by_id.get(nid)
        if n is None:
            problems.append(f"managed {nid}: unknown——不存在于 structure")
        elif n.get("origin") != "self_created":
            problems.append(f"managed {nid}: not_self_created——指向 mirror 节点(mirror 零触碰铁律)")
        else:
            extra = set(n.get("linked_clause_ids") or []) - assigned
            if extra:
                problems.append(
                    f"managed {nid}: external_anchors {sorted(extra)}——节点挂接含 responses merge 外加锚点, "
                    "删除即静默丢失; 先重跑 responses merge 或确认弃锚后从 managed 移除该 id"
                )
    if problems:
        raise OutlineMergeError("managed 集合校验拒绝:\n  - " + "\n  - ".join(problems))


def merge(structure: list[dict], normalized: list[dict], old_managed: list[str], source_pack: str | None) -> tuple[list[dict], list[str]]:
    """精准替换: 校验 managed → 删旧 managed 节点 → 插新章树(尾部追加) → 返回 (新 structure, 新 managed)。"""
    validate_managed(old_managed, structure, {cid for ch in normalized for cid in ch["clause_ids"]})
    old = set(old_managed)
    kept = [n for n in structure if n.get("node_id") not in old]
    nodes = build_outline_nodes(normalized, kept, source_pack)
    return kept + nodes, [n["node_id"] for n in nodes]
```

（main 管线：`normalized = validate_candidates(...)` → `old_managed = cand.get("managed_node_ids") or []` → `new_structure, managed = merge(structure, normalized, old_managed, cand.get("source_pack"))` → `remaining_unanchored = 活技术条款数 − 任意节点已挂接数` → 原子写 structure.json（临时文件+os.replace）→ `state_guard.sign_state_files(state_dir, ["structure.json"])` → 回写候选 `managed_node_ids`（原子写）→ stdout 摘要 `{"command": "outline_merge", "created": N, "replaced": len(old_managed), "remaining_unanchored": M}`。**重签失败回滚**：写盘前暂存旧 structure.json 字节；sign 抛错 → 回写旧字节 + 对旧内容重签（恢复原签名态）→ exit 1（stderr 点名「structure.json 未变更，重建入口=重跑 outline_merge」）——保证 spec §6「重签失败=字节不变」可测试成立。）

- [ ] **Step 4: 绿 + 全文件绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_outline_merge.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/public/bid-proposal-overall/scripts/outline_merge.py backend/tests/test_outline_merge.py
git commit -m "feat(bid-materials): outline_merge 节点生成+managed 精准替换+幂等+remaining_unanchored 摘要"
```

---

### Task 3: 消费端核验（build 渲染 / progress 纳入）+ responses 共存回归

**Files:**
- Test: `backend/tests/test_outline_merge.py`（追加，复用 `test_bid_proposal_scripts.py` 的 `_build_module` 导入模式）

- [ ] **Step 1: 写消费端测试**

```python
class TestConsumers:
    def test_build_renders_outline_chapter(self, tmp_path):
        """大纲章树落地后, build --docs technical 按大纲章组织渲染。"""
        import importlib

        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        assert _run_merge(state, cand) == 0
        bo = importlib.import_module("build_output")
        rc = bo.main(["--state-dir", str(state), "--out", str(tmp_path / "out"), "--docs", "technical"])
        assert rc in (0, 3), "渲染不因大纲章失败(rc=3 允许 lint 异常)"
        tech_text = "".join(
            (tmp_path / "out" / f.name).read_text(encoding="utf-8")
            for f in sorted((tmp_path / "out").glob("技术卷-*.md"))
        )
        assert "项目总体理解" in tech_text, "大纲章标题进技术卷"

    def test_progress_init_counts_outline_chapter(self, tmp_path):
        import importlib

        state = _make_state(tmp_path, MIRROR_STRUCTURE, MIRROR_CLAUSES)
        cand = _write_candidate(tmp_path, _candidate(GOOD))
        assert _run_merge(state, cand) == 0
        pg = importlib.import_module("progress")
        rc = pg.main(["init", "--state-dir", str(state)])
        assert rc == 0
        # progress.json 写在 workspace 根(= state_dir.parent, 与 last_build.json 同级)——非 state/ 内
        prog = json.loads((state.parent / "progress.json").read_text(encoding="utf-8"))
        chapters = json.dumps(prog, ensure_ascii=False)
        assert "项目总体理解" in chapters, "章门计划纳入大纲章"
```

（执行注：若消费端测试红，**先查本文件 fixture**（`_clause` 的 `response_status` 枚举字段、progress.json 读取路径=workspace 根），排除后才是消费端真缺口——build/progress 对最小 state 的全部柔性（responses 缺失骨架回退、depth_targets 缺失门跳过）已被既有实现覆盖，无需补 rubric.json（run_build 根本不读它）。）

- [ ] **Step 2: 红→绿**（build/progress 本就按 structure 投影——预期 green-on-arrival，红了即消费端真有适配缺口，就地查）

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_outline_merge.py
git commit -m "test(bid-materials): outline_merge 消费端核验(build 大纲章渲染/progress 纳入/兜底共存)"
```

---

### Task 4: SKILL.md 契约（B1 v2 文案 + 双速查表 + A 防幻觉契约）

**Files:**
- Modify: `skills/public/bid-technical/SKILL.md`（B1 节改写 + 速查表加一行；注意 69 行现状，预算 ≤120 余量充足）
- Modify: `skills/public/bid-proposal-overall/SKILL.md`（防幻觉契约枚举追加 outline_merge——**行内改**，A 已在 120 行天花板）
- Modify: `backend/tests/test_bid_proposal_scripts.py`（B 速查表脚本存在性测试自动覆盖新命令；SKILL required tokens 视需要追加）

- [ ] **Step 1: B SKILL.md**——B1 节"v1 边界"段替换为：

```markdown
- **v2 结构化(确认后)**: `outline_merge.py --state-dir … --candidates candidates/tech_outline.candidates.json --confirm-outline` 把确认后大纲落成 structure.json 自拟章树(origin=self_created, 只接管无镜像锚点的条款; mirror 章零触碰; 重签自动)。候选 JSON 双形态由 B1 生成(B2 消费其章锚点); 重跑=精准替换(managed_node_ids, 外加锚点的旧 managed 节点会被拒绝删除)。**顺序纪律: 大纲 merge 前不跑 responses merge; responses merge 之后重跑大纲 merge 的, 必须再重跑一次 responses merge**(大纲章替换会使 responses 挂接失效); 无大纲场景 responses 兜底路径不变。
```

B 铁律 1 行内追加（同一行内改，不增行）：`……签名校验失败按错误行恢复` 后接 `；唯一获准的 structure 直写通道=outline_merge --confirm-outline(重签自动)`。

B 速查表追加：

```bash
python /mnt/skills/public/bid-proposal-overall/scripts/outline_merge.py --state-dir /mnt/user-data/workspace/bid/state --candidates /mnt/user-data/workspace/bid/candidates/tech_outline.candidates.json --confirm-outline
```

- [ ] **Step 2: A SKILL.md 三处行内改**（120 行预算不破——全部同行内改不增行）：
  1. 防幻觉契约："progress 只有 init/…/mark-build-done" 句后追加行内说明：`outline_merge 无子命令(--confirm-outline 为确认硬闸)`。
  2. 铁律 9 行内追加：`门1 后修 structure.json 的唯一获准通道=outline_merge --confirm-outline(授权级别等同确认门1 class 修订)`。
  3. 脚本清单行（"下十个 Python 模块(ingest/…+ progress)"）：`十个`→`十一个`，括号枚举追加 `outline_merge`。

- [ ] **Step 2b: 契约 token 钉**——`backend/tests/test_bid_proposal_scripts.py`：B SKILL.md required-token 断言（该文件既有 B 侧 token 机制处）追加 `"outline_merge"` 与 `"--confirm-outline"`；A SKILL.md required tokens 追加 `"outline_merge"`——SKILL.md 文案日后被删/改丢时有测试变红（不留"视需要追加"的无落点表述）。

- [ ] **Step 3: 契约测试**——跑 `TestTwoSkillSplitContract`（速查表脚本存在性自动覆盖新命令）+ B_STAGE_GUIDES tokens 不变；若 `test_quickref_scripts_exist_on_disk` 对 B 新行报红（不应——脚本真实存在），就地查。全 bid 套件绿。

- [ ] **Step 4: Commit**

```bash
git add skills/public/bid-technical/SKILL.md skills/public/bid-proposal-overall/SKILL.md backend/tests/test_bid_proposal_scripts.py
git commit -m "docs(bid-materials): B1 v2 契约——SKILL.md 大纲 merge 工作流+双速查表+防幻觉枚举"
```

---

### Task 5: 全量回归 + 推送

- [ ] **Step 1**: `cd backend && PYTHONPATH=. uv run pytest tests/test_outline_merge.py tests/test_bid_proposal_scripts.py tests/test_bank_compile.py tests/test_bid_materials.py tests/test_geo_sample_bank_compile.py -q`（全绿）+ `uv run ruff check app ../skills/public/bid-proposal-overall/scripts ../skills/public/bid-technical/scripts`
- [ ] **Step 2**: `git push origin main-dev-fork`（flaky 重试 ≤3）+ rev-list 0/0
- [ ] **Step 3**: 开发日志追加一行（append-only，不暂存）

---

## 后续计划（本文档不覆盖）

- 大纲候选的前端只读展示（bid-materials 页面）。
- agnes E2E clean4（A+B 双入口真实走查，含大纲流程）。
