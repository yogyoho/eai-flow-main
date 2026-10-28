"""Domain errors mapped to HTTP responses by the routers."""

from __future__ import annotations


class WorkflowError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(WorkflowError):
    status_code = 404


class ConflictError(WorkflowError):
    status_code = 409


class ForbiddenError(WorkflowError):
    status_code = 403
