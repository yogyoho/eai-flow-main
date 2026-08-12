# EAI-CUSTOM: 备品备件价格体系分析扩展包(forked from contract_price)。
"""spare-parts-analysis 扩展包。

数据层:csp_ 表(挂共享 ``app.extensions.database.Base``,gateway 启动自动建表)。
客户维度归一走 csp_customers 主数据表 + 别名映射(D3);备件名归一走聚类引擎。
OCR 管线脚本在 ``skills/public/spare-parts-analysis/scripts/``,由 service 层触发。

router 在 routers.py 就绪后在此导出(T4/T5 接线)。
"""

from app.extensions.spare_parts.models import (  # noqa: F401
    CspCluster,
    CspCustomer,
    CspDocument,
    CspItem,
    CspRunHistory,
)
from app.extensions.spare_parts.routers import router  # noqa: F401

__all__ = [
    "CspCustomer",
    "CspDocument",
    "CspItem",
    "CspCluster",
    "CspRunHistory",
    "router",
]
