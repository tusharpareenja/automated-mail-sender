from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict | list | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", details: dict | None = None) -> None:
        super().__init__("not_found", message, 404, details)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__("unauthorized", message, 401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "You do not have access to this resource") -> None:
        super().__init__("forbidden", message, 403)


class ConflictError(AppError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("conflict", message, 409, details)


class RateLimitError(AppError):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__("rate_limited", message, 429)


class ProviderError(AppError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("provider_error", message, 502, details)


class ValidationError(AppError):
    def __init__(self, message: str, details: dict | list | None = None) -> None:
        super().__init__("validation_error", message, 400, details)


def error_body(code: str, message: str, details: dict | list | None = None) -> dict:
    payload: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_error",
                "Request validation failed",
                exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "An unexpected error occurred"),
        )
