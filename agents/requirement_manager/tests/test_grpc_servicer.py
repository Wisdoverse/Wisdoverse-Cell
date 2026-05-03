"""
Tests for gRPC Servicer

Tests the gRPC servicer implementation.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.requirement_manager.grpc import requirement_pb2 as pb2
from agents.requirement_manager.grpc.servicer import (
    RequirementServicer,
    _requirement_to_proto,
)
from agents.requirement_manager.models.requirement import Requirement, RequirementStatus


@pytest.fixture
def mock_requirement():
    """Create a mock Requirement object."""
    req = MagicMock(spec=Requirement)
    req.id = "req_test123"
    req.title = "Test Requirement"
    req.description = "Test description"
    req.status = RequirementStatus.PENDING.value
    req.priority = "high"
    req.category = "功能"
    req.source_quote = "Original text"
    req.confirmed_by = None
    req.confirmed_at = None
    req.rejection_reason = None
    req.created_at = datetime.now(UTC)
    req.updated_at = datetime.now(UTC)
    return req


class TestRequirementToProto:
    """Tests for _requirement_to_proto helper."""

    def test_basic_conversion(self, mock_requirement):
        """Should convert requirement to proto message."""
        proto = _requirement_to_proto(mock_requirement)

        assert proto.id == "req_test123"
        assert proto.title == "Test Requirement"
        assert proto.description == "Test description"
        assert proto.status == "pending"
        assert proto.priority == "high"

    def test_handles_none_values(self, mock_requirement):
        """Should handle None values gracefully."""
        mock_requirement.description = None
        mock_requirement.source_quote = None
        mock_requirement.confirmed_by = None
        mock_requirement.confirmed_at = None

        proto = _requirement_to_proto(mock_requirement)

        assert proto.description == ""
        assert proto.source_quote == ""
        assert proto.confirmed_by == ""
        assert proto.confirmed_at == 0


class TestRequirementServicer:
    """Tests for RequirementServicer."""

    @pytest.fixture
    def servicer(self):
        """Create a servicer without agent."""
        return RequirementServicer(agent=None)

    @pytest.fixture
    def servicer_with_agent(self):
        """Create a servicer with mock agent."""
        mock_agent = AsyncMock()
        return RequirementServicer(agent=mock_agent)

    @pytest.fixture
    def mock_context(self):
        """Create a mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_health_check_without_agent(self, servicer, mock_context):
        """HealthCheck should work without agent."""
        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            request = pb2.HealthRequest()
            response = await servicer.HealthCheck(request, mock_context)

            assert response.version == "1.0.0"
            assert "db" in response.services
            assert response.services["agent"] is False

    @pytest.mark.asyncio
    async def test_health_check_with_agent(self, servicer_with_agent, mock_context):
        """HealthCheck should report agent available."""
        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            request = pb2.HealthRequest()
            response = await servicer_with_agent.HealthCheck(request, mock_context)

            assert response.services["agent"] is True

    @pytest.mark.asyncio
    async def test_list_requirements_empty(self, servicer, mock_context):
        """ListRequirements should return empty list when no requirements."""
        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            with patch("agents.requirement_manager.grpc.servicer.RequirementRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.list_all.return_value = []
                MockRepo.return_value = mock_repo

                request = pb2.ListRequest(page=1, page_size=20)
                response = await servicer.ListRequirements(request, mock_context)

                assert response.total == 0
                assert len(response.requirements) == 0

    @pytest.mark.asyncio
    async def test_list_requirements_with_data(self, servicer, mock_context, mock_requirement):
        """ListRequirements should return requirements."""
        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            with patch("agents.requirement_manager.grpc.servicer.RequirementRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.list_all.return_value = [mock_requirement]
                MockRepo.return_value = mock_repo

                request = pb2.ListRequest(page=1, page_size=20)
                response = await servicer.ListRequirements(request, mock_context)

                assert response.total == 1
                assert len(response.requirements) == 1
                assert response.requirements[0].id == "req_test123"

    @pytest.mark.asyncio
    async def test_get_requirement_found(self, servicer, mock_context, mock_requirement):
        """GetRequirement should return requirement when found."""
        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            with patch("agents.requirement_manager.grpc.servicer.RequirementRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.get_by_id.return_value = mock_requirement
                MockRepo.return_value = mock_repo

                request = pb2.GetRequest(id="req_test123")
                response = await servicer.GetRequirement(request, mock_context)

                assert response.id == "req_test123"
                assert response.title == "Test Requirement"

    @pytest.mark.asyncio
    async def test_get_requirement_not_found(self, servicer, mock_context):
        """GetRequirement should set NOT_FOUND when requirement doesn't exist."""
        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            with patch("agents.requirement_manager.grpc.servicer.RequirementRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.get_by_id.return_value = None
                MockRepo.return_value = mock_repo

                request = pb2.GetRequest(id="nonexistent")
                await servicer.GetRequirement(request, mock_context)

                mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_confirm_requirement_with_agent(self, servicer_with_agent, mock_context, mock_requirement):
        """ConfirmRequirement should use agent when available."""
        mock_requirement.status = RequirementStatus.CONFIRMED.value
        servicer_with_agent.agent.confirm_requirement.return_value = mock_requirement

        request = pb2.ConfirmRequest(id="req_test123", confirmed_by="user1")
        response = await servicer_with_agent.ConfirmRequirement(request, mock_context)

        assert response.success is True
        servicer_with_agent.agent.confirm_requirement.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_requirement_with_agent(self, servicer_with_agent, mock_context, mock_requirement):
        """RejectRequirement should use agent when available."""
        mock_requirement.status = RequirementStatus.REJECTED.value
        servicer_with_agent.agent.reject_requirement.return_value = mock_requirement

        request = pb2.RejectRequest(id="req_test123", reason="Not valid", rejected_by="user1")
        response = await servicer_with_agent.RejectRequirement(request, mock_context)

        assert response.success is True
        servicer_with_agent.agent.reject_requirement.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_requirements_without_agent(self, servicer, mock_context):
        """ExtractRequirements should fail without agent."""
        request = pb2.ExtractRequest(content="Meeting notes...", source="test")
        response = await servicer.ExtractRequirements(request, mock_context)

        assert response.success is False
        assert "not initialized" in response.error.lower()

    @pytest.mark.asyncio
    async def test_search_requirements(self, servicer, mock_context, mock_requirement):
        """SearchRequirements should search by keyword."""
        with patch("agents.requirement_manager.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            with patch("agents.requirement_manager.grpc.servicer.RequirementRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.search.return_value = [mock_requirement]
                MockRepo.return_value = mock_repo

                request = pb2.SearchRequest(keyword="test", page=1, page_size=20)
                response = await servicer.SearchRequirements(request, mock_context)

                assert response.total == 1
                mock_repo.search.assert_called_once_with("test")
