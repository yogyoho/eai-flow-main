"""货物分类术语（cpa v3, spec 2026-10-14 §2）：表注册 + CRUD 编排 + capture 改写。

编排测试镜像 M1 test_contract_price_library.py 的 asyncio.run 直调 + monkeypatch 模式，
不需要真实 DB。
"""

import app.extensions.contract_price  # noqa: F401 — 导入即注册模型


def test_terms_table_registered_on_shared_base():
    from app.extensions.database import Base

    assert {"cpa_terms"} <= set(Base.metadata.tables)
