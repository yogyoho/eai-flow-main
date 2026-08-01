"""Collab Workspace — 完全独立的人+agent 协作 workspace 模块。

EAI-CUSTOM: 全新模块，与 extensions/{project,workflow,approval} 零引用。
复用共享基础设施：docmgr 数据表 / collab 协编端点 / review.gate（纯函数）/ AgentStore / Gateway thread API。
"""

from .routers import router

__all__ = ["router"]
