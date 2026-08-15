"""T2 单测：注册表加载 / 指纹+版本 / 坏 YAML 拒绝（fail-closed）.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md §4
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T2 Verify
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from app.extensions.ontology.registry import RegistryError, RegistryStore, load_registry
from app.extensions.ontology.schemas import ObjectType

REGISTRY_DIR = Path(__file__).parent.parent / "app" / "extensions" / "ontology" / "registry"


def test_load_real_registry():
    """① 加载真实注册表：11 对象 / 12 链接（8 FK + 4 跨模块 stub）。"""
    reg = load_registry(REGISTRY_DIR)
    assert len(reg.object_types) == 11, sorted(reg.object_types)
    assert len(reg.link_types) == 12, sorted(reg.link_types)

    fk = [lt for lt in reg.link_types.values() if lt.join.type == "foreign_key"]
    cross = [lt for lt in reg.link_types.values() if lt.cross_module]
    assert len(fk) == 8
    assert len(cross) == 4
    # D3: 全部跨模块链接 stub 上线（召回预测量结论）
    assert all(lt.enabled is False for lt in cross)
    assert all(lt.note for lt in cross), "stub 链接必须带 note 记录实测原因"
    # 域分布
    domains = {obj.domain for obj in reg.object_types.values()}
    assert domains == {"contract_price", "spare_parts", "bid_quote"}
    # hidden 列不参与过滤/搜索
    ds = reg.object_types["data_source"]
    conn = next(p for p in ds.properties if p.name == "connection_config")
    assert conn.hidden and not conn.filterable and not conn.searchable


def test_fingerprint_and_version_bump(tmp_path: Path):
    """② 指纹变化 → registry_version 递增；未变化 → 同实例同版本。"""
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry")
    store = RegistryStore(tmp_path / "registry")
    r1 = store.get()
    assert r1.registry_version == 1
    assert store.get() is r1, "磁盘未变 → 返回同一不可变快照"

    # 修改一个域文件（加一个链接）
    f = tmp_path / "registry" / "bid_quote.yaml"
    f.write_text(
        f.read_text(encoding="utf-8")
        + textwrap.dedent("""
    """),
        encoding="utf-8",
    )
    # 空追加不改语义但改内容字节 → 指纹变
    r2 = store.get()
    assert r2 is not r1
    assert r2.registry_version == r1.registry_version + 1


def test_malformed_yaml_rejected_with_filename(tmp_path: Path):
    """③ 坏 YAML fail-closed：带文件名拒绝，绝不半加载。"""
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry")
    # 语法错误（缩进炸）
    (tmp_path / "registry" / "contract_price.yaml").write_text("object_types:\n  - api_name: x\n    properties: [bad", encoding="utf-8")
    with pytest.raises(RegistryError, match="contract_price.yaml"):
        load_registry(tmp_path / "registry")

    # schema 错误（未知字段，extra=forbid）
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry2")
    (tmp_path / "registry2" / "spare_parts.yaml").write_text("object_types:\n  - api_name: customer\n    bogus_field: 1\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="spare_parts.yaml"):
        load_registry(tmp_path / "registry2")

    # 交叉引用错误：链接指向未注册对象
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry3")
    (tmp_path / "registry3" / "cross_module.yaml").write_text(
        textwrap.dedent("""
        object_types: []
        link_types:
          - api_name: ghost_link
            display_name: ghost
            source: part_cluster
            target: no_such_object
            cardinality: N:N
            reverse: ghost_r
            join:
              type: normalized_key_match
              key_pairs:
                - [representative_name, representative_name]
        """),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="no_such_object"):
        load_registry(tmp_path / "registry3")

    # FK 列未声明（declared-only 铁律）
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry4")
    (tmp_path / "registry4" / "bid_quote.yaml").write_text(
        textwrap.dedent("""
        object_types:
          - api_name: bid_item
            display_name: x
            description: x
            domain: bid_quote
            access: { path: postgres_ext, table: mock_bid_item }
            pk: { column: id, api_name: id, type: integer }
            properties:
              - { name: id, api_name: id, type: integer, description: pk }
        link_types:
          - api_name: bad_fk
            display_name: x
            source: bid_item
            target: bid_item
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
    """热重载失败 → 旧快照继续服务（get 再抛错由调用方决定，旧数据不静默换空）。"""
    shutil.copytree(REGISTRY_DIR, tmp_path / "registry")
    store = RegistryStore(tmp_path / "registry")
    r1 = store.get()
    cross = tmp_path / "registry" / "cross_module.yaml"
    backup = cross.read_text(encoding="utf-8")
    cross.write_text("object_types: [\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        store.get()
    # 修复后恢复并做真实变更 → 触发成功重载，版本递增（失败不占版本号）
    cross.write_text(backup + "# touched\n", encoding="utf-8")
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
