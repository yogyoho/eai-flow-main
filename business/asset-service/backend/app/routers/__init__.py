"""资产管理微服务路由注册"""

from app.routers import (
    allocations,
    assets,
    checks,
    dashboard,
    depreciation,
    maintenance,
    scrapping,
)

__all__ = [
    "assets",
    "maintenance",
    "allocations",
    "depreciation",
    "checks",
    "scrapping",
    "dashboard",
]
