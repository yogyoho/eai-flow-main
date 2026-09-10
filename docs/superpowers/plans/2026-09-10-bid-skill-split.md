# bid 技能拆分（bid-proposal-overall / bid-technical）实现计划（Plan 3）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `bid-proposal-writing` 拆成配对双技能——A `bid-proposal-overall`（阶段0-3+5+build 整体方案，全量脚本 canonical）+ B `bid-technical`（纯编排：大纲自拟→供源级联→章门→build 技术卷，仅自带离线工具 bank_compile），并以 `build_output.py --docs overall|technical|all` 旗标承载两技能共享 outputs/ 的 manifest 合并语义。

**Architecture:** `--docs` 是拆分的核心契约（spec §3.2）：单范围 build 只重写本范围册组+索引卷对应节（未重建节以盘上既有索引原样保留）、manifest 读旧合并（范围外 deliverables/files/docs 保留）、清场收窄（只删本范围前缀 stale）、副表跨两卷聚合归 `all` 专责重建。目录层面 `git mv` 保留历史；B 零自有管线脚本（速查表指向 A 绝对路径，pair-install）。

**Tech Stack:** 纯 stdlib Python 3.12（skill 脚本纪律不变）；pytest；git mv；无新依赖。

**依据 spec:** `docs/superpowers/specs/2026-09-06-bid-materials-two-skill-design.md` §3（拆分+--docs 契约）+ §3.3（A→B 接缝）+ §6 测试矩阵（两 SKILL.md 契约测试 / --docs 三态）+ §7.5（实施顺序位次）。前置 Plan 2（bank_compile+深度门）已完成推送（rev-list 0/0 @ e3c78e481）。

**现状基线（写计划时核查过）:**
- `build_output.py` 尚无 `--docs`；`run_build(state_dir, out_dir)` 恒渲两文档、`_sweep_stale_outputs(out_dir, new_deliverables)` 按"旧 manifest 列名−新集合"全量清场（manifest 缺失分支附带删 v3 遗留双卷）。
- 册文件名前缀：`整体方案-NN-*.md` / `技术卷-NN-*.md`（`DOC_OVERALL="整体方案"` / `DOC_TECH="技术卷"`）；静态件=`0-总目录索引.md`+四副表（`偏离表/覆盖率报表/人核清单/实体lint报告.md`）；`booklets.render_index(groups, extra_notes)` 按 `## {doc}册组(N 册)` 节头逐组渲染。
- manifest：`{"skill": "bid-proposal-writing", "version": 1, "deliverables": [...], "aux_md": [...], "files": {sha}, "docs": {组统计}, "whitelist_sha256"}`；harness `delivery_contract.resolve_manifest` 对 skill 只要求非空字符串（**无白名单**，改值安全）；test_delivery_contract_gates 自构 manifest 不受影响（**不改该测试文件**）。
- `DEFAULT_DEPTH_TARGETS_PATH = Path(__file__).resolve().parent.parent / "references" / "depth_targets.json"`（拆分后须指到 B 的 references）。
- 路由双向锁（T8b/DEC-1）：A SKILL.md ≤120 行 + 点名四份分组指南 + `snapshot.py` 源码反向引用指南基名；三处同步失败才允许改名。
- 旧路径引用点（`grep -rn "bid-proposal-writing"` 全量triage 后的功能性清单）：`test_bid_proposal_scripts.py`(16) / `test_bank_compile.py`(1) / `test_bid_materials.py`(2) / `test_delivery_contract_gates.py`(4, **保持不动**——自构 manifest 的 harness 门测试，skill 名任意) / `e2e_bid_driver.py`(3) / `score_checkpoints.py`(3) / `gen_fixtures.py`(3) / `conftest.py`(1 注释) / `extensions_config.json` + `deploy/offline/extensions_config.json`(各1) / `ops-diagnosis` SKILL.md+failure-signatures.md+_common.py(各1) / `backend/docs/OBSERVABILITY.md`(1) / harness `delivery_contract.py`+`present_file_tool.py`(**仅注释, 不改**——harness 零改动原则) / `TODOS.md`(史述, 不改)。
- 历史文档**不改名**：`docs/superpowers/specs/2026-08-16-bid-proposal-writing-skill-design.md`、`docs/designs/bid-proposal-writing-v4-volume-architecture.md` 等——脚本 docstring 里的"规格:"指向它们，保持原样。
- BidSample 台账已有 3 行入库（Plan 2 T7），`source_path` 指旧路径——Task 6 有 SQL 修正步。

---

### Task 1: build_output `--docs` 旗标（manifest 合并 + 清场收窄 + 索引分区重写 + 副表归属 all）

**Files:**
- Modify: `skills/public/bid-proposal-writing/scripts/build_output.py`
- Modify: `skills/public/bid-proposal-writing/scripts/booklets.py`（render_index 增 section 透传）
- Test: `backend/tests/test_bid_proposal_scripts.py`（新增 `TestBuildDocsScope`）

- [ ] **Step 1: 写失败测试**（追加到 test_bid_proposal_scripts.py 末尾；复用既有 `_copy_prestate` / `_build_module` / `_out_text` / `_snapshot` 助手）

```python
class TestBuildDocsScope:
    """--docs 三态契约(spec §3.2): manifest 合并/清场收窄/索引分区/副表归属 all。"""

    SIDECARS = ("偏离表.md", "覆盖率报表.md", "人核清单.md", "实体lint报告.md")

    def test_docs_overall_only_writes_overall_and_index(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        out = tmp_path / "out"
        assert _build_module().main(["--state-dir", str(state), "--out", str(out), "--docs", "overall"]) == 0
        names = {p.name for p in out.iterdir()}
        assert any(n.startswith("整体方案-") for n in names), "本范围册集必须产出"
        assert not any(n.startswith("技术卷-") for n in names), "范围外册集不得产出"
        assert not any(n in self.SIDECARS for n in names), "副表归属 all 范围专责重建"
        index = _out_text(out, "0-总目录索引.md")
        assert "整体方案册组" in index and "技术卷册组" not in index, "未建册组节整体略去"

    def test_docs_technical_then_overall_merges(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        out = tmp_path / "out"
        mod = _build_module()
        assert mod.main(["--state-dir", str(state), "--out", str(out), "--docs", "technical"]) == 0
        assert mod.main(["--state-dir", str(state), "--out", str(out), "--docs", "overall"]) == 0
        names = {p.name for p in out.iterdir()}
        assert any(n.startswith("技术卷-") for n in names) and any(n.startswith("整体方案-") for n in names), "两范围册集并存"
        assert not any(n in self.SIDECARS for n in names), "副表仍未重建(两次都是单范围)"
        index = _out_text(out, "0-总目录索引.md")
        assert "技术卷册组" in index and "整体方案册组" in index, "索引分区合并: 保留组+新写组"
        manifest = json.loads((out / "delivery_manifest.json").read_text(encoding="utf-8"))
        assert any(n.startswith("技术卷-") for n in manifest["deliverables"]) and any(
            n.startswith("整体方案-") for n in manifest["deliverables"]
        ), "deliverables=合并集"

    def test_single_scope_preserves_other_scope_files_byte_identical(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        out = tmp_path / "out"
        mod = _build_module()
        assert mod.main(["--state-dir", str(state), "--out", str(out)]) == 0  # all 基线
        before = _snapshot(out)
        assert mod.main(["--state-dir", str(state), "--out", str(out), "--docs", "technical"]) == 0
        overall_before = {n: b for n, b in before.items() if n.startswith("整体方案-")}
        overall_after = {p.name: p.read_bytes() for p in out.rglob("*") if p.is_file() and p.name.startswith("整体方案-")}
        assert overall_after == overall_before, "范围外册文件字节不动"
        for n in self.SIDECARS:
            assert (out / n).read_bytes() == before[n], "副表归属 all, 单范围 build 不触碰"

    def test_technical_scope_sweep_narrowing(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        out = tmp_path / "out"
        mod = _build_module()
        assert mod.main(["--state-dir", str(state), "--out", str(out)]) == 0
        (out / "技术卷-09-旧册.md").write_text("stale tech", encoding="utf-8")
        (out / "整体方案-09-旧册.md").write_text("stale overall", encoding="utf-8")
        manifest = json.loads((out / "delivery_manifest.json").read_text(encoding="utf-8"))
        manifest["deliverables"] = sorted(set(manifest["deliverables"]) | {"技术卷-09-旧册.md", "整体方案-09-旧册.md"})
        (out / "delivery_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        assert mod.main(["--state-dir", str(state), "--out", str(out), "--docs", "technical"]) == 0
        assert not (out / "技术卷-09-旧册.md").exists(), "范围内 stale 册删除"
        assert (out / "整体方案-09-旧册.md").exists(), "范围外 stale 册保留(收窄)"
        assert mod.main(["--state-dir", str(state), "--out", str(out), "--docs", "all"]) == 0
        assert not (out / "整体方案-09-旧册.md").exists(), "all 范围全清"

    def test_manifest_out_of_scope_files_sha_preserved(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        out = tmp_path / "out"
        mod = _build_module()
        assert mod.main(["--state-dir", str(state), "--out", str(out)]) == 0
        manifest = json.loads((out / "delivery_manifest.json").read_text(encoding="utf-8"))
        tech_sha = {n: s for n, s in manifest["files"].items() if n.startswith("技术卷-")}
        assert tech_sha, "前置: all 基线 manifest 须含技术卷册 sha"
        assert mod.main(["--state-dir", str(state), "--out", str(out), "--docs", "overall"]) == 0
        manifest2 = json.loads((out / "delivery_manifest.json").read_text(encoding="utf-8"))
        assert {n: s for n, s in manifest2["files"].items() if n.startswith("技术卷-")} == tech_sha, "范围外 files sha 原样保留"

    def test_docs_invalid_value_exit_1(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        rc = _build_module().main(["--state-dir", str(state), "--out", str(tmp_path / "out"), "--docs", "bogus"])
        assert rc == 1, "argparse choices 拒绝→统一改道 1(2 保留给 ingest OCR 分流)"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_proposal_scripts.py::TestBuildDocsScope -v`
