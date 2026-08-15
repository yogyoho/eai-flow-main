"""AI Document management module."""


# ponytail: lazy import to avoid FastAPI dependency in MCP server context
def __getattr__(name: str):
    if name == "docmgr_router":
        from app.extensions.docmgr.routers import router as _router

        return _router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["docmgr_router"]
