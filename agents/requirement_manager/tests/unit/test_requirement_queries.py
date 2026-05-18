from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.requirement_queries import RequirementQueryService


def _requirement_row(requirement_id: str = "req_test", history: list[dict] | None = None):
    timestamp = datetime.now(UTC)
    return SimpleNamespace(
        id=requirement_id,
        title="Test requirement",
        description="Test description",
        source_quote="source quote",
        status="pending",
        priority="high",
        category="Feature",
        source_meeting_ids=["meet_1"],
        confirmed_by=None,
        confirmed_at=None,
        open_questions=[],
        history=history or [],
        created_at=timestamp,
        updated_at=timestamp,
    )


def _meeting_row(meeting_id: str = "meet_test"):
    timestamp = datetime.now(UTC)
    return SimpleNamespace(
        id=meeting_id,
        source="upload",
        title="Test meeting",
        meeting_date=timestamp,
        participants=["Alice"],
        processed=False,
        created_at=timestamp,
    )


def _service(requirement_repo, meeting_repo=None, vector_stats=None):
    if meeting_repo is None:
        meeting_repo = AsyncMock()
    if vector_stats is None:
        vector_stats = AsyncMock()
        vector_stats.get_stats = AsyncMock(return_value={"total_documents": 0})
        vector_stats.search = AsyncMock(return_value=[])
        vector_stats.find_similar = AsyncMock(return_value=[])
    return RequirementQueryService(
        requirement_repository=requirement_repo,
        meeting_repository=meeting_repo,
        vector_stats=vector_stats,
    )


@pytest.mark.asyncio
async def test_list_requirements_returns_paginated_read_model():
    requirement_repo = AsyncMock()
    requirement_repo.list_all = AsyncMock(return_value=([_requirement_row()], 3))

    result = await _service(requirement_repo).list_requirements(
        status="pending",
        category="Feature",
        priority="high",
        page=2,
        page_size=1,
    )

    assert result.total == 3
    assert result.page == 2
    assert result.page_size == 1
    assert result.items[0].id == "req_test"
    requirement_repo.list_all.assert_awaited_once_with(
        status="pending",
        category="Feature",
        priority="high",
        skip=1,
        limit=1,
    )


@pytest.mark.asyncio
async def test_get_requirement_returns_none_for_missing_row():
    requirement_repo = AsyncMock()
    requirement_repo.get_by_id = AsyncMock(return_value=None)

    result = await _service(requirement_repo).get_requirement("req_missing")

    assert result is None


@pytest.mark.asyncio
async def test_search_requirements_delegates_to_vector_index():
    requirement_repo = AsyncMock()
    vector_stats = AsyncMock()
    vector_stats.search = AsyncMock(
        return_value=[
            {
                "id": "req_match",
                "title": "Matched requirement",
                "category": "Feature",
                "similarity": 0.87,
            }
        ]
    )

    result = await _service(
        requirement_repo,
        vector_stats=vector_stats,
    ).search_requirements(
        query="recording",
        category="Feature",
        limit=3,
        min_similarity=0.8,
    )

    assert result.query == "recording"
    assert result.items[0].id == "req_match"
    vector_stats.search.assert_awaited_once_with(
        query="recording",
        n_results=3,
        category_filter="Feature",
        min_similarity=0.8,
    )


@pytest.mark.asyncio
async def test_list_meetings_returns_paginated_read_model():
    requirement_repo = AsyncMock()
    meeting_repo = AsyncMock()
    meeting_repo.list_all = AsyncMock(return_value=([_meeting_row()], 2))

    result = await _service(requirement_repo, meeting_repo).list_meetings(
        source="upload",
        page=2,
        page_size=1,
    )

    assert result.total == 2
    assert result.items[0].id == "meet_test"
    meeting_repo.list_all.assert_awaited_once_with(
        source="upload",
        skip=1,
        limit=1,
    )


@pytest.mark.asyncio
async def test_get_stats_combines_requirement_meeting_and_vector_counts():
    requirement_repo = AsyncMock()
    requirement_repo.count_by_status = AsyncMock(return_value={"pending": 2})
    meeting_repo = AsyncMock()
    meeting_repo.list_all = AsyncMock(return_value=([], 4))
    meeting_repo.list_unprocessed = AsyncMock(return_value=[_meeting_row()])
    vector_stats = AsyncMock()
    vector_stats.get_stats = AsyncMock(return_value={"total_documents": 9})

    result = await _service(
        requirement_repo,
        meeting_repo,
        vector_stats,
    ).get_stats()

    assert result.requirements_by_status == {"pending": 2}
    assert result.total_meetings == 4
    assert result.unprocessed_meetings == 1
    assert result.vector_store_count == 9


@pytest.mark.asyncio
async def test_get_enhanced_stats_returns_trends_and_dimensions():
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

    result = await _service(
        requirement_repo,
        meeting_repo,
        vector_stats,
    ).get_enhanced_stats()

    assert result.requirements_by_status == {"pending": 2}
    assert result.requirements_by_priority == {"high": 1}
    assert result.requirements_by_category == {"Feature": 1}
    assert result.weekly_trend == [{"date": "05/17", "count": 2}]
    assert result.today_count == 2


@pytest.mark.asyncio
async def test_find_similar_requirements_checks_existence_and_queries_vector_index():
    requirement_repo = AsyncMock()
    requirement_repo.get_by_id = AsyncMock(return_value=_requirement_row())
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

    result = await _service(
        requirement_repo,
        vector_stats=vector_stats,
    ).find_similar_requirements(
        "req_test",
        limit=3,
        min_similarity=0.8,
    )

    assert result is not None
    assert result.requirement_id == "req_test"
    assert result.similar[0].id == "req_other"
    vector_stats.find_similar.assert_awaited_once_with(
        requirement_id="req_test",
        n_results=3,
        min_similarity=0.8,
    )


@pytest.mark.asyncio
async def test_requirement_history_and_diff_are_read_models():
    history = [
        {"action": "created", "detail": "initial"},
        {"action": "confirmed", "detail": "accepted"},
    ]
    requirement_repo = AsyncMock()
    requirement_repo.get_by_id = AsyncMock(
        return_value=_requirement_row(history=history),
    )
    service = _service(requirement_repo)

    history_result = await service.get_requirement_history("req_test")
    diff_result = await service.get_requirement_diff(
        "req_test",
        from_index=1,
        to_index=-1,
    )

    assert history_result is not None
    assert history_result.total_changes == 2
    assert diff_result is not None
    assert diff_result.from_index == 1
    assert diff_result.to_index == 1
    assert diff_result.changes == [history[1]]