Expected: FAIL（`unrecognized arguments: --docs`）

- [ ] **Step 3: 实现——build_output.py 五处修改**

3a. 常量区（`DOC_TECH` 行后）追加：

```python
# --- --docs 构建范围(spec §3.2): 两技能共享 outputs/ 的合并契约 ------------------
# A(bid-proposal-overall) build --docs overall / B(bid-technical) build --docs technical;
# 单范围: 范围外册/副表不重写不触碰, 索引卷分区重写, manifest 合并, 清场收窄。
DOCS_CHOICES = ("overall", "technical", "all")
_SCOPE_PREFIXES = {"overall": ("整体方案-",), "technical": ("技术卷-",), "all": ("整体方案-", "技术卷-")}
MANIFEST_SKILL = "bid-proposal-writing"  # 交付契约属主(Plan3 Task2 改 bid-proposal-overall)
```

3b. `_sweep_stale_outputs` 整函数替换（清场名单改由 run_build 判定传入；legacy v3 双卷清理收归 all 范围）：

```python
def _sweep_stale_outputs(out_dir: Path, stale_names: set[str], docs: str) -> list[str]:
    """上一轮交付清场(11A, --docs 收窄版): 只删调用方判定的 stale 名单
    (旧 manifest 列名 − 合并集, 已过范围过滤)。manifest 缺失 → 跳过清场
    (首轮构建合法态; all 范围附带确定性移除 v3 遗留双卷)。防御: 只删 out_dir 直属普通文件。
    """
    manifest_path = out_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        # v3→v4 升级边角: 旧双卷(商务卷/技术卷.md)无 manifest 可依——all 范围确定性移除,
        # 防其以"杂散 .md"身份触发自家交付门反控(单范围不碰: 清场收窄)
        removed_legacy: list[str] = []
        if docs == "all":
            for legacy in LEGACY_OUTPUT_FILES:
                target = out_dir / legacy
                if target.is_file():
                    target.unlink()
                    removed_legacy.append(legacy)
        note = f"清场跳过: {MANIFEST_NAME} 缺失(首轮构建)"
        return [note + (f"; 移除 v3 遗留双卷 {', '.join(removed_legacy)}" if removed_legacy else "")]
    deleted: list[str] = []
    for name in sorted(stale_names):
        target = out_dir / name
        if target.parent == out_dir and target.is_file():
            target.unlink()
            deleted.append(name)
    return [f"清场删除上一轮遗留 {len(deleted)} 文件: {', '.join(sorted(deleted))}"] if deleted else []
```

3c. 索引/范围助手（`_sweep_stale_outputs` 前插入）：

```python
def _in_stale_scope(name: str, docs: str) -> bool:
    """清场收窄(spec §3.2): 单范围只删本范围册前缀的 stale; all 全清。
    索引卷两个单范围都重写, 永不 stale。"""
    if name == INDEX_FILE:
        return False
    if docs == "all":
        return True
    return name.startswith(_SCOPE_PREFIXES[docs])


def _split_index_group(index_md: str, doc: str) -> str | None:
    """从索引卷文本切出 '{doc}册组' 节(含节头行, 至下一 '## ' 前缀或文末); 无 → None。"""
    lines = index_md.split("\n")
    start = next((i for i, ln in enumerate(lines) if ln.startswith(f"## {doc}册组")), None)
    if start is None:
        return None
    end = next((j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip("\n")
```

3d. `run_build` 整函数替换（签名加 `docs: str = "all"`；渲染/索引/写盘/manifest/摘要全按范围语义）：

