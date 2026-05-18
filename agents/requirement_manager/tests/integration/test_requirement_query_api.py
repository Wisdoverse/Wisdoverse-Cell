"""Integration tests for requirement query API routes."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from httpx import ASGITransport, AsyncClient

from agents.requirement_manager.core.requirement_queries import RequirementQueryService


def _requirement_row(
    requirement_id: str = "req_query_001",
    history: list[dict] | None = None,
):
    timestamp = datetime.now(UTC)
    return SimpleNamespace(
        id=requirement_id,
        title="Query test requirement",
        description="Query test description",
        source_quote="source quote",
        status="pending",
        priority="high",
        category="Feature",
        source_meeting_ids=["meet_query_001"],
        confirmed_by=None,
        confirmed_at=None,
        open_questions=[],
        history=history or [],
        created_at=timestamp,
        updated_at=timestamp,
    )


def _meeting_row(meeting_id: str = "meet_query_001"):
    timestamp = datetime.now(UTC)
    return SimpleNamespace(
        id=meeting_id,
        source="upload",
        title="Query test meeting",
        meeting_date=timestamp,
        participants=["Alice"],
        processed=False,
        created_at=timestamp,
    )


async def _get_with_requirement_query_service(
    app,
    requirement_repo,
    meeting_repo,
    vector_stats,
    path: str,
):
    from agents.requirement_manager.api.dependencies import (
        get_requirement_query_service,
    )

    app.dependency_overrides[get_requirement_query_service] = (
        lambda: RequirementQueryService(
            requirement_repository=requirement_repo,
            meeting_repository=meeting_repo,
            vector_stats=vector_stats,
        )
    )
    try:
        with patch("agents.requirement_manager.app.main.agent") as mock_agent:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                return await client.get(path)
    finally:
        app.dependency_overrides.pop(get_requirement_query_service, None)


@pytest.mark.asyncio
async def test_list_requirements_delegates_to_query_service():
    from agents.requirement_manager.app.main import app

    requirement_repo = AsyncMock()
    requirement_repo.list_all = AsyncMock(return_value=([_requirement_row()], 1))
    meeting_repo = AsyncMock()
    vector_stats = AsyncMock()
    vector_stats.get_stats = AsyncMock(return_value={"total_documents": 0})
    vector_stats.search = AsyncMock(return_value=[])

    response = await _get_with_requirement_query_service(
        app,
        requirement_repo,
        meeting_repo,
        vector_stats,
        "/api/v1/requirements?status=pending&page=2&page_size=1",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 2
    assert data["items"][0]["id"] == "req_query_001"
    requirement_repo.list_all.assert_awaited_once_with(
        status="pending",
        category=None,
        priority=None,
        skip=1,
        limit=1,
    )


@pytest.mark.asyncio
async def test_get_requirement_not_found_uses_shared_error_contract():
    from agents.requirement_manager.app.main import app

    requirement_repo = AsyncMock()
    requirement_repo.get_by_id = AsyncMock(return_value=None)
    meeting_repo = AsyncMock()
    vector_stats = AsyncMock()
    vector_stats.get_stats = AsyncMock(return_value={"total_documents": 0})
    vector_stats.search = AsyncMock(return_value=[])

    response = await _get_with_requirement_query_service(
        app,
        requirement_repo,
        meeting_repo,
        vector_stats,
        "/api/v1/requirements/req_missing",
    )

    assert response.status_code == 404
    assert response.headers["x-error-code"] == "requirement.not_found"


@pytest.mark.asyncio
async def test_list_meetings_delegates_to_query_service():
    from agents.requirement_manager.app.main import app

    requirement_repo = AsyncMock()
    meeting_repo = AsyncMock()
    meeting_repo.list_all = AsyncMock(return_value=([_meeting_row()], 1))
    vector_stats = AsyncMock()
    vector_stats.get_stats = AsyncMock(return_value={"total_documents": 0})
    vector_stats.search = AsyncMock(return_value=[])

    response = await _get_with_requirement_query_service(
        app,
        requirement_repo,
        meeting_repo,
        vector_stats,
        "/api/v1/meetings?source=upload&page=2&page_size=1",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == "meet_query_001"
    meeting_repo.list_all.assert_awaited_once_with(
        source="upload",
        skip=1,
        limit=1,
    )


@pytest.mark.asyncio
async def test_stats_routes_delegate_to_query_service():
    from agents.requirement_manager.app.main import app

    requirement_repo = AsyncMock()
    requirement_repo.count_by_status = AsyncMock(return_value={"pending": 2})
    requirement_repo.count_by_priority = AsyncMock(return_value={"high": 1})
    requirement_repo.count_by_category = AsyncMock(return_value={"Feature": 1})
    requirement_repo.get_daily_counts = AsyncMock(
        return_value=[{"date": "05/17", "count": 2}],
    )
    requirement_repo.count_today = AsyncMock(return_value=2)
    meeting_repo = AsyncMock()
    meeting_repo.list_all = AsyncMock(return_value=([], 4))
    meeting_repo.list_unprocessed = AsyncMock(return_value=[_meeting_row()])
    vector_stats = AsyncMock()
    vector_stats.get_stats = AsyncMock(return_value={"total_documents": 9})
    vector_stats.search = AsyncMock(return_value=[])

    response = await _get_with_requirement_query_service(
        app,
        requirement_repo,
        meeting_repo,
        vector_stats,
        "/api/v1/stats/enhanced",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requirements_by_status"] == {"pending": 2}
    assert data["requirements_by_priority"] == {"high": 1}
    assert data["requirements_by_category"] == {"Feature": 1}
    assert data["total_meetings"] == 4
    assert data["unprocessed_meetings"] == 1
    assert data["vector_store_count"] == 9
    assert data["weekly_trend"] == [{"date": "05/17", "count": 2}]


@pytest.mark.asyncio
async def test_semantic_search_delegates_to_query_service():
    from agents.requirement_manager.app.main import app

    requirement_repo = AsyncMock()
    meeting_repo = AsyncMock()
    vector_stats = AsyncMock()
    vector_stats.search = AsyncMock(
        return_value=[
            {
                "id": "req_match",
                "title": "Matched requirement",
                "category": "Feature",
                "similarity": 0.87,
            }
        ],
    )
    vector_stats.get_stats = AsyncMock(return_value={"total_documents": 1})

    response = await _get_with_requirement_query_service(
        app,
        requirement_repo,
        meeting_repo,
        vector_stats,
        "/api/v1/requirements/search?q=recording&category=Feature&limit=3&min_similarity=0.8",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "recording"
    assert data["items"][0]["id"] == "req_match"
    vector_stats.search.assert_awaited_once_with(
        query="recording",
        n_results=3,
        category_filter="Feature",
        min_similarity=0.8,
    )


@pytest.mark.asyncio
async def test_similar_requirements_delegates_to_query_service():
    from agents.requirement_manager.app.main import app

    requirement_repo = AsyncMock()
    requirement_repo.get_by_id = AsyncMock(return_value=_requirement_row())
    meeting_repo = AsyncMock()
    vector_stats = AsyncMock()
    vector_stats.find_similar = AsyncMock(
        return_value=[
            {
                "id": "req_other",
                "title": "Other requirement",
                "category": "Feature",
                "similarity": 0.91,
            }
        ],
    )
    vector_stats.get_stats = AsyncMock(return_value={"total_documents": 1})

    response = await _get_with_requirement_query_service(
        app,
        requirement_repo,
        meeting_repo,
        vector_stats,
        "/api/v1/requirements/req_query_001/similar?limit=3&min_similarity=0.8",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requirement_id"] == "req_query_001"
    assert data["similar"][0]["id"] == "req_other"
    vector_stats.find_similar.assert_awaited_once_with(
        requirement_id="req_query_001",
        n_results=3,
        min_similarity=0.8,
    )


@pytest.mark.asyncio
async def test_history_and_diff_routes_delegate_to_query_service():
    from agents.requirement_manager.app.main import app

    history = [
        {"action": "created", "detail": "initial"},
        {"action": "confirmed", "detail": "accepted"},
    ]
    requirement_repo = AsyncMock()
    requirement_repo.get_by_id = AsyncMock(
        return_value=_requirement_row(history=history),
    )
    meeting_repo = AsyncMock()
    vector_stats = AsyncMock()
    vector_stats.get_stats = AsyncMock(return_value={"total_documents": 0})
    vector_stats.search = AsyncMock(return_value=[])
    vector_stats.find_similar = AsyncMock(return_value=[])

    history_response = await _get_with_requirement_query_service(
        app,
        requirement_repo,
        meeting_repo,
        vector_stats,
        "/api/v1/requirements/req_query_001/history",
    )
    diff_response = await _get_with_requirement_query_service(
        app,
        requirement_repo,
        meeting_repo,
        vector_stats,
        "/api/v1/requirements/req_query_001/diff?from_index=1",
    )

    assert history_response.status_code == 200
    assert history_response.json()["total_changes"] == 2
    assert diff_response.status_code == 200
    assert diff_response.json()["from_index"] == 1
    assert diff_response.json()["changes"] == [history[1]]
