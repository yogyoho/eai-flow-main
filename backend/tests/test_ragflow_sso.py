# EAI-CUSTOM: RAGFlow SSO integration tests — 本地定制,非上游.


def test_ragflow_config_reads_sso_secret(monkeypatch):
    from app.extensions.config import RAGFlowConfig

    monkeypatch.setenv("EAI_SSO_SHARED_SECRET", "abc123")
    cfg = RAGFlowConfig.from_env()
    assert cfg.sso_secret == "abc123"


def test_ragflow_config_sso_secret_default_empty(monkeypatch):
    from app.extensions.config import RAGFlowConfig

    monkeypatch.delenv("EAI_SSO_SHARED_SECRET", raising=False)
    cfg = RAGFlowConfig.from_env()
    assert cfg.sso_secret == ""


def test_credential_model_registered_in_metadata():
    # EAI-CUSTOM: guards the models/__init__ aggregation import — if it is
    # removed/reordered, create_all silently drops the table and the first
    # SSO exchange dies on a missing relation.
    import app.extensions.models  # noqa: F401 — ensures aggregation ran
    from app.extensions.database import Base
    from app.extensions.ragflow_sso.models import RagflowCredential

    assert RagflowCredential.__tablename__ in Base.metadata.tables