```python
def run_build(state_dir: Path, out_dir: Path, docs: str = "all") -> int:
    """读状态(只读) → --docs 范围册集渲染(v4+spec §3.2) → 清场收窄 → 原子写盘
    → 交付凭据(manifest 合并语义) → stdout 单行 JSON 摘要; 返回退出码。"""
    guard_problems = state_guard.verify_state_files(state_dir)
    if guard_problems:
        raise BuildOutputError("权威状态文件签名校验失败(疑似脚本外直写/误删):\n  - " + "\n  - ".join(guard_problems))
    clauses = load_clauses(state_dir)
    structure = load_structure(state_dir)
    whitelist = load_whitelist(state_dir)
    responses = load_responses(state_dir)

    anomalies: list[dict] = []
    if whitelist is None:
        anomalies.append({"kind": "whitelist_missing", "message": "entities_whitelist.json 缺失, lint 按空集 diff(全部候选进[待核对])——确认门1 未锁定白名单或文件被移动"})

    # 深度门(Plan2 T6): 基线缺失=门静默跳过(可诊断); 质量牵引不阻断凭据(spec §4.4)。
    depth_targets, depth_skip_reason = load_depth_targets()
    depth_anomalies, depth_summary = run_depth_gate(responses, depth_targets, skip_reason=depth_skip_reason)
    anomalies.extend(depth_anomalies)

    # --docs 范围渲染: technical 不渲 overall; overall 渲 technical 仅为占位页分册目录
    # (tech_ref——以当前 state 投影, technical 文件不落盘); all 两组全渲。
    slots = load_slots(state_dir)
    overall_doc: dict | None = None
    tech_doc: dict | None = None
    if docs in ("all", "technical"):
        tech_doc = render_doc_booklets(DOC_TECH, structure, clauses, responses, slots=slots)
        anomalies.extend(tech_doc["anomalies"])
    if docs in ("all", "overall"):
        overall_doc = render_doc_booklets(DOC_OVERALL, structure, clauses, responses, tech_ref=tech_doc, slots=slots)
        anomalies.extend(overall_doc["anomalies"])
    dev_rows = deviation_rows(clauses)  # 副表数据恒全量计算(摘要消费); 是否落盘由范围决定
    deviation_md = render_deviation_md(dev_rows, structure)
    coverage = compute_coverage(clauses)
    coverage_md = render_coverage_md(clauses, coverage, structure)
    checklist_md, checklist_counts = render_checklist_md(structure, responses)
    scan_texts: dict[str, str] = {}
    if overall_doc is not None:
        scan_texts.update(overall_doc["contents"])
    if tech_doc is not None:
        scan_texts.update(tech_doc["contents"])
    flagged, hits = run_entity_lint(clauses, whitelist, extra_texts=scan_texts)
    anomalies.extend(flagged)
    entity_gate = _entity_gate_state(state_dir, flagged)
    lint_md = render_lint_md(whitelist, flagged, hits, depth_anomalies=depth_anomalies, depth_targets=depth_targets, depth_skip_reason=depth_skip_reason)

    # 索引卷分区重写(spec §3.2): 重建组 fresh 渲染; 未重建组以盘上既有索引同节原样保留
    # (含旧节头/计数——与盘上未动文件一致); 盘上无既有索引/该节缺席 → 该节整体略去。
    existing_index_path = out_dir / INDEX_FILE
    existing_index = existing_index_path.read_text(encoding="utf-8") if existing_index_path.is_file() else ""
    index_groups: list[dict] = []
    if overall_doc is not None:
        index_groups.append({"doc": DOC_OVERALL, "files": overall_doc["files"], "booklets": overall_doc["booklets"]})
    else:
        sec = _split_index_group(existing_index, DOC_OVERALL)
        if sec is not None:
            index_groups.append({"doc": DOC_OVERALL, "section": sec})
    if docs != "overall" and tech_doc is not None:
        index_groups.append({"doc": DOC_TECH, "files": tech_doc["files"], "booklets": tech_doc["booklets"]})
    else:
        sec = _split_index_group(existing_index, DOC_TECH)
        if sec is not None:
            index_groups.append({"doc": DOC_TECH, "section": sec})
    index_md = booklets.render_index(
        index_groups,
        extra_notes=["槽位编排与围栏域分布见 覆盖率报表.md(槽位编排表); 分册告警见构建摘要 booklets 字段"],
    )

    outputs: dict[str, str] = {}
    if overall_doc is not None:
        outputs.update(overall_doc["contents"])
    if docs != "overall" and tech_doc is not None:
        outputs.update(tech_doc["contents"])
    outputs[INDEX_FILE] = index_md
    if docs == "all":
        # 副表跨两卷聚合(spec §3.2) → all 专责重建; 单范围保留盘上既有副表不触碰
        outputs.update({"偏离表.md": deviation_md, "覆盖率报表.md": coverage_md, "人核清单.md": checklist_md, "实体lint报告.md": lint_md})
    written_names = set(outputs)

    # manifest 合并语义(spec §3.2): 读既有 manifest → 范围内条目更新、范围外保留。
    manifest_parse_warning: str | None = None
    manifest_path = out_dir / MANIFEST_NAME
    old_manifest: dict | None = None
    if manifest_path.is_file():
        try:
            parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
            old_manifest = parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            old_manifest = None
        if old_manifest is None:
            manifest_parse_warning = f"清场跳过: {MANIFEST_NAME} 不可解析——不做遗留文件删除"
    old_deliverables = [n for n in (old_manifest or {}).get("deliverables", []) if isinstance(n, str)]
    stale_names = {n for n in old_deliverables if n not in written_names and _in_stale_scope(n, docs)}
    merged_deliverables = sorted((set(old_deliverables) - stale_names) | written_names)
    old_files = (old_manifest or {}).get("files", {})
    old_files = old_files if isinstance(old_files, dict) else {}
    files_sha = {
        **{n: old_files[n] for n in merged_deliverables if n not in written_names and n in old_files},
        **{name: hashlib.sha256(outputs[name].encode("utf-8")).hexdigest() for name in written_names},
    }
    old_docs_stats = (old_manifest or {}).get("docs", {})
    docs_stats: dict = dict(old_docs_stats) if isinstance(old_docs_stats, dict) else {}
    if overall_doc is not None:
        docs_stats[DOC_OVERALL] = {"booklets": len(overall_doc["files"]), "pages_est": booklets.total_pages(overall_doc["booklets"])}
    if docs in ("all", "technical"):
        docs_stats[DOC_TECH] = {"booklets": len(tech_doc["files"]), "pages_est": booklets.total_pages(tech_doc["booklets"])}

    sweep_warnings = _sweep_stale_outputs(out_dir, stale_names, docs)
    if manifest_parse_warning:
        sweep_warnings.append(manifest_parse_warning)
    for name in sorted(written_names):
        atomic_write_text(out_dir / name, outputs[name])

    # 交付凭据(v4 WP-2.3 bid 侧): skill/version/deliverables——合并集; 实体门 blocked →
    # 不写凭据且作废旧凭据/标记(交付门 STATUS_MISSING 全禁 .md)。
    whitelist_path = state_dir / "entities_whitelist.json"
    whitelist_sha256 = state_guard.sha256_file(whitelist_path) if whitelist_path.is_file() else None
    if entity_gate["blocked"]:
        stale_manifest = out_dir / MANIFEST_NAME
        if stale_manifest.is_file():
            stale_manifest.unlink()
        stale_marker = out_dir / ".delivery-contract"
        if stale_marker.is_file():
            stale_marker.unlink()
        sweep_warnings.append(
            f"实体门硬门生效(第 {entity_gate['rounds']} 轮): 白名单外实体未处置, 本轮不写交付凭据——"
            "处置路径: 确认候选白名单入册(见 实体lint报告.md)或回 stage4a 重写响应后重跑"
        )
    manifest = {
        "skill": MANIFEST_SKILL,
        "version": MANIFEST_VERSION,
        "deliverables": merged_deliverables,
        # 确认门工件白名单(WP-2.3 aux_md): 门1 条款清单/门2 补遗diff表由 extract/merge
        # 阶段写 outputs/ 并在门2(build 后)经 present_files 呈现——非管线 build 产物但
        # 合法呈现, 由本管线在此申报(harness 交付门放行集=deliverables∪aux_md)。
        "aux_md": ["条款清单.md", "补遗diff表.md"],
        "files": files_sha,
        "docs": docs_stats,
        "whitelist_sha256": whitelist_sha256,
    }
    if not entity_gate["blocked"]:
        atomic_write_text(out_dir / MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        # 交付契约标记(bug-2225/3109): build 成功即激活本线程交付门——任一 --docs 范围
        # 成功即激活/更新(契约线程级, 不受范围影响)。
        atomic_write_text(out_dir / ".delivery-contract", "{}\n")

    # 构建回执(回放实证 fd49b085); 内容确定性, 重跑字节级幂等。
    receipt = {
        "out_dir": str(out_dir),
        "files": files_sha,
        "whitelist_sha256": whitelist_sha256,
        "entity_gate": entity_gate,
    }
    atomic_write_text(state_dir.parent / "last_build.json", json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    responded_ids = {r.get("clause_id") for r in responses}
    summary_booklets: dict = {}
    if overall_doc is not None:
        summary_booklets[DOC_OVERALL] = {"count": len(overall_doc["files"]), "pages_est": booklets.total_pages(overall_doc["booklets"]), "warnings": overall_doc["warnings"]}
    if docs in ("all", "technical"):
        summary_booklets[DOC_TECH] = {"count": len(tech_doc["files"]), "pages_est": booklets.total_pages(tech_doc["booklets"]), "warnings": tech_doc["warnings"]}
    summary = {
        "docs": docs,
        "written": sorted(written_names),
        "booklets": summary_booklets,
        "sweep": sweep_warnings,
        "coverage": coverage,
        "deviation_rows": len(dev_rows),
        "template_prefill_count": sum(1 for n in structure if template_text_of(n) is not None),
        "responses_rendered": sum(1 for c in clauses if _is_active(c) and c.get("category") in ENTRY_CATEGORIES and c["clause_id"] in responded_ids),
        "fixed_rows_replicated": sum(_fixed_row_count(n) for n in structure),
        "self_created_sections": sum(1 for n in structure if n.get("origin") == "self_created"),
        "human_checklist": checklist_counts,
        "lint": {"flagged": len(flagged), "entity_hits": len(hits), "whitelist_missing": whitelist is None},
        "depth_gate": depth_summary,
        "entity_gate": entity_gate,
        "whitelist_sha256": whitelist_sha256,
        "anomalies": anomalies,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK if not anomalies else EXIT_ANOMALY
```

3e. `main()` 加旗标并透传：

```python
    parser.add_argument("--docs", choices=DOCS_CHOICES, default="all", help="构建范围(spec §3.2): overall=整体方案组 / technical=技术卷组 / all=两组+副表(默认, 兼容既有调用)")
```

调用行改 `return run_build(Path(args.state_dir), Path(args.out), args.docs)`。

3f. booklets.py `render_index` 循环体首部加 section 透传：

```python
    for group in groups:
        if group.get("section") is not None:
            # 单范围 build(--docs): 未重建册组节以既有索引文本原样嵌入(含旧节头/计数)
            lines.append(group["section"])
            lines.append("")
            continue
        lines.append(f"## {group['doc']}册组({len(group['booklets'])} 册)")
```

