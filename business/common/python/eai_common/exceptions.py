"""Shared exception classes for business microservices."""

from fastapi import HTTPException, status


class BusinessException(HTTPException):
    """Base exception for business service errors."""

    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class NotFoundException(BusinessException):
    """Exception for resource not found errors."""

    def __init__(self, resource: str, resource_id: str | None = None):
        detail = f"{resource} not found"
        if resource_id:
            detail = f"{resource} with id '{resource_id}' not found"
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class UnauthorizedException(BusinessException):
    """Exception for authentication errors."""

    def __init__(self, detail: str = "Authentication required"):
        super().__init__(detail=detail, status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenException(BusinessException):
    """Exception for authorization errors."""

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)
