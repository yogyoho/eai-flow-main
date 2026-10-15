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
    import subprocess
    import sys
    from pathlib import Path

    # EAI-CUSTOM: guards the models/__init__ aggregation import — if it is
    # removed/reordered, create_all silently drops the table and the first
    # SSO exchange dies on a missing relation. Runs in a fresh interpreter so
    # pytest-session imports cannot make this self-fulfilling.
    probe = "import app.extensions.models; from app.extensions.database import Base; assert 'ragflow_credentials' in Base.metadata.tables"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
