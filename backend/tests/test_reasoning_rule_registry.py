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
    """⑦ 修改失败（坏 YAML）→ 保留旧快照继续服务；修复后恢复重载且版本递增。"""
    reg = _make_reg(tmp_path)
    d = _write_rules_dir(tmp_path)
    store = RuleStore(d, reg_provider=lambda: reg)
    r1 = store.get()

    (d / "eia.yaml").write_text("rules:\n  - name: broken\n    when: [bad", encoding="utf-8")
    r2 = store.get()
    assert r2 is r1, "重载失败 → 保留旧快照继续服务"
    assert r2.rules_version == r1.rules_version
    assert store.last_error is not None and "eia.yaml" in store.last_error

    (d / "eia.yaml").write_text(GOOD_YAML + "\n# 修复后重载\n", encoding="utf-8")
    r3 = store.get()
    assert r3 is not r1
    assert r3.rules_version == r1.rules_version + 1
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


def test_real_repo_rules_load():
    """附加：仓库自带示例规则（rules/eia.yaml）对真枚举可加载——lint check_reasoning_rules 同源回归锚。"""
    reg = load_registry(REGISTRY_DIR)
    snap = load_rules(RULES_DIR, reg=reg)
    assert len(snap.rules) >= 2
    assert all(r.note.strip() for r in snap.rules), "示例规则必须带 note（演示规则，非业务定案）"
    assert all("演示规则" in r.note for r in snap.rules)
