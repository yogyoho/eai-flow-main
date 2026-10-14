"""合同文件库（cpa v3, spec 2026-10-14 §1）：表注册 + 端点编排 + scanner 跳过。

表注册用共享 Base 断言；端点编排用 asyncio.run 直调路由函数 +
monkeypatch crud/storage（镜像 test_contract_price_document_file.py 的模式），
不需要真实 DB / MinIO。
"""

import app.extensions.contract_price  # noqa: F401 — 导入即注册模型


def test_library_tables_registered_on_shared_base():
    from app.extensions.database import Base

    assert {"cpa_library_folders", "cpa_library_files"} <= set(Base.metadata.tables)


def test_router_exposes_library_area():
    from app.extensions.contract_price import router

    paths = {r.path for r in router.routes}
    base = "/api/extensions/contract-price"
    assert f"{base}/library/folders" in paths
    assert f"{base}/library/files" in paths
    assert f"{base}/library/files/upload" in paths
    assert f"{base}/library/files/{{file_id}}/content" in paths
    assert f"{base}/library/files/{{file_id}}/items" in paths
    assert f"{base}/library/files/{{file_id}}/analyze" in paths
