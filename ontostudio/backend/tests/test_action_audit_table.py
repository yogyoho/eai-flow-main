"""审计表随 Base.metadata 注册 + status 枚举含 rejected + 真实 registry 已声明审核动作。"""

from app.db import Base
from app.doc_graph.tables import DgActionAudit


def test_audit_table_registered_in_metadata():
    assert "dg_action_audit" in Base.metadata.tables


def test_audit_columns():
    cols = set(DgActionAudit.__table__.columns.keys())
    assert {
        "id",
        "action_id",
        "domain",
        "target_table",
        "target_pk",
        "actor_id",
        "actor_role",
        "params",
        "before",
        "after",
        "source",
        "created_at",
    } <= cols


def test_status_enum_includes_rejected():
    from pathlib import Path

    src = Path("app/ontology/kernel/validate.py").read_text(encoding="utf-8")
    assert '"rejected"' in src, "status 枚举未加 rejected——SHACL 会判拒绝后实体违规"


def test_registry_doc_graph_status_enum_includes_rejected():
    from pathlib import Path

    yaml_src = Path("app/ontology/registry/doc_graph.yaml").read_text(encoding="utf-8")
    assert "rejected" in yaml_src


def test_real_registry_declares_review_actions():
    """真实 registry 已声明两个审核动作——Task 5/7/8/10 全靠它们。"""
    from app.ontology.registry import get_registry

    reg = get_registry()
    assert reg.get_action("review_entity.confirm") is not None
    assert reg.get_action("review_entity.reject") is not None
    assert reg.get_action("review_entity.confirm").target == "graph_entity"
