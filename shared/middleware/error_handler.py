"""FastAPI exception handlers for the shared API error contract."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.api import (
    http_exception_error_response,
    internal_error_response,
    validation_error_response,
)
from shared.utils.logger import get_logger

logger = get_logger("error_handler")


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Return HTTPException responses using the shared structured envelope."""
    return http_exception_error_response(request, exc)


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return validation failures using the shared structured envelope."""
    return validation_error_response(request=request, errors=exc.errors())


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler that returns a consistent ErrorResponse JSON body."""
    trace_id = getattr(request.state, "trace_id", "")
    logger.error(
        "unhandled_exception",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
        trace_id=trace_id,
    )
    return internal_error_response(request)
