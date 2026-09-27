"""T2 单测：注册表加载 / 指纹+版本 / 坏 YAML 拒绝（fail-closed）.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md §4
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T2 Verify
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from app.ontology.registry import RegistryError, RegistryStore, load_registry
from app.ontology.schemas import ObjectType

REGISTRY_DIR = Path(__file__).parent.parent / "app" / "ontology" / "registry"


def test_load_real_registry():
    """① 加载真实注册表（EAI-CUSTOM 2026-09-27 缩编后两文件世界）：
    5 对象 / 6 链接（6 FK，全部 enabled——旧四域的 4 条跨模块 stub 链接随 yaml 退场，
    D3 stub 机制由 test_ontology_engine 的合成 stub 用例守）。"""
    reg = load_registry(REGISTRY_DIR)
    assert len(reg.object_types) == 5, sorted(reg.object_types)
    assert len(reg.link_types) == 6, sorted(reg.link_types)

    fk = [lt for lt in reg.link_types.values() if lt.join.type == "foreign_key"]
    cross = [lt for lt in reg.link_types.values() if lt.cross_module]
    assert len(fk) == 6
    assert cross == []
    # 缩编后无 stub：全部链接 enabled（stub 遍历拒绝机制见 test_ontology_engine）
    assert all(lt.enabled for lt in reg.link_types.values())
    # 域分布：幸存域 = doc_graph + eia（eia 经 mention_of_eia_* 证据链挂接，不再 orphan）
    domains = {obj.domain for obj in reg.object_types.values()}
    assert domains == {"doc_graph", "eia"}
    # eia 域 dg_* 透镜: etype 枚举齐全（抽取四类目标 + 章节结构）
    eia_obj = reg.object_types["eia_entity"]
    etype_prop = next(p for p in eia_obj.properties if p.name == "etype")
    assert "standard_threshold" in (etype_prop.enum or []) and "report" in (etype_prop.enum or [])
    # doc_graph 域: 审核动作仍钉在 graph_entity
    assert "review_entity.confirm" in reg.actions and "review_entity.reject" in reg.actions


def test_fingerprint_and_version_bump(tmp_path: Path):
    """② 指纹变化 → registry_version 递增；未变化 → 同实例同版本。"""
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry")
    store = RegistryStore(tmp_path / "registry")
    r1 = store.get()
    assert r1.registry_version == 1
    assert store.get() is r1, "磁盘未变 → 返回同一不可变快照"

    # 修改一个域文件（缩编后幸存文件之一；空追加不改语义但改内容字节 → 指纹变）
    f = tmp_path / "registry" / "eia.yaml"
    f.write_text(
        f.read_text(encoding="utf-8")
        + textwrap.dedent("""
    """),
        encoding="utf-8",
    )
    r2 = store.get()
    assert r2 is not r1
    assert r2.registry_version == r1.registry_version + 1


def test_malformed_yaml_rejected_with_filename(tmp_path: Path):
    """③ 坏 YAML fail-closed：带文件名拒绝，绝不半加载。

    EAI-CUSTOM(2026-09-27 registry 缩编): 载体从已删的 contract_price/spare_parts/
    cross_module/bid_quote 换成幸存的 doc_graph.yaml / eia.yaml——机制断言全部不变
    （坏写内容整文件覆盖清单内文件，加载器按清单重读才踩雷）。
    """
    # 语法错误（缩进炸）
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry")
    (tmp_path / "registry" / "doc_graph.yaml").write_text("object_types:\n  - api_name: x\n    properties: [bad", encoding="utf-8")
    with pytest.raises(RegistryError, match="doc_graph.yaml"):
        load_registry(tmp_path / "registry")

    # schema 错误（未知字段，extra=forbid）
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry2")
    (tmp_path / "registry2" / "eia.yaml").write_text("object_types:\n  - api_name: customer\n    bogus_field: 1\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="eia.yaml"):
        load_registry(tmp_path / "registry2")

    # 交叉引用错误：链接指向未注册对象（source 用真实类型，让 target 的报错命中）
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry3")
    (tmp_path / "registry3" / "eia.yaml").write_text(
        textwrap.dedent("""
        object_types: []
        link_types:
          - api_name: ghost_link
            display_name: ghost
            source: graph_mention
            target: no_such_object
            cardinality: N:N
            reverse: ghost_r
            join:
              type: normalized_key_match
              key_pairs:
                - [entity_id, entity_id]
        """),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="no_such_object"):
        load_registry(tmp_path / "registry3")

    # FK 列未声明（declared-only 铁律）
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry4")
    (tmp_path / "registry4" / "eia.yaml").write_text(
        textwrap.dedent("""
        object_types:
          - api_name: mock_thing
            display_name: x
            description: x
            domain: eia
            access: { path: postgres_ext, table: mock_thing }
            pk: { column: id, api_name: id, type: integer }
            properties:
              - { name: id, api_name: id, type: integer, description: pk }
        link_types:
          - api_name: bad_fk
            display_name: x
            source: mock_thing
            target: mock_thing
            cardinality: N:1
            reverse: bad_fk_r
            join:
              type: foreign_key
              source_column: undeclared_col
              target_column: id
        """),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="undeclared_col"):
        load_registry(tmp_path / "registry4")


def test_hot_reload_failure_keeps_old_version(tmp_path: Path):
    """热重载失败 → 旧快照继续服务（get 再抛错由调用方决定，旧数据不静默换空）。

    EAI-CUSTOM(2026-09-27 registry 缩编): 载体 cross_module.yaml → eia.yaml，机制断言不变。
    """
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry")
    store = RegistryStore(tmp_path / "registry")
    r1 = store.get()
    target = tmp_path / "registry" / "eia.yaml"
    backup = target.read_text(encoding="utf-8")
    target.write_text("object_types: [\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        store.get()
    # 修复后恢复并做真实变更 → 触发成功重载，版本递增（失败不占版本号）
    target.write_text(backup + "# touched\n", encoding="utf-8")
    r3 = store.get()
    assert r3.registry_version == r1.registry_version + 1
    assert store.get() is r3


def test_object_type_visible_properties():
    obj = ObjectType.model_validate(
        {
            "api_name": "t",
            "display_name": "t",
            "description": "t",
            "domain": "t",
            "access": {"path": "postgres_ext", "table": "t"},
            "pk": {"column": "id", "api_name": "id", "type": "uuid"},
            "properties": [
                {"name": "id", "api_name": "id", "type": "uuid", "description": ""},
                {"name": "secret", "api_name": "secret", "type": "string", "description": "", "hidden": True},
            ],
        }
    )
    assert [p.name for p in obj.visible_properties()] == ["id"]
    assert len(obj.visible_properties(include_hidden=True)) == 2
