"""
Integration tests for the requirement manager agent gRPC boundary.

The runtime implementation lives under
``agents.requirement_manager.grpc``. ``shared.grpc.server`` is kept only
as a deprecated compatibility entry point and must not expose capability
runtime classes.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.grpc import requirement_pb2 as pb2
from agents.requirement_manager.grpc.servicer import RequirementServicer


@pytest.fixture
def mock_context():
    """Create a mock gRPC context."""
    context = MagicMock()
    context.set_code = MagicMock()
    context.set_details = MagicMock()
    return context


@pytest.fixture
def mock_requirement():
    """Create a mock requirement record."""
    req = MagicMock()
    req.id = "req_001"
    req.title = "Test Requirement"
    req.description = "Test Description"
    req.status = "pending"
    req.priority = "P0"
    req.category = "feature"
    req.source_quote = "User said..."
    req.confirmed_by = None
    req.confirmed_at = None
    req.rejection_reason = None
    req.created_at = datetime.now(UTC)
    req.updated_at = datetime.now(UTC)
    return req


def test_shared_grpc_server_entrypoint_is_deprecated():
    """The shared package must not expose requirements runtime classes."""
    from shared.grpc.server import main

    with pytest.raises(SystemExit, match="agents.requirement_manager.grpc.server"):
        main()


class TestRequirementServicer:
    """Tests for the canonical requirements gRPC servicer."""

    @pytest.mark.asyncio
    async def test_health_check_uses_requirements_boundary(self, mock_context):
        """HealthCheck should execute through the canonical servicer."""
        health_store = AsyncMock()
        health_store.is_database_ready = AsyncMock(return_value=True)
        servicer = RequirementServicer(agent=None, health_store=health_store)

        response = await servicer.HealthCheck(pb2.HealthRequest(), mock_context)

        assert response.healthy is True
        assert response.version == "1.0.0"
        assert response.services["db"] is True
        assert response.services["agent"] is False
        health_store.is_database_ready.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_requirements_uses_requirements_repository(
        self,
        mock_context,
        mock_requirement,
    ):
        """ListRequirements should use the requirement manager gRPC store."""
        requirement_store = AsyncMock()
        requirement_store.list_requirements = AsyncMock(
            return_value=([mock_requirement], 1)
        )
        servicer = RequirementServicer(
            agent=None,
            requirement_store=requirement_store,
        )

        response = await servicer.ListRequirements(
            pb2.ListRequest(page=1, page_size=20),
            mock_context,
        )

        assert response.total == 1
        assert response.total_pages == 1
        assert response.requirements[0].id == "req_001"
        requirement_store.list_requirements.assert_awaited_once_with(
            status=None,
            page=1,
            page_size=20,
        )

    @pytest.mark.asyncio
    async def test_confirm_requirement_uses_agent_boundary(self, mock_context, mock_requirement):
        """ConfirmRequirement should call the injected requirements agent."""
        agent = AsyncMock()
        mock_requirement.status = "confirmed"
        agent.confirm_requirement.return_value = mock_requirement
        servicer = RequirementServicer(agent=agent)

        response = await servicer.ConfirmRequirement(
            pb2.ConfirmRequest(id="req_001", confirmed_by="user123"),
            mock_context,
        )

        assert response.success is True
        assert response.requirement.status == "confirmed"
        agent.confirm_requirement.assert_called_once_with(
            requirement_id="req_001",
            confirmed_by="user123",
        )

    @pytest.mark.asyncio
    async def test_extract_requirements_uses_agent_and_repository(
        self,
        mock_context,
        mock_requirement,
    ):
        """ExtractRequirements should call the injected agent and gRPC store."""
        agent = AsyncMock()
        result = MagicMock()
        result.meeting_id = "meeting_001"
        result.requirements = ["req_001"]
        result.open_questions = ["Clarify priority"]
        agent.ingest_meeting.return_value = result
        requirement_store = AsyncMock()
        requirement_store.get_many = AsyncMock(return_value=[mock_requirement])
        servicer = RequirementServicer(
            agent=agent,
            requirement_store=requirement_store,
        )

        response = await servicer.ExtractRequirements(
            pb2.ExtractRequest(
                content="We need offline mode.",
                source="chat",
                context="Product meeting",
                participants=["Alice", "Bob"],
            ),
            mock_context,
        )

        assert response.success is True
        assert response.meeting_id == "meeting_001"
        assert response.questions_count == 1
        assert response.requirements[0].id == "req_001"
        agent.ingest_meeting.assert_called_once_with(
            content="We need offline mode.",
            source="chat",
            context="Product meeting",
            participants=["Alice", "Bob"],
        )
