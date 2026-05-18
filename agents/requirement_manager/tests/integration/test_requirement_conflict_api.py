"""Integration tests for requirement conflict-check API routes."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from httpx import ASGITransport, AsyncClient

from agents.requirement_manager.core.comparator import ComparisonResult, RelationType


@pytest.mark.asyncio
async def test_check_conflict_delegates_to_use_case():
    from agents.requirement_manager.api.dependencies import (
        get_requirement_conflict_check_use_case,
    )
    from agents.requirement_manager.app.main import app

    use_case = MagicMock()
    use_case.check_conflict = AsyncMock(
        return_value=ComparisonResult(
            relation=RelationType.UPDATE,
            confidence=0.78,
            explanation="Refines an existing requirement",
            suggested_action="Review and merge",
            related_requirement_id="req_existing",
            merge_suggestion="Merge descriptions",
        )
    )
    app.dependency_overrides[get_requirement_conflict_check_use_case] = lambda: use_case
    try:
        with patch("agents.requirement_manager.app.main.agent") as mock_agent:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/v1/requirements/check-conflict",
                    json={
                        "title": "Offline recording",
                        "description": "Import offline recordings",
                        "category": "Feature",
                        "exclude_ids": ["req_current"],
                    },
                )
    finally:
        app.dependency_overrides.pop(get_requirement_conflict_check_use_case, None)

    assert response.status_code == 200
    assert response.json()["relation"] == "update"
    assert response.json()["related_requirement_id"] == "req_existing"
    use_case.check_conflict.assert_awaited_once_with(
        title="Offline recording",
        description="Import offline recordings",
        category="Feature",
        exclude_ids=["req_current"],
    )
