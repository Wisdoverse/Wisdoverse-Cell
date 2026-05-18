"""
Integration tests for API endpoints

Tests API route integration with the Agent:
- HTTP requests delegate to the Agent correctly
- Response formats are correct
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path.
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from agents.requirement_manager.core.ingest_use_cases import IngestUseCaseResult


class TestIngestAPI:
    """Ingest API tests."""

    @pytest.mark.asyncio
    async def test_upload_delegates_to_ingest_use_case(self):
        """Upload endpoint delegates to the ingest use case."""
        from agents.requirement_manager.api.dependencies import get_ingest_use_case
        from agents.requirement_manager.app.main import app

        ingest_use_case = MagicMock()
        ingest_use_case.upload_content = AsyncMock(
            return_value=IngestUseCaseResult(
                meeting_id="mtg_test123",
                requirements_extracted=2,
                questions_generated=1,
            )
        )
        app.dependency_overrides[get_ingest_use_case] = lambda: ingest_use_case
        response = None
        # Mock lifespan to skip agent startup
        try:
            with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:
                mock_main_agent.startup = AsyncMock()
                mock_main_agent.shutdown = AsyncMock()

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/ingest/upload",
                        json={
                            "content": "会议内容：讨论了新功能需求",
                            "source": "upload",
                            "title": "测试会议"
                        }
                    )
        finally:
            app.dependency_overrides.pop(get_ingest_use_case, None)

        assert response is not None
        assert response.status_code == 200
        ingest_use_case.upload_content.assert_awaited_once_with(
            content="会议内容：讨论了新功能需求",
            source="upload",
            title="测试会议",
            meeting_date=None,
            participants=None,
            context=None,
        )


class TestFeedbackAPI:
    """Feedback API tests."""

    @pytest.mark.asyncio
    async def test_confirm_delegates_to_feedback_use_case(self):
        """Confirm endpoint delegates to the feedback use case."""
        # Create mock requirement with all RequirementOut fields.
        from datetime import datetime

        from agents.requirement_manager.api.dependencies import (
            get_requirement_feedback_use_case,
        )
        from agents.requirement_manager.app.main import app
        mock_requirement = MagicMock()
        mock_requirement.id = "req_123"
        mock_requirement.title = "测试需求"
        mock_requirement.description = "描述"
        mock_requirement.status = "CONFIRMED"
        mock_requirement.priority = "HIGH"
        mock_requirement.category = "功能"
        mock_requirement.source_quote = None
        mock_requirement.source_meeting_ids = []
        mock_requirement.confirmed_by = "测试用户"
        mock_requirement.confirmed_at = datetime.now()
        mock_requirement.open_questions = []
        mock_requirement.created_at = datetime.now()
        mock_requirement.updated_at = datetime.now()

        feedback_use_case = MagicMock()
        feedback_use_case.confirm_requirement = AsyncMock(return_value=mock_requirement)
        app.dependency_overrides[get_requirement_feedback_use_case] = (
            lambda: feedback_use_case
        )

        try:
            with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:
                mock_main_agent.startup = AsyncMock()
                mock_main_agent.shutdown = AsyncMock()

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    await client.put(
                        "/api/v1/requirements/req_123/confirm",
                        json={"confirmed_by": "测试用户"}
                    )
        finally:
            app.dependency_overrides.pop(get_requirement_feedback_use_case, None)

        feedback_use_case.confirm_requirement.assert_awaited_once_with(
            requirement_id="req_123",
            confirmed_by="测试用户",
        )

    @pytest.mark.asyncio
    async def test_reject_delegates_to_feedback_use_case(self):
        """Reject endpoint delegates to the feedback use case."""
        # Create mock requirement with all RequirementOut fields.
        from datetime import datetime

        from agents.requirement_manager.api.dependencies import (
            get_requirement_feedback_use_case,
        )
        from agents.requirement_manager.app.main import app
        mock_requirement = MagicMock()
        mock_requirement.id = "req_123"
        mock_requirement.title = "测试需求"
        mock_requirement.description = "描述"
        mock_requirement.status = "REJECTED"
        mock_requirement.priority = "HIGH"
        mock_requirement.category = "功能"
        mock_requirement.source_quote = None
        mock_requirement.source_meeting_ids = []
        mock_requirement.confirmed_by = None
        mock_requirement.confirmed_at = None
        mock_requirement.open_questions = []
        mock_requirement.created_at = datetime.now()
        mock_requirement.updated_at = datetime.now()

        feedback_use_case = MagicMock()
        feedback_use_case.reject_requirement = AsyncMock(return_value=mock_requirement)
        app.dependency_overrides[get_requirement_feedback_use_case] = (
            lambda: feedback_use_case
        )

        try:
            with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:
                mock_main_agent.startup = AsyncMock()
                mock_main_agent.shutdown = AsyncMock()

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    await client.put(
                        "/api/v1/requirements/req_123/reject",
                        json={
                            "reason": "不符合产品方向",
                            "rejected_by": "产品经理"
                        }
                    )
        finally:
            app.dependency_overrides.pop(get_requirement_feedback_use_case, None)

        feedback_use_case.reject_requirement.assert_awaited_once_with(
            requirement_id="req_123",
            reason="不符合产品方向",
            rejected_by="产品经理",
        )


class TestAgentEventPublishing:
    """Agent event publishing tests."""

    @pytest.mark.asyncio
    async def test_confirm_publishes_event(self):
        """Confirming a requirement publishes an event."""
        from agents.requirement_manager.models import Requirement
        from agents.requirement_manager.service.agent import RequirementManagerAgent
        from shared.schemas.event import EventTypes

        # Create an Agent with mock dependencies.
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(return_value=True)
        mock_bus.connect = AsyncMock()
        mock_bus.disconnect = AsyncMock()

        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=mock_bus,
            vectors=MagicMock()
        )

        # Mock repository
        mock_requirement = MagicMock(spec=Requirement)
        mock_requirement.id = "req_123"
        mock_requirement.title = "测试需求"
        mock_requirement.priority = "HIGH"
        mock_requirement.category = "功能"

        mock_session = MagicMock()

        with patch("agents.requirement_manager.service.agent.RequirementRepository") as MockRepo:
            mock_repo_instance = MagicMock()
            mock_repo_instance.confirm = AsyncMock(return_value=mock_requirement)
            MockRepo.return_value = mock_repo_instance

            await test_agent.confirm_requirement(
                requirement_id="req_123",
                confirmed_by="测试用户",
                session=mock_session
            )

        # Validate event publishing.
        mock_bus.publish.assert_called_once()
        published_event = mock_bus.publish.call_args[0][0]

        assert published_event.event_type == EventTypes.REQUIREMENT_CONFIRMED
        assert published_event.source_agent == "requirement-manager"
        assert published_event.payload["requirement_id"] == "req_123"
        assert published_event.payload["confirmed_by"] == "测试用户"

    @pytest.mark.asyncio
    async def test_event_publish_failure_does_not_block(self):
        """Event publishing failures do not block the main flow."""
        from agents.requirement_manager.models import Requirement
        from agents.requirement_manager.service.agent import RequirementManagerAgent

        # Create a mock event bus that simulates publish failure.
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=Exception("Redis connection failed"))
        mock_bus.connect = AsyncMock()
        mock_bus.disconnect = AsyncMock()

        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=mock_bus,
            vectors=MagicMock()
        )

        mock_requirement = MagicMock(spec=Requirement)
        mock_requirement.id = "req_123"
        mock_requirement.title = "测试需求"
        mock_requirement.priority = "HIGH"
        mock_requirement.category = "功能"

        mock_session = MagicMock()

        with patch("agents.requirement_manager.service.agent.RequirementRepository") as MockRepo:
            mock_repo_instance = MagicMock()
            mock_repo_instance.confirm = AsyncMock(return_value=mock_requirement)
            MockRepo.return_value = mock_repo_instance

            # Should not raise.
            result = await test_agent.confirm_requirement(
                requirement_id="req_123",
                confirmed_by="测试用户",
                session=mock_session
            )

        # Validate that the main flow completed.
        assert result == mock_requirement
