"""Tests for the contract_price extension (models, routes, schemas).

These run in the backend test environment (``PYTHONPATH=. uv run pytest``) and
verify the extension is wired into the shared Base + Gateway without needing a
live DB.
"""


def test_cpa_models_registered_on_shared_base():
    # Importing the extension registers its models on the shared Base.metadata.
    import app.extensions.contract_price  # noqa: F401
    from app.extensions.database import Base

    tables = set(Base.metadata.tables)
    assert {
        "cpa_documents",
        "cpa_items",
        "cpa_clusters",
        "cpa_run_history",
    } <= tables


def test_router_exposes_all_functional_areas():
    from app.extensions.contract_price import router

    paths = {r.path for r in router.routes}
    base = "/api/extensions/contract-price"
    # Functional area 1: documents
    assert f"{base}/documents" in paths
    # Functional area 2: clusters
    assert f"{base}/clusters" in paths
    assert f"{base}/clusters/merge" in paths
    # Functional area 3: items
    assert f"{base}/items" in paths
    # Functional area 4: runs
    assert f"{base}/runs" in paths
    # Functional area 5: config
    assert f"{base}/config" in paths
    # Functional area 6: dashboard
    assert f"{base}/dashboard" in paths
    # Pipeline trigger
    assert f"{base}/pipeline/run" in paths


def test_schemas_roundtrip():
    from app.extensions.contract_price.schemas import (
        ClusterMerge,
        ConfigOut,
        DashboardOut,
        ItemUpdate,
        PipelineRunRequest,
    )

    cfg = ConfigOut()
    assert cfg.cluster_eps == 0.6
    assert DashboardOut(
        contract_count=1, item_count=2, cluster_count=1,
        pending_cluster_count=1, confirmed_cluster_count=0,
    ).price_range is None
    merge = ClusterMerge(
        cluster_ids=["00000000-0000-0000-0000-000000000000"] * 2,
        representative_name="开关柜",
    )
    assert merge.representative_name == "开关柜"
    assert PipelineRunRequest().mode == "table"


def test_config_crud_roundtrip(tmp_path, monkeypatch):
    from app.extensions.contract_price import crud
    from app.extensions.contract_price.schemas import ConfigUpdate

    monkeypatch.setattr(crud, "_CONFIG_PATH", str(tmp_path / "config.json"))
    cfg = ConfigUpdate(parse_mode="list", scheduled_enabled=True, schedule_cron="0 2 * * *")
    crud.save_config(cfg)
    loaded = crud.load_config()
    assert loaded.parse_mode == "list"
    assert loaded.scheduled_enabled is True
    assert loaded.schedule_cron == "0 2 * * *"
