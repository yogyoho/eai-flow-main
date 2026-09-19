"""registry 内容管理端点测试（建模器 MVP 后端, EAI-CUSTOM 2026-09-20）.

读/校验/写三端点：真实 mini registry 临时目录注入（conftest 无 DB 依赖）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ontology.registry import RegistryStore

MINI = """\
namespaces:
  ex: "https://example.org/mini#"
object_types:
  - api_name: thing
    display_name: 事物
    description: 测试对象
    domain: mini
    access: { path: postgres_ext, table: mini_things }
    pk: { column: id, api_name: id, type: uuid }
    properties:
      - { name: id, api_name: id, type: uuid, description: 主键 }
      - { name: etype, api_name: etype, type: string, description: 类型, enum: [project, activity] }
      - { name: norm_name, api_name: normName, type: string, description: 规范名 }
    etype_classes:
      project: { class: Project, subClassOf: [Activity], label: 项目, definition: 测试项目类 }
"""


@pytest.fixture()
def mini_env(tmp_path: Path, monkeypatch):
    """临时 registry 目录 + 指向它的 RegistryStore 单例隔离。"""
    (tmp_path / "_manifest.yaml").write_text("schema_version: 1\nfiles:\n  - file: mini.yaml\n", encoding="utf-8")
    (tmp_path / "mini.yaml").write_text(MINI, encoding="utf-8")
    store = RegistryStore(tmp_path)
    monkeypatch.setattr("app.ontology.registry._store", store)
    monkeypatch.setattr("app.ontology.registry.REGISTRY_DIR", tmp_path)
    import app.ontology.registry_content as rc

    monkeypatch.setattr(rc, "REGISTRY_DIR", tmp_path)
    return tmp_path


def test_guard_rejects_bad_filename():
    from app.ontology.registry_content import _guard_file

    with pytest.raises(Exception, match="非法文件名"):
        _guard_file("../evil.yaml")


def test_validate_good_draft(mini_env):
    from app.ontology.registry_content import _validate_draft

    ok, errors, registry = _validate_draft("mini.yaml", MINI)
    assert ok and not errors and registry is not None


def test_validate_bad_draft_fails_closed(mini_env):
    from app.ontology.registry_content import _validate_draft

    bad = MINI.replace("    access: { path: postgres_ext, table: mini_things }\n", "")
    ok, errors, registry = _validate_draft("mini.yaml", bad)
    assert not ok and errors


def test_summary_contains_classes(mini_env):
    from app.ontology.registry_content import _registry_summary, load_registry

    registry = load_registry(mini_env)
    summary = _registry_summary(registry)
    mini = summary["domains"]["mini"]
    names = [c["name"] for c in mini["classes"]]
    assert "Project" in names and "Activity" in names
    proj = next(c for c in mini["classes"] if c["name"] == "Project")
    assert proj["parents"] == ["Activity"] and proj["label"] == "项目"


def test_atomic_write_and_reload(mini_env):
    import os

    target = mini_env / "mini.yaml"
    updated = MINI + "\n# touched\n"
    tmp = target.with_suffix(".yaml.tmp")
    tmp.write_text(updated, encoding="utf-8")
    os.replace(tmp, target)
    store = RegistryStore(mini_env)
    reg = store.get()
    assert "# touched" in (mini_env / "mini.yaml").read_text(encoding="utf-8")
    assert reg.registry_version >= 1
