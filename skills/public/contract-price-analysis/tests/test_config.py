from scripts.config import get_config


def test_get_config_reads_env(monkeypatch):
    monkeypatch.setenv("CPA_MINIO_BUCKET", "x")
    cfg = get_config()
    assert cfg.minio_bucket == "x"


def test_get_config_defaults(monkeypatch):
    monkeypatch.delenv("OCR_SERVICE_URL", raising=False)
    monkeypatch.delenv("CPA_MINIO_BUCKET", raising=False)
    cfg = get_config()
    assert cfg.ocr_service_url == "http://eai-flow-ocr:8010"
    assert cfg.minio_bucket == "cpa-contracts"
