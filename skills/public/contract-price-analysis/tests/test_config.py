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


def test_cluster_toggles_and_params(monkeypatch):
    """分组开关+聚类参数(2026-09-23 接线): env 解析与默认值。"""
    monkeypatch.setenv("CPA_CLUSTER_BY_SPEC", "0")
    monkeypatch.setenv("CPA_CLUSTER_BY_CATEGORY", "false")
    monkeypatch.setenv("CPA_CLUSTER_EPS", "0.5")
    monkeypatch.setenv("CPA_CLUSTER_MIN_SAMPLES", "3")
    cfg = get_config()
    assert cfg.cluster_by_spec is False
    assert cfg.cluster_by_category is False
    assert cfg.cluster_eps == 0.5
    assert cfg.cluster_min_samples == 3


def test_cluster_defaults(monkeypatch):
    for k in (
        "CPA_CLUSTER_BY_SPEC",
        "CPA_CLUSTER_BY_CATEGORY",
        "CPA_CLUSTER_EPS",
        "CPA_CLUSTER_MIN_SAMPLES",
    ):
        monkeypatch.delenv(k, raising=False)
    cfg = get_config()
    assert cfg.cluster_by_spec is True
    assert cfg.cluster_by_category is True
    assert cfg.cluster_eps == 0.6
    assert cfg.cluster_min_samples == 2
