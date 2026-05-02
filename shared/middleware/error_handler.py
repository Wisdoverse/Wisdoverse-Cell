"""Global exception handler using unified ErrorResponse format."""


from fastapi import Request
from fastapi.responses import JSONResponse

from shared.schemas.error import ErrorResponse
from shared.utils.logger import get_logger

logger = get_logger("error_handler")


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
    error = ErrorResponse(
        code="INTERNAL_ERROR",
        message="Internal service error. Please try again later.",
        trace_id=trace_id,
    )
    return JSONResponse(status_code=500, content=error.model_dump())
