"""合同文件库（cpa v3, spec 2026-10-14 §1）：表注册 + 端点编排 + scanner 跳过。

表注册用共享 Base 断言；端点编排用 asyncio.run 直调路由函数 +
monkeypatch crud/storage（镜像 test_contract_price_document_file.py 的模式），
不需要真实 DB / MinIO。
"""

import app.extensions.contract_price  # noqa: F401 — 导入即注册模型
from app.extensions.contract_price import storage as cpa_storage


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


def test_library_key_shape():
    key = cpa_storage.library_key("f-1", "a" * 64, "合同 A.pdf")
    assert key.startswith("library/f-1/")
    assert key.endswith("_合同 A.pdf")
    assert "a" * 16 in key  # hash 前 16 位
    assert cpa_storage.library_key("f-1", "a" * 64, "x/y.pdf").count("/") == 2  # 文件名里的 / 被替换


def test_copy_object_uses_server_side_copy(monkeypatch):
    captured = {}

    class _FakeMinio:
        def copy_object(self, bucket, dst, src):
            # minio 7.2.x CopySource 暴露 bucket_name / object_name（无 .bucket 别名）
            captured.update(bucket=bucket, dst=dst, src_bucket=src.bucket_name, src_key=src.object_name)

    monkeypatch.setattr(cpa_storage, "_client", lambda: _FakeMinio())
    uri = cpa_storage.copy_object("library/f1/abc_合同.pdf", "合同B.pdf")
    assert captured == {
        "bucket": "cpa-contracts",
        "dst": "合同B.pdf",
        "src_bucket": "cpa-contracts",
        "src_key": "library/f1/abc_合同.pdf",
    }
    assert uri == "s3://cpa-contracts/合同B.pdf"
