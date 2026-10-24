"""Structured errors matching the QW2 API contract."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class SalesError(Exception):
    def __init__(
        self,
        detail: str,
        code: str = "SALES-500-INTERNAL",
        status_code: int = 500,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status_code = status_code
        self.context = context or {}


def error_response(request: Request, exc: SalesError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code, "context": exc.context},
    )


def bad_request(detail: str, code: str = "SALES-400-INVALID", context: dict | None = None) -> SalesError:
    return SalesError(detail, code, 400, context)


def forbidden(detail: str = "数据范围或权限不足", code: str = "SALES-403-SCOPE_DENIED") -> SalesError:
    return SalesError(detail, code, 403)


def not_found(detail: str = "对象不存在", code: str = "SALES-404-NOT_FOUND") -> SalesError:
    return SalesError(detail, code, 404)


def conflict(detail: str, code: str = "SALES-409-STATE") -> SalesError:
    return SalesError(detail, code, 409)


def unprocessable(detail: str, code: str = "SALES-422-RULE", context: dict | None = None) -> SalesError:
    return SalesError(detail, code, 422, context)


def unavailable(detail: str = "审批引擎暂不可用，请稍后重试", code: str = "SALES-503-TEMPORAL_UNAVAILABLE") -> SalesError:
    return SalesError(detail, code, 503)
