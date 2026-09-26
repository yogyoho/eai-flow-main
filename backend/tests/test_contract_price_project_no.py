"""cpa_documents.project_no 新字段端到端(2026-09-21 合同元数据修复)。

链路: 提取(skill project_fields,另测) → skill scripts/models.py 镜像列 →
backend ORM 列 + 幂等 ALTER → DocumentOut / DocumentUpdate → crud 白名单。
无 DB 依赖: ORM/迁移/schema 用真实对象断言,crud 白名单用源码契约断言
(与 skills 侧 test_persist_one_doc_field_sentinel_is_key_presence 同手法)。
"""

from __future__ import annotations

import inspect
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_MODELS = _REPO_ROOT / "skills" / "public" / "contract-price-analysis" / "scripts" / "models.py"


def test_backend_orm_has_project_no_varchar120():
    from app.extensions.contract_price.models import CpaDocument

    col = CpaDocument.__table__.columns["project_no"]
    assert col.nullable is True
    assert "VARCHAR(120)" in str(col.type).upper()


def test_skill_mirror_model_has_matching_project_no_column():
    """镜像列必须与 backend 列同型——两套 ORM 描述同一物理表,漂移即静默腐蚀。"""
    import importlib.util

    assert _SKILL_MODELS.exists(), f"skill mirror missing: {_SKILL_MODELS}"
    spec = importlib.util.spec_from_file_location("cpa_skill_models_pn", _SKILL_MODELS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    col = module.CpaDocument.__table__.columns["project_no"]
    assert "VARCHAR(120)" in str(col.type).upper()


def test_database_migration_declares_project_no_alter():
    """幂等 ALTER 必须存在——create_all 不会给已填充的 cpa_documents 补列。"""
    from app.extensions import database

    src = inspect.getsource(database)
    assert "ALTER TABLE cpa_documents ADD COLUMN IF NOT EXISTS project_no VARCHAR(120)" in src


def test_document_out_exposes_project_no():
    from app.extensions.contract_price.schemas import DocumentOut

    assert "project_no" in DocumentOut.model_fields
    assert DocumentOut.model_fields["project_no"].default is None


def test_document_update_accepts_project_no():
    from app.extensions.contract_price.schemas import DocumentUpdate

    body = DocumentUpdate(project_no="01116102P20200020000000000P")
    assert body.project_no == "01116102P20200020000000000P"
    # None 也合法(手改清空)
    assert DocumentUpdate(project_no=None).project_no is None


def test_crud_update_document_whitelist_includes_project_no():
    from app.extensions.contract_price import crud

    src = inspect.getsource(crud.update_document)
    assert '"project_no"' in src, "crud.update_document 白名单缺 project_no,PATCH 手改通道不生效"


def test_skill_persist_writes_project_no_column():
    """skill 侧 _persist_one_doc 必须落 project_no(键存在哨兵,见 bug-3431 语义)。
    以源码文本断言(完整 import 链在 skill 套件内已有行为级测试:
    test_persist_one_doc_field_sentinel_is_key_presence)。"""
    cli_src = (_REPO_ROOT / "skills" / "public" / "contract-price-analysis" / "scripts" / "cli.py").read_text(
        encoding="utf-8"
    )
    assert 'project_no=doc.get("project_no")' in cli_src
    assert '("project_name", "project_location", "contract_no", "supplier", "project_no")' in cli_src
    assert '"project_no": project_no' in cli_src
