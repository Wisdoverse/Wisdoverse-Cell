"""Extracted route endpoints for requirement_manager."""
from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse

api_info_router = APIRouter()
api_v1_redirect_router = APIRouter()


@api_info_router.get("/api/v1")
async def api_info():
    """API information endpoint."""
    return {
        "name": "Requirement Manager Agent",
        "version": "2.0.0",
        "api_version": "v1",
        "endpoints": {
            "ingest": "/api/v1/ingest/upload, /api/v1/ingest/feishu",
            "requirements": "/api/v1/requirements, /api/v1/requirements/search",
            "feedback": "/api/v1/requirements/{id}/confirm, /api/v1/requirements/{id}/reject",
            "conflict": "/api/v1/requirements/check-conflict",
            "export": "/api/v1/export/prd, /api/v1/export/questions",
            "questions": "/api/v1/questions/open, /api/v1/questions/{id}/answer",
            "admin": "/api/v1/admin/llm-usage, /api/v1/admin/circuit-breaker",
        },
    }


@api_v1_redirect_router.api_route(
    "/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def api_v1_redirect(request: Request, path: str):
    """Redirect unversioned /api/* to /api/v1/* for backward compatibility."""
    new_url = request.url.replace(path=f"/api/v1/{path}")
    return RedirectResponse(url=str(new_url), status_code=307)