- [ ] **Step 4: 跑测试确认通过（含既有回归不破）**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_proposal_scripts.py tests/test_bid_materials.py tests/test_delivery_contract_gates.py -v`
Expected: 全 PASS（默认 all 语义字节兼容——`test_rerun_byte_identical`/`test_six_outputs_no_tmp_residue` 等既有用例是本次改动的回归钉）

- [ ] **Step 5: Commit**

```bash
git add skills/public/bid-proposal-writing/scripts/build_output.py skills/public/bid-proposal-writing/scripts/booklets.py backend/tests/test_bid_proposal_scripts.py
git commit -m "feat(bid-materials): build --docs 旗标(manifest 合并/清场收窄/索引分区/副表归属 all)"
```

---

### Task 2: 目录重组（git mv）+ 全量路径引用改道

**Files:**
- Rename: `skills/public/bid-proposal-writing/` → `skills/public/bid-proposal-overall/`（整目录 git mv）
- Rename: `bid-proposal-overall/scripts/bank_compile.py` → `bid-technical/scripts/bank_compile.py`
- Rename: `references/{samples_bank/, bank_index.json, depth_targets.json, registration.json}` → `bid-technical/references/…`
- Rename: `references/tech_response_prompt.md` → `bid-technical/references/tech_response_prompt.md`
- Rename: `references/stage4-response-build.md` → `bid-technical/references/build-technical.md`（改名对齐 spec §3.1 B 清单）
- Modify: 测试/配置/邻接技能引用（下表逐项）

- [ ] **Step 1: git mv（保留历史，一次性完成）**

```bash
git mv skills/public/bid-proposal-writing skills/public/bid-proposal-overall
mkdir -p skills/public/bid-technical/scripts skills/public/bid-technical/references
git mv skills/public/bid-proposal-overall/scripts/bank_compile.py skills/public/bid-technical/scripts/bank_compile.py
git mv skills/public/bid-proposal-overall/references/samples_bank skills/public/bid-technical/references/samples_bank
git mv skills/public/bid-proposal-overall/references/bank_index.json skills/public/bid-technical/references/bank_index.json
git mv skills/public/bid-proposal-overall/references/depth_targets.json skills/public/bid-technical/references/depth_targets.json
git mv skills/public/bid-proposal-overall/references/registration.json skills/public/bid-technical/references/registration.json
git mv skills/public/bid-proposal-overall/references/tech_response_prompt.md skills/public/bid-technical/references/tech_response_prompt.md
git mv skills/public/bid-proposal-overall/references/stage4-response-build.md skills/public/bid-technical/references/build-technical.md
```

- [ ] **Step 2: build_output.py 两处值改道**

```python
MANIFEST_SKILL = "bid-proposal-overall"  # 交付契约属主=A(canonical scripts 所在); B build 更新同一 manifest 不翻转此字段
DEFAULT_DEPTH_TARGETS_PATH = Path(__file__).resolve().parents[2] / "bid-technical" / "references" / "depth_targets.json"  # 样例库基线在 B(pair-install 软读: 缺失=深度门跳过, 不构成硬反向依赖)
```

（`parents[2]`=skills/public；siblings 解析在容器 `/mnt/skills/public/` 下同样成立。）

- [ ] **Step 3: 测试文件路径常量与断言改道**（test_bid_proposal_scripts.py）

| 位置 | 改法 |
|---|---|
| L31 `SCRIPTS_DIR` | `"bid-proposal-writing"` → `"bid-proposal-overall"` |
| L483 `REFERENCES_DIR` | → `"bid-proposal-overall"`；紧随新增 `TECH_REFERENCES_DIR = REPO_ROOT / "skills" / "public" / "bid-technical" / "references"` |
| L6041 responses.schema 路径 | → `bid-proposal-overall` |
| L6287 `SKILL_MD_PATH` | → `bid-proposal-overall` |
| L6290 `_SKILL_SCRIPT_RE` | `bid-proposal-writing/scripts` → `bid-proposal-overall/scripts` |
| L6337-6338 REQUIRED_TOKENS 两条 `/mnt/...` 路径 | → `bid-proposal-overall` |
| L6389 frontmatter 断言、L6404/6405 速查表正则 | → `bid-proposal-overall` |
| L6502 `STAGE_GROUP_FILENAMES` | 拆两组：`A_STAGE_GUIDES = ("stage0-2-intake-extract.md", "stage3-merge-gate2.md", "stage5-scoring.md")`（A references）+ `B_STAGE_GUIDES = ("build-technical.md", "tech_response_prompt.md")`（TECH_REFERENCES_DIR）；存在性循环与 token maps 的 key `"stage4-response-build.md"` → `"build-technical.md"`（token map 读取目录按组切换） |
| 双向锁 snapshot 测试 | pinned 基名清单改为 `("stage0-2-intake-extract", "stage3-merge-gate2", "stage5-scoring", "build-technical")` |
| L7346 / L7432 `manifest["skill"]` 断言 | → `"bid-proposal-overall"` |

- [ ] **Step 4: 其余测试/驱动改道**

- `test_bank_compile.py`：`SCRIPTS_DIR` → `"bid-technical"`。
- `test_bid_materials.py` L553 注释 + L558 `SCRIPTS_DIR` → `"bid-proposal-overall"`（深度门测的是 build_output/responses，都在 A）。
- `backend/tests/e2e/bid/score_checkpoints.py` L38 `SCRIPTS` → `"bid-proposal-overall"`；L1/L291 描述文案。
- `backend/tests/e2e/bid/e2e_bid_driver.py` L1 docstring / L64 T1 提示词 / L517 argparse 描述 → `bid-proposal-overall`（T1 文案改"请使用 bid-proposal-overall 技能…技术卷部分使用 bid-technical 技能"）。
- `backend/tests/fixtures/bid_proposal/gen_fixtures.py` L2/L465 技能名文案（L4 的历史 spec 路径**保留**）。
- `backend/tests/conftest.py` L212 注释 → `bid-proposal-overall`。

- [ ] **Step 5: 配置与邻接技能改道**

- `extensions_config.json` 与 `deploy/offline/extensions_config.json`（两份同步）：`"bid-proposal-writing"` 键 → `"bid-proposal-overall"`，并新增 `"bid-technical": {"enabled": true}`。
- `skills/public/bid-proposal-overall/scripts/snapshot.py`：L81-82 docstring 四指南清单与 L101/102/107 next_step 文案中 `见 stage4-response-build` → `见 bid-technical 的 build-technical`（技术响应指引改指 B）。
- `skills/public/ops-diagnosis/SKILL.md` L12 / `references/failure-signatures.md` L27 / `scripts/_common.py` L30：技能名 → `bid-proposal-overall`（rc=3 契约属主）。
- `backend/docs/OBSERVABILITY.md` L323 示例文案 → `bid-proposal-overall`。
- `skills/public/bid-proposal-overall/SKILL.md`（机械改道，Task 3 再内容重写）：frontmatter `name:` → `bid-proposal-overall`；标题行；速查表全部 `/mnt/skills/public/bid-proposal-writing/` → `/mnt/skills/public/bid-proposal-overall/`（build 命令此步不加 --docs，Task 3 加）。
- **A references 内部残留**（已核实）：`stage0-2-intake-extract.md` 4 处 `/mnt/skills/public/bid-proposal-writing/scripts/` 命令路径 → `bid-proposal-overall`；四个 schema 的 `$id` URL（clauses/responses/rubric/structure.schema.json L3）→ `bid-proposal-overall`。
- **B references 内部残留**（同法核对）：`tech_response_prompt.md` 与 `build-technical.md` 内若引用 `/mnt/skills/public/bid-proposal-writing/`（responses.py 等命令示例）→ `bid-proposal-overall`（B 调 A 脚本的绝对路径正确形态）。
- bank_compile.py 顶部 docstring 中 `skills/public/bid-proposal-writing` 若有自指 → `bid-technical`（核对后改）。

- [ ] **Step 6: 全套件绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_proposal_scripts.py tests/test_bank_compile.py tests/test_bid_materials.py tests/test_delivery_contract_gates.py -v`
Expected: 全 PASS（路由双向锁此步仍绿——A SKILL.md 文本还点名 stage4 文件名，Task 3 才收口）

残留复核（应只剩历史文档/史述）：`grep -rn "bid-proposal-writing" skills/ backend/tests/ extensions_config.json | grep -v "docs/superpowers\|docs/designs\|test_delivery_contract_gates"` → 期望零命中。

- [ ] **Step 7: Commit**

```bash
git add -A skills/public backend/tests extensions_config.json deploy/offline/extensions_config.json backend/docs/OBSERVABILITY.md
git commit -m "refactor(bid-materials): 技能目录重组 bid-proposal-overall+bid-technical(路径引用全量改道)"
```

---

### Task 3: Skill A SKILL.md 内容改写 + 新指南 build-overall.md

