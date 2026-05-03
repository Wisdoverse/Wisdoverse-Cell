"""
Integration tests for the requirement manager agent gRPC boundary.

The runtime implementation lives under
``agents.requirement_manager.grpc``. ``shared.grpc.server`` is kept only
as a deprecated compatibility entry point and must not expose capability
runtime classes.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

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
        servicer = RequirementServicer(agent=None)

        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            response = await servicer.HealthCheck(pb2.HealthRequest(), mock_context)

        assert response.healthy is True
        assert response.version == "1.0.0"
        assert response.services["db"] is True
        assert response.services["agent"] is False

    @pytest.mark.asyncio
    async def test_list_requirements_uses_requirements_repository(
        self,
        mock_context,
        mock_requirement,
    ):
        """ListRequirements should use the requirement manager agent repository."""
        servicer = RequirementServicer(agent=None)

        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            with patch("agents.requirement_manager.grpc.servicer.RequirementRepository") as repo_cls:
                repo = AsyncMock()
                repo.list_all.return_value = [mock_requirement]
                repo_cls.return_value = repo

                response = await servicer.ListRequirements(
                    pb2.ListRequest(page=1, page_size=20),
                    mock_context,
                )

        assert response.total == 1
        assert response.total_pages == 1
        assert response.requirements[0].id == "req_001"
        repo.list_all.assert_called_once()

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
        """ExtractRequirements should call the injected agent and canonical repository."""
        agent = AsyncMock()
        result = MagicMock()
        result.meeting_id = "meeting_001"
        result.requirements = ["req_001"]
        result.open_questions = ["Clarify priority"]
        agent.ingest_meeting.return_value = result
        servicer = RequirementServicer(agent=agent)

        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            with patch("agents.requirement_manager.grpc.servicer.RequirementRepository") as repo_cls:
                repo = AsyncMock()
                repo.get_by_id.return_value = mock_requirement
                repo_cls.return_value = repo

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
