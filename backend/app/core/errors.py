"""Common error response format (API spec, section 9).

Every error is returned as {"error": {"code", "message", "details", "fieldErrors"}}.
Clients branch on `code`; `message` is a default text that can be shown to users.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Codes for HTTPExceptions raised without an ApiError, e.g. by auth dependencies or routing.
_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "INVALID_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHENTICATED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


class ApiError(Exception):
    """Raise from routes or services to return a spec error, e.g. ApiError(404, "BAR_NOT_FOUND", ...)."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        field_errors: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.field_errors = field_errors or []


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    field_errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details, "fieldErrors": field_errors or []}}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def field_path(loc: tuple[str | int, ...]) -> str:
    """("query", "lat") -> "lat"; ("body", "items", 0, "price") -> "items[0].price"."""
    if loc and loc[0] in {"query", "path", "body", "header"}:
        loc = loc[1:]
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        elif path:
            path += f".{part}"
        else:
            path = str(part)
    return path


async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.field_errors)


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    field_errors = [
        {"path": field_path(tuple(error["loc"])), "code": error["type"].upper(), "message": error["msg"]}
        for error in exc.errors()
    ]
    return error_response(422, "VALIDATION_FAILED", "입력값을 확인해 주세요.", field_errors=field_errors)


async def _http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