**Files:**
- Modify: `skills/public/bid-proposal-overall/SKILL.md`（整文件替换，全文见下）
- Create: `skills/public/bid-proposal-overall/references/build-overall.md`
- Test: `backend/tests/test_bid_proposal_scripts.py`（先改断言表达新契约：A 点名 3 份 stage 指南 + build-overall；REQUIRED_TOKENS 去 `tech_response_prompt.md` 加 `build-overall.md` 与 `--docs overall`；路由表测试同步）

- [ ] **Step 1: 先改测试表达新契约（跑失败）**

A 侧断言改法：`STAGE_GROUP_FILENAMES`（A 组）→ `("stage0-2-intake-extract.md", "stage3-merge-gate2.md", "build-overall.md", "stage5-scoring.md")`；`SKILL_MD_REQUIRED_TOKENS` 中 `"tech_response_prompt.md"` → `"build-overall.md"`，并加 `"--docs overall"`。Run 既有 SKILL 契约测试 → Expected FAIL（SKILL.md 还是旧文）。

- [ ] **Step 2: 替换 A SKILL.md 全文**（≤120 行预算；铁律/借口表/红线等正文块**逐字保留**，以下 `…` 处即原文件对应块原样照搬）

```markdown
---
name: bid-proposal-overall
description: 当用户需要编制投标整体方案(分析招标文件、义务清单、商务全量响应骨架、补遗合并、整体方案册集 build、模拟评分)时使用此技能。把招标文件(含答疑/补遗)转化为带原文锚点的机器可核对义务清单,产出整体方案册集(商务全量+技术占位页)与偏离表,并按评分办法模拟评分。技术卷逐条款响应编制在配对技能 bid-technical。
---

# 投标整体方案技能(bid-proposal-overall, 原 bid-proposal-writing 商务主线)

本文件=编排总纲+唯一合法命令来源;各阶段流程细节、状态文件表、排错表在 references/ 的**分组执行指南**里,进入对应阶段先读对应那份(见阶段路由表)。

## 概述与分工(配对技能 pair-install)

把**招标文件**变成**机器可核对的义务清单**(逐条分类/锚定原文),产出整体方案册集(商务全量+技术占位页)与偏离表,终稿前按评分办法模拟打分。分工:脚本=确定性工作(全部管线脚本不调 LLM);Agent=编排+上下文内 LLM 循环(可审计、每步候选落盘);两道人工确认门(清单锁定/补遗+终稿复核),Agent 不替用户做废标级决定。

**配对技能 bid-technical(B)**:技术卷编制(技术条款逐条响应:样例检索/编造+深度目标、progress 章门、build --docs technical)。B 消费本技能的 scripts/ 与 workspace/state(同一项目权威态,clauses/structure/responses 同源),两技能 outputs/ 同目录,合并语义见 build-overall.md。B 未跑时技术章渲染占位页(合法态)。

## 铁律(违反任何一条立即停下)

…（原铁律 1-10 逐字保留，第 9 条 state_guard 路径、第 6 条 snapshot 指引不变）…

贯穿红线(双轨):…（原文逐字保留）…

## 借口→现实(出现该念头=已偏轨)

…（原表逐字保留）…

红旗即停:…（原文逐字保留）…

## 管线总览:五阶段(A 线) + 两道确认门

```
阶段0 输入受理(分流:docx/pdf/扫描件;补遗标记)
  → 阶段1 ingest(纯结构化 → sections.json)
  → 阶段2 extract(分块提取循环 → 候选落盘 → extract.py 校验/合并)
──── 确认门1:计数+异常项+完整清单工件+clause_id 改分类回写+实体白名单锁定 ────
  → 阶段3 merge(补遗/答疑:ingest --addendum → 提取循环 → merge_addenda.py 落账)
  → 阶段4a 技术响应生成 ——【配对技能 bid-technical 执行,见其 SKILL.md】
  → 阶段4 build(build_output.py --docs overall:整体方案册集+索引卷整体方案节 → present_files;
      --docs all 全量并重建副表)
──── 确认门2:补遗 diff 表+终稿复核清单(B 技术卷就绪后一并复核) ────
  → 阶段5 模拟评分(双形态对齐 → 主观评审循环 → aggregate → report version++)
  # 阶段0-3+5 主线各走一遍;阶段5 团队回传后可重跑,每次 version++ 留痕
```

## 路径与契约文档

- 脚本(沙箱路径):`/mnt/skills/public/bid-proposal-overall/scripts/` 下十个 Python 模块(ingest/extract/merge_addenda/check_format/responses/build_output/score_simulate + snapshot + state_guard + progress),全部 argparse CLI、纯 Python 3.12、不调 LLM;booklets.py 为 build_output 内部分册模块(无 CLI)。**全量脚本 canonical 在本技能**,bid-technical 经绝对路径调用。
- 契约文档:`/mnt/skills/public/bid-proposal-overall/references/` —— 四份分组执行指南(stage0-2-intake-extract / stage3-merge-gate2 / build-overall / stage5-scoring)+ 四个 JSON Schema(clauses/structure/rubric/responses)+ classification.md + extraction_prompt.md + scoring_prompt.md。技术卷指南(tech_response_prompt / build-technical)在配对技能 bid-technical/references/。
- 状态目录:建议 `/mnt/user-data/workspace/bid/`(其下 state/ 权威态、candidates/ 候选 checkpoint);交付 md 与确认门工件放 `/mnt/user-data/outputs/`(present_files 只认这个目录)。

### 命令速查表(唯一合法调用形态——逐字照抄,换路径只换路径)

```bash
python /mnt/skills/public/bid-proposal-overall/scripts/ingest.py --input /mnt/user-data/uploads/招标文件.docx --code ZB --out /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/ingest.py --input /mnt/user-data/uploads/补遗01.docx --code BY --addendum --out /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/ingest.py --resume --out /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/extract.py validate --candidates /mnt/user-data/workspace/bid/candidates/CH-001.clauses.json /mnt/user-data/workspace/bid/candidates/T-001.rubric.json --sections /mnt/user-data/workspace/bid/state/sections.json --declared-total 100
python /mnt/skills/public/bid-proposal-overall/scripts/extract.py merge --candidates /mnt/user-data/workspace/bid/candidates/CH-001.clauses.json --sections /mnt/user-data/workspace/bid/state/sections.json --state-dir /mnt/user-data/workspace/bid/state --declared-total 100
python /mnt/skills/public/bid-proposal-overall/scripts/check_format.py --state-dir /mnt/user-data/workspace/bid/state --sources /mnt/user-data/uploads/招标文件.md
python /mnt/skills/public/bid-proposal-overall/scripts/responses.py validate --candidates /mnt/user-data/workspace/bid/candidates/RESP-tech-001.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/responses.py merge --candidates /mnt/user-data/workspace/bid/candidates/RESP-tech-001.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/merge_addenda.py --addendum-candidates /mnt/user-data/workspace/bid/candidates/BY_addendum.json --state-dir /mnt/user-data/workspace/bid/state --decisions /mnt/user-data/workspace/bid/candidates/BY_decisions.json
python /mnt/skills/public/bid-proposal-overall/scripts/build_output.py --state-dir /mnt/user-data/workspace/bid/state --out /mnt/user-data/outputs/投标文件 --docs overall
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py init --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py next --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py gate --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py mark C-01 DRAFTED --state-dir /mnt/user-data/workspace/bid/state --detail 处置完成
python /mnt/skills/public/bid-proposal-overall/scripts/score_simulate.py reingest --source /mnt/user-data/uploads/投标文件-技术卷-回传.md --state-dir /mnt/user-data/workspace/bid/state --volume technical
python /mnt/skills/public/bid-proposal-overall/scripts/score_simulate.py assemble-evidence --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/score_simulate.py aggregate --scores /mnt/user-data/workspace/bid/candidates/subjective_scores_v1.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/score_simulate.py report --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/snapshot.py --workspace /mnt/user-data/workspace/bid --project 项目名称 --code ZB=招标文件
python /mnt/skills/public/bid-proposal-overall/scripts/state_guard.py sign --state-dir /mnt/user-data/workspace/bid/state --files clauses.json --confirm-gate1-edit
python /mnt/skills/public/bid-proposal-overall/scripts/state_guard.py verify --state-dir /mnt/user-data/workspace/bid/state
```

**防幻觉契约(回放实证,违者即停)**:A/B 两份速查表之外**不存在**任何脚本或子命令(bid-technical 的离线工具 bank_compile.py 不进速查表)。特别地:`extract_clauses.py`、`check.py`、`trace.py` 之类文件名**不存在**;extract 子命令只有 `validate`/`merge`,responses 只有 `validate`/`merge`/`confirm-hnv`,score_simulate 只有 `reingest`/`assemble-evidence`/`aggregate`/`report`,progress 只有 `init`/`next`/`status`/`mark`/`gate`/`mark-build-done`,ingest/merge_addenda/check_format/build_output/snapshot/state_guard 无子命令(build_output 只有 `--docs` 旗标)。记不准就先跑 `<脚本> --help`。所有命令用**绝对路径**执行,不 `cd`。

## 阶段路由表(进入阶段先读对应分组指南)

| 阶段 | 入口条件 | 必读指南(references/) | 产出·完成判据 |
|---|---|---|---|
| 阶段0 受理 / 阶段1 ingest / 阶段2 extract / 确认门1 | 首跑,或 snapshot phase ∈ {0-受理, 2-提取中, 确认门1-待锁定} | stage0-2-intake-extract.md | sections.json + clauses/structure/rubric.json + 实体白名单锁定 |
| 阶段3 补遗合并 / 确认门2 | 门1 已过,或补遗/答疑到达 | stage3-merge-gate2.md | merge_ledger.json + 补遗 diff 表逐项确认 + 终稿复核清单 |
| 阶段4a 技术响应生成 / 技术卷 build | 门1 已过 | 【配对技能 bid-technical:其 SKILL.md + build-technical.md】 | responses.json + 技术卷册集(--docs technical) |
| 阶段4 build(整体方案) | 门1 已过(技术卷可后补) | build-overall.md | 整体方案册集(--docs overall)+ 索引卷 + 副表(all 时)+ last_build.json |
| 阶段5 模拟评分 | 门2 已过,有填写态或团队回传 | stage5-scoring.md | 评分报告 version_N.md + 改进建议(可重跑)。单卷回传必须显式 `--volume commercial\|technical` |

- 退出码(五脚本统一约定):`0`=干净完成;`1`=用法/文件错误(**例外**:score_simulate 的 Σ 不一致中止与重灌降级拒绝计分也归 `1`——同条件在 extract 侧是 `3` 完成带异常,编排时勿把该 `1` 当单纯文件错;**签名校验失败也归 `1`**,按错误行恢复指令重建,不试错绕行);`2`=**仅 ingest**:存在无文本层输入(扫描件)需走 eai-flow-ocr;`3`=完成但有异常项——**退出码 3 不是失败**,必须读脚本 stdout 的单行 JSON 摘要,把 `anomalies` 逐项呈现给用户,绝不静默吞掉。

## 快照与上下文纪律

…（原文逐字保留）…

## 排错一级索引(症状→对应指南的排错表,不试错绕行)

- 通用(路径/参数/签名校验失败/退出码 2、3/熔断/present_files 拒绝)与格式保真异常(check_format.py):stage0-2-intake-extract.md 排错表
- 补遗落账(pending 待裁决/锚点 mismatch/悬挂外键/台账 skipped):stage3-merge-gate2.md 排错表
- 响应校验(citations 缺失/thin/boilerplate/placement)/技术卷渲染异常:bid-technical 的 build-technical.md 排错表
- build --docs 合并语义/清场收窄/副表归属/占位页接缝:build-overall.md 排错表
- 评分(整体降级/多命中/Σ 不一致/未重灌矛盾):stage5-scoring.md 排错表
- 记不准命令/参数:防幻觉契约 + `<脚本> --help`,绝不凭记忆造

## 注意事项

…（原文两条逐字保留）+ 追加一条:
- 与 bid-technical 为 pair-install(B 消费本技能 scripts 与 state,不可独立分发);本技能 build 默认 `--docs overall` 只动整体方案组,技术卷册由 B 维护——禁止用 `--docs all` 单方面重建副表覆盖 B 已交付内容之外的场景(副表聚合两卷,all 重建是唯一合法入口,重建前确认 B 响应已 merge)。
```

