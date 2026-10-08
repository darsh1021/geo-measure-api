import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

_CODES = {
    404: "NOT_FOUND",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_FILE_TYPE",
    422: "UNPROCESSABLE_FILE",
    500: "INTERNAL_ERROR",
}


def error_response(status, code, message, *, file_id=None, details=None, headers=None):
    error = {"status": status, "code": code, "message": message}
    if file_id:
        error["file_id"] = file_id
    if details is not None:
        error["details"] = details
    return JSONResponse({"error": error}, status_code=status, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    # Registered on Starlette's HTTPException so framework-raised errors
    # (unknown route, wrong method) get the same shape as ours.
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        file_id = None
        if isinstance(exc.detail, dict):  # our upload errors carry the file id
            file_id = exc.detail.get("id")
            message = exc.detail.get("error", "Request failed")
        else:
            message = str(exc.detail)
        return error_response(
            exc.status_code,
            _CODES.get(exc.status_code, f"HTTP_{exc.status_code}"),
            message,
            file_id=file_id,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(
            422, "VALIDATION_ERROR", "Request validation failed",
            details=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(500, "INTERNAL_ERROR", "Internal server error")
