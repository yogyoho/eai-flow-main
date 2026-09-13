"""规则注册表 fail-closed 测试（tmp_path 注入目录）.

EAI-CUSTOM: plan docs/superpowers/plans/2026-09-13-ontology-reasoning-rules.md Task 2 Step 2.1。
镜像 test_ontology_registry.py 的 copytree+显式参数注入模式; 谓词/etype 枚举用真源
（registry/doc_graph.yaml copy → load_registry → 注入 load_rules(rules_dir, reg=...)）。
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from app.extensions.ontology.doc_graph.reasoning.rule_registry import (
    RULES_DIR,
    RulesError,
    RuleStore,
    load_rules,
)
from app.extensions.ontology.registry import REGISTRY_DIR, load_registry

MANIFEST_YAML = textwrap.dedent("""\
    schema_version: 1
    files:
      - file: eia.yaml
    """)

GOOD_YAML = textwrap.dedent("""\
    rules:
      - name: demo_org_involved_in_mine
        enabled: true
        domain: eia
        when:
          - "org_develops_project(?ORG, ?PROJ)"
          - "mine(?MINE)"
        derive: "org_involved_in(?ORG, ?MINE)"
        note: "演示规则：开发主体参与其项目下矿井（验证底座，非业务定案）"
      - name: demo_disabled_rule
        enabled: false
        domain: eia
        when:
          - "org_compiles_project(?ORG, ?PROJ)"
        derive: "org_involved_in(?ORG, ?PROJ)"
        note: "disabled 规则：全量可查但不参与推理"
    """)


def _make_reg(tmp_path: Path):
    reg_dir = tmp_path / "registry"
    shutil.copytree(REGISTRY_DIR, reg_dir)
    return load_registry(reg_dir)


def _write_rules_dir(tmp_path: Path, eia_text: str = GOOD_YAML, manifest_text: str = MANIFEST_YAML) -> Path:
    d = tmp_path / "rules"
    d.mkdir(exist_ok=True)
    (d / "manifest.yaml").write_text(manifest_text, encoding="utf-8")
    (d / "eia.yaml").write_text(eia_text, encoding="utf-8")
    return d


def test_load_enabled_filter_and_full_query(tmp_path: Path):
    """① 合法 YAML（2 规则一 enabled 一 disabled）→ enabled 过滤可见 / 全量可查。"""
    reg = _make_reg(tmp_path)
    snap = load_rules(_write_rules_dir(tmp_path), reg=reg)
    assert [r.name for r in snap.rules] == ["demo_org_involved_in_mine", "demo_disabled_rule"]
    assert [r.name for r in snap.enabled_rules] == ["demo_org_involved_in_mine"]
    assert all(r.enabled for r in snap.enabled_rules)


def test_bad_yaml_rejected_with_filename(tmp_path: Path):
    """② 坏 YAML → 拒绝且错误带文件名（语法错 + extra=forbid schema 错）。"""
    reg = _make_reg(tmp_path)
    d = _write_rules_dir(tmp_path, eia_text="rules:\n  - name: x\n    when: [bad")
    with pytest.raises(RulesError, match="eia.yaml"):
        load_rules(d, reg=reg)

    d2 = _write_rules_dir(
        tmp_path,
        eia_text='rules:\n  - name: x\n    domain: eia\n    when: ["org_develops_project(?O, ?P)"]\n    derive: "org_involved_in(?O, ?P)"\n    bogus: 1\n',
    )
    with pytest.raises(RulesError, match="eia.yaml"):
        load_rules(d2, reg=reg)


def test_when_unregistered_predicate_rejected(tmp_path: Path):
    """③ when 引用未注册谓词（不在 registry doc_graph.yaml 枚举内）→ 拒绝。"""
    reg = _make_reg(tmp_path)
    bad = GOOD_YAML.replace("org_develops_project(?ORG, ?PROJ)", "ghost_pred(?ORG, ?PROJ)")
    d = _write_rules_dir(tmp_path, eia_text=bad)
    with pytest.raises(RulesError, match="ghost_pred"):
        load_rules(d, reg=reg)


def test_derive_unregistered_etype_rejected(tmp_path: Path):
    """④ derive 引用未注册 etype（类型事实谓词）→ 拒绝。"""
    reg = _make_reg(tmp_path)
    bad = GOOD_YAML.replace('derive: "org_involved_in(?ORG, ?MINE)"', 'derive: "ghost_mine(?ORG, ?MINE)"')
    d = _write_rules_dir(tmp_path, eia_text=bad)
    with pytest.raises(RulesError, match="ghost_mine"):
        load_rules(d, reg=reg)


def test_manifest_missing_file_rejected(tmp_path: Path):
    """⑤ manifest 列了不存在的文件 → 拒绝。"""
    reg = _make_reg(tmp_path)
    m = MANIFEST_YAML + "  - file: ghost.yaml\n"
    d = _write_rules_dir(tmp_path, manifest_text=m)
    with pytest.raises(RulesError, match="ghost.yaml"):
        load_rules(d, reg=reg)


def test_hot_reload_version_bump(tmp_path: Path):
    """⑥ 修改文件内容 → 指纹变化 → 版本递增（热重载）。"""
    reg = _make_reg(tmp_path)
    d = _write_rules_dir(tmp_path)
    store = RuleStore(d, reg_provider=lambda: reg)
    r1 = store.get()
    assert r1.rules_version == 1
    assert store.get() is r1, "磁盘未变 → 返回同一不可变快照"

    f = d / "eia.yaml"
    f.write_text(f.read_text(encoding="utf-8") + "\n# touch\n", encoding="utf-8")
    r2 = store.get()
    assert r2 is not r1
    assert r2.rules_version == r1.rules_version + 1


def test_failed_reload_keeps_old_snapshot(tmp_path: Path):
    """⑦ 修改失败（坏 YAML）→ 保留旧快照继续服务；还原/修复后恢复且 last_error 被清。"""
    reg = _make_reg(tmp_path)
    d = _write_rules_dir(tmp_path)
    store = RuleStore(d, reg_provider=lambda: reg)
    r1 = store.get()

    (d / "eia.yaml").write_text("rules:\n  - name: broken\n    when: [bad", encoding="utf-8")
    r2 = store.get()
    assert r2 is r1, "重载失败 → 保留旧快照继续服务"
    assert r2.rules_version == r1.rules_version
    assert store.last_error is not None and "eia.yaml" in store.last_error

    # 字节级还原 → 指纹与 r1 相同 → 短路返回同一快照, 陈旧 last_error 被清除
    (d / "eia.yaml").write_text(GOOD_YAML, encoding="utf-8")
    assert store.get() is r1
    assert store.last_error is None

    # 内容变化的修复 → 触发重载且版本递增
    (d / "eia.yaml").write_text(GOOD_YAML + "\n# 修复后重载\n", encoding="utf-8")
    r3 = store.get()
    assert r3 is not r1
    assert r3.rules_version == r1.rules_version + 1
    assert store.last_error is None


def test_registry_version_change_triggers_revalidation(tmp_path: Path):
    """⑫ registry 版本变化触发规则重校验（规则文件指纹未变）:

    (a) 版本 bump → 短路失效, 规则重校验出新快照/版本+1;
    (b) 新枚举收缩致规则失效 → 保留旧快照 + last_error 置位;
    (c) 恢复有效 registry → 重载成功 + last_error 清除。
    """
    reg = _make_reg(tmp_path)
    d = _write_rules_dir(tmp_path)
    state = {"reg": reg}
    store = RuleStore(d, reg_provider=lambda: state["reg"])
    r1 = store.get()
    assert store.get() is r1, "短路基线：磁盘与 registry 版本均未变"

    # (a) registry 热重载（版本递增）→ 规则文件未变也重校验
    reg.registry_version += 1
    r2 = store.get()
    assert r2 is not r1
    assert r2.rules_version == r1.rules_version + 1
    assert r2.source_registry_version == reg.registry_version
    assert store.last_error is None

    # (b) 枚举收缩（etype 去 mine → demo 规则失效）→ 保留旧快照 + last_error 置位
    shrunk_dir = tmp_path / "registry_shrunk"
    shutil.copytree(REGISTRY_DIR, shrunk_dir)
    f = shrunk_dir / "doc_graph.yaml"
    f.write_text(f.read_text(encoding="utf-8").replace("qualification, mine, org", "qualification, org"), encoding="utf-8")
    reg_shrunk = load_registry(shrunk_dir)
    reg_shrunk.registry_version = reg.registry_version + 1  # 模拟 registry store 已重载该变更
    state["reg"] = reg_shrunk
    r3 = store.get()
    assert r3 is r2, "规则对新枚举失效 → 保留旧快照继续服务"
    assert r3.rules_version == r2.rules_version
    assert store.last_error is not None and "mine" in store.last_error

    # (c) 恢复有效 registry（版本再递增）→ 重载成功 + last_error 清除
    reg.registry_version += 1
    state["reg"] = reg
    r4 = store.get()
    assert r4 is not r2
    assert r4.rules_version == r2.rules_version + 1
    assert store.last_error is None


def test_malformed_pattern_rejected_as_rules_error(tmp_path: Path):
    """附加：语法坏的模式（无括号）经 facade._compile_pattern 拒绝并包装为带文件名的 RulesError。"""
    reg = _make_reg(tmp_path)
    d = _write_rules_dir(tmp_path, eia_text='rules:\n  - name: x\n    domain: eia\n    when: ["no_parens"]\n    derive: "org_involved_in(?O, ?P)"\n')
    with pytest.raises(RulesError, match="eia.yaml"):
        load_rules(d, reg=reg)


def test_duplicate_rule_name_rejected(tmp_path: Path):
    """附加：规则名重复注册 → 拒绝（防激活溯源塌缩到同名规则）。"""
    reg = _make_reg(tmp_path)
    dup = textwrap.dedent("""\
        rules:
          - name: same_name
            domain: eia
            when: ["org_develops_project(?O, ?P)"]
            derive: "org_involved_in(?O, ?P)"
          - name: same_name
            domain: eia
            when: ["org_compiles_project(?O, ?P)"]
            derive: "org_involved_in(?O, ?P)"
        """)
    d = _write_rules_dir(tmp_path, eia_text=dup)
    with pytest.raises(RulesError, match="same_name"):
        load_rules(d, reg=reg)


def test_cross_domain_predicate_rejected_in_when(tmp_path: Path):
    """⑧ 跨域谓词（spec §5）: eia 规则 when 混入 bid 域谓词 bidder_of_project → 拒绝；derive 混入亦拒。"""
    reg = _make_reg(tmp_path)
    bad = GOOD_YAML.replace("org_develops_project(?ORG, ?PROJ)", "bidder_of_project(?ORG, ?PROJ)")
    d = _write_rules_dir(tmp_path, eia_text=bad)
    with pytest.raises(RulesError, match="bidder_of_project"):
        load_rules(d, reg=reg)

    bad2 = GOOD_YAML.replace('derive: "org_involved_in(?ORG, ?MINE)"', 'derive: "bidder_supplies_goods(?ORG, ?MINE)"')
    d2 = _write_rules_dir(tmp_path, eia_text=bad2)
    with pytest.raises(RulesError, match="bidder_supplies_goods"):
        load_rules(d2, reg=reg)


def test_bid_domain_rule_clean_loads_and_cross_rejected(tmp_path: Path):
    """⑨ bid 域规则同走 load_rules 校验路径: 干净 bid 规则可加载; 混入 eia 谓词 org_develops_project → 拒绝。"""
    reg = _make_reg(tmp_path)
    clean = textwrap.dedent("""\
        rules:
          - name: bid_self_demo
            domain: bid
            when:
              - "bidder_of_project(?BIDDER, ?PROJ)"
            derive: "bidder_of_project(?BIDDER, ?PROJ)"
        """)
    d0 = _write_rules_dir(tmp_path, eia_text=clean)
    snap = load_rules(d0, reg=reg)
    assert [r.name for r in snap.rules] == ["bid_self_demo"]

    dirty = textwrap.dedent("""\
        rules:
          - name: bid_cross_demo
            domain: bid
            when:
              - "org_develops_project(?BIDDER, ?PROJ)"
            derive: "bidder_of_project(?BIDDER, ?PROJ)"
        """)
    d1 = _write_rules_dir(tmp_path, eia_text=dirty)
    with pytest.raises(RulesError, match="org_develops_project"):
        load_rules(d1, reg=reg)


def test_cross_domain_etype_rejected(tmp_path: Path):
    """⑩ 跨域 etype: eia 规则 when 出现 bid 域 etype bidder（类型谓词）→ 拒绝。"""
    reg = _make_reg(tmp_path)
    bad = textwrap.dedent("""\
        rules:
          - name: eia_cross_etype
            domain: eia
            when:
              - "bidder(?B)"
            derive: "org_involved_in(?B, ?B)"
        """)
    d = _write_rules_dir(tmp_path, eia_text=bad)
    with pytest.raises(RulesError, match=r"bidder' 不属于域 'eia'"):
        load_rules(d, reg=reg)


def test_unknown_domain_rejected(tmp_path: Path):
    """⑪ 未知域: domain 不在已知域表 → 拒绝（fail-closed, 不静默放行）。"""
    reg = _make_reg(tmp_path)
    bad = GOOD_YAML.replace("domain: eia", "domain: ghost_domain")
    d = _write_rules_dir(tmp_path, eia_text=bad)
    with pytest.raises(RulesError, match="ghost_domain"):
        load_rules(d, reg=reg)


def test_real_repo_rules_load():
    """附加：仓库自带示例规则（rules/eia.yaml）对真枚举可加载——lint check_reasoning_rules 同源回归锚。"""
    reg = load_registry(REGISTRY_DIR)
    snap = load_rules(RULES_DIR, reg=reg)
    assert len(snap.rules) >= 2
    assert all(r.note.strip() for r in snap.rules), "示例规则必须带 note（演示规则，非业务定案）"
    assert all("演示规则" in r.note for r in snap.rules)