（执行注意:`…` 占位处从 git 历史原文件逐字搬运;改完后 `wc -l` ≤120,超了先砍注意事项追加条的措辞。）

- [ ] **Step 3: 新建 references/build-overall.md**（全文）

```markdown
# 阶段4: 整体方案册集 build(--docs overall)分组执行指南

进入条件: 确认门1 已过(snapshot `phase` ∈ {3/4-合并与构建})。命令照抄 SKILL.md 速查表; 本文讲 --docs 范围语义与判据, 不重复罗列调用。

## 调用与范围(spec §3.2)

- `build_output.py --state-dir … --out … --docs overall`: 只重写整体方案册组 + 索引卷整体方案节。
- `--docs all`(默认): 两组全量 + 索引全量 + 四张副表(偏离表/覆盖率报表/人核清单/实体lint报告——跨两卷聚合, all 专责重建)。
- `--docs technical` 属配对技能 bid-technical, 本技能不发起。

## 合并语义(两技能共享 outputs/ 的契约)

1. **manifest 合并**: 读既有 delivery_manifest.json → 本次范围内条目更新, 范围外原样保留(deliverables/files/docs 三处); `skill` 字段恒=`bid-proposal-overall`(契约属主, B build 不翻转)。
2. **清场收窄**: 只删本次范围前缀的 stale 册(overall=`整体方案-*`; all=两组+副表+v3 遗留); 范围外 stale 留给对应技能自清——A 不清 B 的技术卷册。
3. **索引卷分区重写**: 未重建册组节以盘上既有索引原样保留(含旧节头/计数); 盘上无既有索引/该节缺席 → 该节略去(该组从未 build 是合法态)。
4. **交付契约标记与凭据**: 任一范围 build 成功即激活/更新 `.delivery-contract` 与 manifest(线程级, 不受 --docs 影响); 实体门 blocked → 不写凭据且作废旧凭据/标记(处置见排错)。

## 与 bid-technical 的接缝(spec §3.3)

- 整体方案技术章渲染**占位页**(逐字章标题+技术卷分册目录+指引, 零技术正文内联); 分册目录以当前 state 投影——B 未 build 时占位页即"技术卷编制中"合法态。
- B build --docs technical 后重跑本技能 --docs overall 可刷新占位页目录; 册文件确定性幂等, 重跑字节一致。

## 排错

- 实体门 blocked: 本轮不写凭据, 交付门全禁 .md——处置路径: 确认候选白名单入册(见 实体lint报告.md)或回 B 的 stage4a 重写响应后重跑。
- 深度异常(depth_below_target/depth_below_floor): 质量牵引非废标风险, 只进 实体lint报告.md"深度"节与摘要 anomalies; 基线缺失=门跳过(skip_reason 随摘要呈现, bid-technical/references/depth_targets.json 未编译是合法初态)。
- `--docs` 非法值: argparse 拒绝 → 退出码 1(与其它用法错误同通道)。
- 退出码 3=完成但有异常项: 读 stdout 单行 JSON 摘要逐项呈现, 不是失败。
```

- [ ] **Step 4: 跑 SKILL 契约测试 + 全 bid 套件绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_proposal_scripts.py -v`
Expected: 全 PASS（含 ≤120 行预算、路由双向锁、速查表防幻觉正则）

- [ ] **Step 5: Commit**

```bash
git add skills/public/bid-proposal-overall backend/tests/test_bid_proposal_scripts.py
git commit -m "docs(bid-materials): A SKILL.md 改写(bid-proposal-overall)+build-overall 指南(--docs 语义)"
```

---

### Task 4: Skill B 落地（SKILL.md + tech_outline_packs 骨架 + build-technical.md 内容收口）

**Files:**
- Create: `skills/public/bid-technical/SKILL.md`（全文见下）
- Create: `skills/public/bid-technical/references/tech_outline_packs/README.md`（16 类骨架登记, pack 文件后续填充）
- Modify: `skills/public/bid-technical/references/build-technical.md`（头部+build 节改写, 见 Step 2 的三处编辑）
- Test: `backend/tests/test_bid_proposal_scripts.py`（B_STAGE_GUIDES 的 build-technical.md REQUIRED_TOKENS 追加 `--docs technical`）

- [ ] **Step 1: 建 tech_outline_packs/README.md**（全文）

```markdown
# tech_outline_packs——技术卷大纲骨架包(16 类, 后续填充)

用途(spec §3.3): 技术卷 TOC 自拟的分类骨架层——分类器判定项目类别 → 装载 `<类别>.json`
→ 招标技术要求/评分办法按评分项关键词聚类实例化 → 对话确认门。依据调研:
docs/designs/bid-tech-outline-packs-research.md。

