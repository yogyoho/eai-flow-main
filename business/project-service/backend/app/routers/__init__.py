"""项目管理微服务路由注册"""

from app.routers import (
    dashboard,
    documents,
    milestones,
    projects,
    resources,
    risks,
    tasks,
)

__all__ = [
    "projects",
    "tasks",
    "milestones",
    "resources",
    "risks",
    "documents",
    "dashboard",
]
