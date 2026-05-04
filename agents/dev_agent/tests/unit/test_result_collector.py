from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.dev_agent.core.config import DevCoreConfig
from agents.dev_agent.core.result_collector import ResultCollector
from agents.dev_agent.models.schemas import VALID_TRANSITIONS
from shared.schemas.event import EventTypes


def test_executing_to_security_scanning():
    assert "security_scanning" in VALID_TRANSITIONS["executing"]


def test_security_scanning_to_mr_creating():
    assert "mr_creating" in VALID_TRANSITIONS["security_scanning"]


def test_mr_created_to_qa_triggered():
    assert "qa_triggered" in VALID_TRANSITIONS["mr_created"]


def test_reviewing_to_completed():
    assert "completed" in VALID_TRANSITIONS["reviewing"]


def test_reviewing_to_failed():
    assert "failed" in VALID_TRANSITIONS["reviewing"]


def test_failed_can_retry():
    assert "planning" in VALID_TRANSITIONS["failed"]


def test_completed_is_terminal():
    assert VALID_TRANSITIONS["completed"] == set()


@pytest.mark.asyncio
async def test_result_collector_uses_injected_gitlab_project_id_for_qa_event():
    task = SimpleNamespace(
        id="dev-1",
        wp_id=123,
        task_title="Dev Agent task",
        risk_level="MEDIUM",
    )
    repo = AsyncMock()
    repo.update_status = AsyncMock(return_value=True)
    gitlab = AsyncMock()
    gitlab.check_existing_mr = AsyncMock(return_value=None)
    gitlab.create_mr = AsyncMock(return_value={"iid": 7, "web_url": "https://mr/7"})
    scanner = AsyncMock()
    scanner.scan = AsyncMock(return_value=MagicMock(passed=True, issues=[]))
    notifier = AsyncMock()

    collector = ResultCollector(
        repo=repo,
        log_repo=AsyncMock(),
        gitlab=gitlab,
        notifier=notifier,
        security_scanner=scanner,
        config=DevCoreConfig.from_values(gitlab_project_id=42),
    )

    events = await collector.handle_completion(task, {"status": "completed"})

    qa_event = next(event for event in events if event.event_type == EventTypes.QA_RUN_REQUESTED)
    assert qa_event.payload["gitlab_project_id"] == 42
