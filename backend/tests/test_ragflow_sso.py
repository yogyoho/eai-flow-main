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
