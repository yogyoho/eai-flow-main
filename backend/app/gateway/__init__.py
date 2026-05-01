from .config import GatewayConfig, get_gateway_config


def _get_app():
    """Lazy-import ``app`` and ``create_app`` so that importing from
    ``app.gateway`` does not trigger the full FastAPI application import
    chain (which pulls in every extension router)."""
    from .app import app, create_app  # noqa: PLC0415

    return app, create_app


__all__ = ["GatewayConfig", "get_gateway_config"]
