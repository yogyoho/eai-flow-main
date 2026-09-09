# EAI-CUSTOM: 投标资料管理扩展（bug-3109 v4）——资质 MinIO 版本库 + 样例台账。
"""Bid materials extension: qualification MinIO version bank + sample ledger.

表创建机制：本包导入即把 bid_* 模型注册到共享 ``app.extensions.database`` Base，
gateway 启动序 init_db（create_all）建表（同 eia_samples/geo_samples 机制）。

管理路由挂载于 Gateway ``/api/extensions/bid-materials``（routers.py）。
"""

from .routers import router  # noqa: F401
from .routers import router as bid_materials_router  # noqa: F401

__all__ = ["router", "bid_materials_router"]
