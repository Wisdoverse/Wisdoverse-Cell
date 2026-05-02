import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_api_info_returns_correct_name():
    from agents.capabilities.requirements.app.routes import api_info_router

    app = FastAPI()
    app.include_router(api_info_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1")
    assert r.status_code == 200
    assert r.json()["name"] == "Requirement Manager Agent"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_path", "expected_path"),
    [
        ("/api", "/api/v1"),
        ("/api/", "/api/v1"),
        ("/api/requirements", "/api/v1/requirements"),
        ("/api/v1/requirements", "/api/v1/requirements"),
    ],
)
async def test_api_v1_redirect(request_path: str, expected_path: str):
    from agents.capabilities.requirements.app.routes import api_v1_redirect_router

    app = FastAPI()
    app.include_router(api_v1_redirect_router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    ) as c:
        r = await c.get(request_path)
    assert r.status_code == 307
    assert r.headers["location"] == f"http://test{expected_path}"