## 16 类登记(状态=待填充; 文件名=本表 slug)

| slug | 类别 | 调研 confidence |
|---|---|---|
| engineering | 工程类(施工总承包主骨架) | 9/10 |
| goods | 货物类(设备/物资采购主骨架) | 7/10 |
| services | 服务类(勘察/设计/监理/咨询主骨架) | 8/10 |
| it-platform | 信息系统/软件平台类(主骨架) | 7/10 |
| construction | 工程施工类(房建/市政施组) | 9/10 |
| epc | EPC 工程总承包类 | 7/10 |
| design | 工程设计类 | 8/10 |
| goods-general | 通用供货类 | 8/10 |
| goods-medical | 医疗设备采购类 | 7/10 |
| goods-heavy | 大型机械装备/成套设备类 | 7/10 |
| it-full | IT 软件平台与系统集成(详版·方案型) | 9/10 |
| it-lite | IT 信息化(简版·响应型) | 7/10 |
| it-ops | IT 运维服务类 | 9/10 |
| supervision | 工程监理服务类 | 8/10 |
| consulting | 咨询服务类 | 7/10 |
| inspection | 检验检测服务类 | 6/10 |

## pack 文件形态(填充时遵守)

`<slug>.json`: `{"slug": …, "类别": …, "aliases": […], "chapters": [{"no": 1, "title": …,
"notes": …}], "source": "调研文档节名"}`——章纲=调研文档对应表逐行; 填充后在本表状态列
改"已填充"。骨架是**大纲候选素材**, 不直接写盘 state(见 SKILL.md B1 v1 边界)。
```

- [ ] **Step 2: build-technical.md（原 stage4 指南）三处编辑**

2a. 标题与进入条件（首 3 行）改为：

```markdown
# 阶段B: 技术卷编制指南(供源级联响应生成 → progress 章门 → build --docs technical)

进入条件: 配对技能 bid-proposal-overall 的确认门1 已过(snapshot `phase` ∈ {3/4-合并与构建}); 补遗到达时先走 A 的 stage3-merge-gate2 再回来。本指南属 bid-technical(B); A 侧整体方案 build 见 A 的 build-overall.md。
```

2b. 正文所有 `阶段4a` 字样 → `阶段B2`(逐处替换), build 小节的旗标表述改为 `--docs technical`(命令示例同步); 文中"两文档册集/六件套"表述改为"技术卷册组+索引卷技术卷节(manifest 合并语义: 范围外册/副表不触碰, 索引未重建节原样保留——详见 A 的 build-overall.md)"。

2c. 排错表追加一行: `- 整体方案册/副表在本技能 build 后"未变": 这是收窄语义不是故障——副表只在 A 的 --docs all 重建; 需刷新副表请回 A 发起 --docs all。`

- [ ] **Step 3: 建 SKILL.md**（全文, ≤120 行）

```markdown
---
name: bid-technical
description: 当用户需要编制投标技术卷(技术条款逐条响应、样例库检索仿写/编造+深度目标校准、响应校验落账、章节进度章门、技术卷分册 build 交付)时使用此技能。依赖配对技能 bid-proposal-overall(A)的管线脚本与 workspace 权威态(pair-install, 不可独立分发); 招标文件义务清单提取/整体方案/模拟评分在 A。
---

# 投标技术卷技能(bid-technical, 纯编排——脚本 canonical 在 bid-proposal-overall)

## 前置与分工

- **前置**: A 的阶段0-3 已过确认门1——`clauses.json`/`structure.json`/`entities_whitelist.json` 就绪(snapshot `phase` ∈ {3/4-合并与构建})。缺前置回 A 走阶段0-3, **不代做**。
- **B 负责**: B1 技术卷大纲自拟 → B2 供源级联逐条款响应(4a) → B3 progress 章门 → B4 build `--docs technical`。
- **脚本**: 全部管线脚本在 `/mnt/skills/public/bid-proposal-overall/scripts/`(速查表见 A; 本文件速查表只列 B 常用子集)。本技能 scripts/ 仅 `bank_compile.py`——**离线维护者工具**(样例入库编译: 脱敏→切片→深度基线→RAGFlow 推送), 不进 Agent 速查表、运行时不调用。

## 铁律(继承 A 全部铁律——state 防改/失败熔断/反弃线/快照纪律同 A, 附加三条)

1. state/ 权威文件只由 A 的管线脚本写盘并签名; B 不新增任何直写途径, 签名校验失败按错误行恢复, 不试错绕行。
2. 响应完备性>溯源性(双轨): 样例库仿写优先→样例库没有**直接编造**合法且必要(标 `fabricated` 全量进人核); **四类硬围栏绝不编造**(报价数字/资质证号/公司实体名(白名单外)/招标原文引用)。
3. `depth_target` 只在样例命中组写(命中段实质长 median 取整), 编造/self 候选不写——不拍脑袋估数; 未写者落库级 absolute_floor 兜底。

## 工作流

### B0 前置核验
跑 A 速查表 snapshot.py 读 `phase`; 确认 clauses/structure/whitelist 在位。

### B1 技术卷大纲自拟(v1 对话协议, 无 UI)
- 输入: A 的 extract 活条款(`category ∈ {technical, service}`)+评分办法条款+`references/tech_outline_packs/` 骨架(16 类登记见其 README; pack 未填充的类别按评分办法关键词自行拟章组)。
- 按评分项关键词把条款聚到骨架类别(确定性关键词匹配起步, 聚类质量进人核)。
- 产出: `candidates/tech_outline.candidates.md`(章组→clause_id 组映射+骨架偏差说明), 对话呈现**确认后**才作为响应推进的组织视图。
- **v1 边界**: 技术卷章结构仍以 structure.json 技术章为准渲染; 大纲自拟当前只组织响应推进次序与章组检索批, 不直写 structure.json(结构化大纲→structure 扩写为后续计划)。

### B2 供源级联响应生成
开始前**先读全篇** `references/tech_response_prompt.md` + `references/build-technical.md`。级联(逐条款按序, 不跳步): 第一层样例库检索(按章组批量, RAGFlow filters; 命中→仿写+写 `depth_target`+`needs_human_verify=true`)→无命中**直接编造**(合法默认, 标 `fabricated`)→self 重组。候选 JSON 即刻落盘 `candidates/`, 逐批跑 A 速查表 `responses.py validate` + `merge`。脱敏语料的 `****` 是掩码: 引用片段避开掩码段, 绝不照抄掩码形态进正文。

### B3 progress 章门
A 速查表 `progress.py init` → 逐章推进 `next`/`mark` → `gate`; FAIL detail 回 B2 补写。深度异常(depth_below_target/depth_below_floor)是质量牵引非废标阻断, 按 build-technical.md 排错处置。

### B4 build --docs technical
A 速查表 `build_output.py … --docs technical`: 只重写技术卷册组+索引卷技术卷节; 整体方案册/副表不触碰(manifest 合并)。交付 present_files 后**确认门2 回 A 走**(补遗 diff+终稿复核两技能一并)。模拟评分在 A(阶段5), B 不产评分报告。

## 命令速查表(B 常用子集——脚本 canonical 在 A, 绝对路径照抄)

```bash
python /mnt/skills/public/bid-proposal-overall/scripts/responses.py validate --candidates /mnt/user-data/workspace/bid/candidates/RESP-tech-001.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/responses.py merge --candidates /mnt/user-data/workspace/bid/candidates/RESP-tech-001.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py init --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py next --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py gate --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-overall/scripts/progress.py mark C-01 DRAFTED --state-dir /mnt/user-data/workspace/bid/state --detail 处置完成
python /mnt/skills/public/bid-proposal-overall/scripts/build_output.py --state-dir /mnt/user-data/workspace/bid/state --out /mnt/user-data/outputs/投标文件 --docs technical
python /mnt/skills/public/bid-proposal-overall/scripts/snapshot.py --workspace /mnt/user-data/workspace/bid --project 项目名称 --code ZB=招标文件
python /mnt/skills/public/bid-proposal-overall/scripts/state_guard.py verify --state-dir /mnt/user-data/workspace/bid/state
```

**防幻觉契约**: A/B 两份速查表之外不存在任何脚本或子命令; 子命令清单以 A 速查表为准。记不准先跑 `<脚本> --help`。所有命令绝对路径, 不 `cd`。

## 排错一级索引

- 响应校验(citations/thin/boilerplate/placement/深度门)/技术卷渲染: build-technical.md 排错表
- 通用(路径/签名/退出码 2、3/熔断): A 的 stage0-2-intake-extract.md 排错表
- 整体方案册"没被本技能 build 改动": 收窄语义不是故障(副表只在 A 的 --docs all 重建)
- 样例入库(bank_compile 残留扫描 rc=1 不出库): 维护者离线操作, 见 scripts/bank_compile.py docstring

## 注意事项

- 不调外部标书 SaaS, 招标文件与标书不出内网; 样例库供源以 RAGFlow bid_samples 域为准(bank_compile 可选推送), 未建库直接编造(完备性优先)。
- 主观评分与商务全量镜像在 A; B 交付物=技术卷册组, 与 A 的整体方案册同目录、manifest 合并、互不清场。
```

- [ ] **Step 4: 测试同步**（build-technical.md REQUIRED_TOKENS 加 `--docs technical`；B_STAGE_GUIDES 存在性/token 循环指向 TECH_REFERENCES_DIR 已在 Task 2 就位）→ 跑全 bid 套件绿

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_proposal_scripts.py tests/test_bank_compile.py -v`

- [ ] **Step 5: Commit**

```bash
git add skills/public/bid-technical backend/tests/test_bid_proposal_scripts.py
git commit -m "feat(bid-materials): Skill B bid-technical 落地(SKILL.md+大纲自拟+tech_outline_packs 16类登记)"
```

---

### Task 5: 两 SKILL.md 契约测试（spec §6）

**Files:**
- Test: `backend/tests/test_bid_proposal_scripts.py`（末尾新增）

- [ ] **Step 1: 写测试**（应直接全绿——前四个 Task 已把契约做实；若有红即前序任务的漏网断言，就地修）

```python
# ===========================================================================
# Skill 拆分契约(spec §6): bid-proposal-overall / bid-technical 两 SKILL.md
# ——路由表/速查表/行数预算各自独立; B pair-install(消费 A scripts, 不可独立分发)
# ===========================================================================
BID_OVERALL_DIR = REPO_ROOT / "skills" / "public" / "bid-proposal-overall"
BID_TECHNICAL_DIR = REPO_ROOT / "skills" / "public" / "bid-technical"
_QUICKREF_SCRIPT_RE = re.compile(r"/mnt/skills/public/(bid-proposal-overall|bid-technical)/scripts/([a-z_]+)\.py")


class TestTwoSkillSplitContract:
    def _skill_md(self, skill_dir):
        path = skill_dir / "SKILL.md"
        assert path.is_file(), f"{path} 缺失"
        return path.read_text(encoding="utf-8")

    def test_frontmatter_names_match_dirs(self):
        for skill_dir, name in ((BID_OVERALL_DIR, "bid-proposal-overall"), (BID_TECHNICAL_DIR, "bid-technical")):
            assert re.search(rf"^name:\s*{name}\s*$", self._skill_md(skill_dir), re.MULTILINE), f"{skill_dir.name} frontmatter name 必须为 {name}"

    def test_technical_is_orchestration_only(self):
        """spec §3.1: B 纯编排技能, scripts/ 只允许 bank_compile(离线维护者工具)。"""
        scripts = sorted(p.name for p in (BID_TECHNICAL_DIR / "scripts").glob("*.py"))
        assert scripts == ["bank_compile.py"], f"bid-technical/scripts 只允许 bank_compile.py, 实际 {scripts}"

    def test_technical_quickref_targets_pair_scripts(self):
        """pair-install 契约: B 速查表管线命令全部指向 A 脚本绝对路径; bank_compile 不进速查表。"""
        commands = [ln.strip() for ln in self._skill_md(BID_TECHNICAL_DIR).splitlines() if ln.strip().startswith("python /mnt/skills/")]
        assert commands, "B 速查表不得为空"
        for cmd in commands:
            assert "/mnt/skills/public/bid-proposal-overall/scripts/" in cmd, f"B 管线命令必须指向 A 脚本: {cmd}"
            assert "bank_compile" not in cmd, "bank_compile 是离线维护者工具, 不进 Agent 速查表"

    def test_quickref_scripts_exist_on_disk(self):
        """两份速查表点名的脚本文件必须真实存在(防幻觉命令)。"""
        for skill_dir in (BID_OVERALL_DIR, BID_TECHNICAL_DIR):
            for m in _QUICKREF_SCRIPT_RE.finditer(self._skill_md(skill_dir)):
                target = REPO_ROOT / "skills" / "public" / m.group(1) / "scripts" / f"{m.group(2)}.py"
                assert target.is_file(), f"{skill_dir.name} 速查表点名不存在的脚本: {target}"

    def test_build_docs_flag_in_both_quickrefs(self):
        for skill_dir, flag in ((BID_OVERALL_DIR, "--docs overall"), (BID_TECHNICAL_DIR, "--docs technical")):
            assert flag in self._skill_md(skill_dir), f"{skill_dir.name} 速查表 build 命令须带 {flag}"

    def test_referenced_reference_files_exist(self):
        """SKILL.md 以 references/ 前缀点名的文件在对应技能内真实存在(路由不悬空)。"""
        for skill_dir in (BID_OVERALL_DIR, BID_TECHNICAL_DIR):
            for ref in set(re.findall(r"references/([A-Za-z0-9_\-]+\.(?:md|json))", self._skill_md(skill_dir))):
                assert (skill_dir / "references" / ref).is_file(), f"{skill_dir.name} 点名 references/{ref} 不存在"

    def test_line_budgets_independent(self):
        """行数预算各自独立(spec §6): 两份 SKILL.md 各 ≤120 行。"""
        for skill_dir in (BID_OVERALL_DIR, BID_TECHNICAL_DIR):
            n = len(self._skill_md(skill_dir).splitlines())
            assert n <= 120, f"{skill_dir.name}/SKILL.md 超预算: {n} > 120"
```

- [ ] **Step 2: 跑测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_proposal_scripts.py::TestTwoSkillSplitContract -v`
Expected: 8 passed

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_bid_proposal_scripts.py
git commit -m "test(bid-materials): 两 SKILL.md 契约测试(路由/速查/行数预算各自独立+pair-install)"
```

---

### Task 6: 全量回归 + 台账修正 + 文档收尾 + 推送

- [ ] **Step 1: 全量回归 + lint**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_proposal_scripts.py tests/test_bank_compile.py tests/test_bid_materials.py tests/test_delivery_contract_gates.py -v
cd backend && make lint
```
Expected: 全 PASS / ruff 干净。另跑 `grep -rn "bid-proposal-writing" skills/ backend/tests/ extensions_config.json` 复核：剩余命中只允许是历史 spec/design 路径、test_delivery_contract_gates.py（自构 manifest）与 prose 史述。

- [ ] **Step 2: BidSample 台账 source_path 修正**（Plan 2 已入库 3 行指向旧路径）

```bash
docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "UPDATE bid_samples SET source_path = replace(source_path, 'skills/public/bid-proposal-writing/', 'skills/public/bid-technical/'), updated_at = now() WHERE source_path LIKE 'skills/public/bid-proposal-writing/%';"
docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "SELECT title, source_path FROM bid_samples;"  # 核对 3 行全部指向 bid-technical
```

- [ ] **Step 3: 文档收尾**

- `开发日志.md` 追加本计划完成条目（一段：拆分+--docs+两 SKILL.md+台账修正）。
- `deploy/offline/UPGRADE-v20260906-cutover.md` 追加一行：技能目录改名+新增 bid-technical=离线模板变更，delta 镜像不可覆盖，须全量重打包（既有约定）。

- [ ] **Step 4: 推送 + rev-list 0/0**

```bash
git push origin main-dev-fork; git fetch origin; git rev-list --left-right --count origin/main-dev-fork...HEAD
```
Expected: `0	0`（push flaky 时按既有 postBuffer+重试手法）

---

## 后续计划（本文档不覆盖）

- **Plan 4**: 前端 bid-materials 页面（镜像 coal-eia-samples 双层形态）。
- **tech_outline_packs 16 类 pack 填充**（按 README 形态逐类落 json, 调研文档已备章纲）。
- **大纲自拟结构化**(B1 v1 边界升级: 确认后大纲→structure.json 扩写, 需新脚本+签名通道)——另立计划。
- **agnes E2E clean4 复跑**(spec §7.6: A+B 双入口真实走查, 需活网关, 人工/专项执行)。
- T6b 完结: 深度门章角色级校准随样例库语料增长演进(spec §8 记录不做)。
