"""
Integration tests for gRPC Server.

Tests the RequirementServicer with a mocked agent.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# Skip if proto not generated
try:
    from shared.grpc.generated import requirement_pb2
    from shared.grpc.server import RequirementServicer
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False


@pytest.fixture
def mock_agent():
    """Create a mock RequirementManagerAgent."""
    agent = MagicMock()
    agent._db_manager = MagicMock()

    # Mock session context manager
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    agent._db_manager.session.return_value = mock_session

    return agent


@pytest.fixture
def servicer(mock_agent):
    """Create a RequirementServicer with mocked agent."""
    if not PROTO_AVAILABLE:
        pytest.skip("Proto files not generated")
    return RequirementServicer(mock_agent)


@pytest.fixture
def mock_context():
    """Create a mock gRPC context."""
    context = MagicMock()
    return context


@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Proto files not generated")
class TestHealthCheck:
    """Tests for HealthCheck endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy(self, servicer, mock_context):
        """Test that health check returns healthy status."""
        request = requirement_pb2.HealthRequest()

        response = await servicer.HealthCheck(request, mock_context)

        assert response.healthy is True
        assert response.version == "1.0.0"
        assert response.services["db"] is True
        assert response.services["redis"] is True
        assert response.services["llm"] is True


@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Proto files not generated")
class TestListRequirements:
    """Tests for ListRequirements endpoint."""

    @pytest.mark.asyncio
    async def test_list_requirements_success(self, servicer, mock_agent, mock_context):
        """Test listing requirements successfully."""
        mock_agent.list_pending_requirements = AsyncMock(return_value=(
            [
                {"id": "req_001", "title": "Test 1", "description": "Desc 1", "status": "PENDING", "priority": "P0", "category": "feature"},
                {"id": "req_002", "title": "Test 2", "description": "Desc 2", "status": "PENDING", "priority": "P1", "category": "bug"},
            ],
            2,  # total
            1,  # total_pages
        ))

        request = requirement_pb2.ListRequest(status="PENDING", page=1, page_size=20)

        response = await servicer.ListRequirements(request, mock_context)

        assert len(response.requirements) == 2
        assert response.total == 2
        assert response.total_pages == 1
        assert response.requirements[0].id == "req_001"
        assert response.requirements[0].title == "Test 1"

    @pytest.mark.asyncio
    async def test_list_requirements_empty(self, servicer, mock_agent, mock_context):
        """Test listing requirements when none exist."""
        mock_agent.list_pending_requirements = AsyncMock(return_value=([], 0, 0))

        request = requirement_pb2.ListRequest(status="PENDING", page=1, page_size=20)

        response = await servicer.ListRequirements(request, mock_context)

        assert len(response.requirements) == 0
        assert response.total == 0

    @pytest.mark.asyncio
    async def test_list_requirements_pagination(self, servicer, mock_agent, mock_context):
        """Test pagination parameters are passed correctly."""
        mock_agent.list_pending_requirements = AsyncMock(return_value=([], 0, 0))

        request = requirement_pb2.ListRequest(status="CONFIRMED", page=3, page_size=5)

        await servicer.ListRequirements(request, mock_context)

        mock_agent.list_pending_requirements.assert_called_once_with(page=3, page_size=5)

    @pytest.mark.asyncio
    async def test_list_requirements_error(self, servicer, mock_agent, mock_context):
        """Test error handling in list requirements."""
        mock_agent.list_pending_requirements = AsyncMock(side_effect=Exception("DB error"))

        request = requirement_pb2.ListRequest(status="PENDING", page=1, page_size=20)

        response = await servicer.ListRequirements(request, mock_context)

        # Should return empty response and set error on context
        assert len(response.requirements) == 0
        mock_context.set_code.assert_called()


@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Proto files not generated")
class TestGetRequirement:
    """Tests for GetRequirement endpoint."""

    @pytest.mark.asyncio
    async def test_get_requirement_success(self, servicer, mock_agent, mock_context):
        """Test getting a requirement by ID."""
        mock_req = MagicMock()
        mock_req.id = "req_001"
        mock_req.title = "Test Requirement"
        mock_req.description = "Test Description"
        mock_req.status = "PENDING"
        mock_req.priority = "P0"
        mock_req.category = "feature"
        mock_req.source_quote = "User said..."
        mock_req.confirmed_by = None
        mock_req.confirmed_at = None
        mock_req.rejection_reason = None
        mock_req.created_at = datetime.now(UTC)
        mock_req.updated_at = datetime.now(UTC)

        mock_agent.get_requirement = AsyncMock(return_value=mock_req)

        request = requirement_pb2.GetRequest(id="req_001")

        response = await servicer.GetRequirement(request, mock_context)

        assert response.id == "req_001"
        assert response.title == "Test Requirement"

    @pytest.mark.asyncio
    async def test_get_requirement_not_found(self, servicer, mock_agent, mock_context):
        """Test getting a non-existent requirement."""
        mock_agent.get_requirement = AsyncMock(return_value=None)

        request = requirement_pb2.GetRequest(id="nonexistent")

        await servicer.GetRequirement(request, mock_context)

        mock_context.set_code.assert_called()


@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Proto files not generated")
class TestConfirmRequirement:
    """Tests for ConfirmRequirement endpoint."""

    @pytest.mark.asyncio
    async def test_confirm_requirement_success(self, servicer, mock_agent, mock_context):
        """Test confirming a requirement successfully."""
        mock_req = MagicMock()
        mock_req.id = "req_001"
        mock_req.title = "Confirmed Requirement"
        mock_req.description = "Description"
        mock_req.status = "CONFIRMED"
        mock_req.priority = "P0"
        mock_req.category = "feature"
        mock_req.source_quote = ""
        mock_req.confirmed_by = "user123"
        mock_req.confirmed_at = datetime.now(UTC)
        mock_req.rejection_reason = None
        mock_req.created_at = datetime.now(UTC)
        mock_req.updated_at = datetime.now(UTC)

        mock_agent.confirm_requirement = AsyncMock(return_value=mock_req)

        request = requirement_pb2.ConfirmRequest(id="req_001", confirmed_by="user123")

        response = await servicer.ConfirmRequirement(request, mock_context)

        assert response.success is True
        assert response.requirement.id == "req_001"
        assert response.requirement.status == "CONFIRMED"

    @pytest.mark.asyncio
    async def test_confirm_requirement_not_found(self, servicer, mock_agent, mock_context):
        """Test confirming a non-existent requirement."""
        mock_agent.confirm_requirement = AsyncMock(return_value=None)

        request = requirement_pb2.ConfirmRequest(id="nonexistent", confirmed_by="user123")

        response = await servicer.ConfirmRequirement(request, mock_context)

        assert response.success is False
        assert "not found" in response.error.lower()


@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Proto files not generated")
class TestRejectRequirement:
    """Tests for RejectRequirement endpoint."""

    @pytest.mark.asyncio
    async def test_reject_requirement_success(self, servicer, mock_agent, mock_context):
        """Test rejecting a requirement successfully."""
        mock_req = MagicMock()
        mock_req.id = "req_001"
        mock_req.title = "Rejected Requirement"
        mock_req.description = "Description"
        mock_req.status = "REJECTED"
        mock_req.priority = "P0"
        mock_req.category = "feature"
        mock_req.source_quote = ""
        mock_req.confirmed_by = None
        mock_req.confirmed_at = None
        mock_req.rejection_reason = "Not in scope"
        mock_req.created_at = datetime.now(UTC)
        mock_req.updated_at = datetime.now(UTC)

        mock_agent.reject_requirement = AsyncMock(return_value=mock_req)

        request = requirement_pb2.RejectRequest(
            id="req_001",
            reason="Not in scope",
            rejected_by="user123"
        )

        response = await servicer.RejectRequirement(request, mock_context)

        assert response.success is True
        assert response.requirement.id == "req_001"
        assert response.requirement.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_reject_requirement_not_found(self, servicer, mock_agent, mock_context):
        """Test rejecting a non-existent requirement."""
        mock_agent.reject_requirement = AsyncMock(return_value=None)

        request = requirement_pb2.RejectRequest(
            id="nonexistent",
            reason="Test",
            rejected_by="user123"
        )

        response = await servicer.RejectRequirement(request, mock_context)

        assert response.success is False
        assert "not found" in response.error.lower()


@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Proto files not generated")
class TestExtractRequirements:
    """Tests for ExtractRequirements endpoint."""

    @pytest.mark.asyncio
    async def test_extract_requirements_success(self, servicer, mock_agent, mock_context):
        """Test extracting requirements from content."""
        mock_result = MagicMock()
        mock_result.meeting_id = "meeting_001"
        mock_result.questions_generated = 3

        mock_agent.ingest_meeting = AsyncMock(return_value=mock_result)

        request = requirement_pb2.ExtractRequest(
            content="We need to add offline mode and improve performance.",
            source="chat",
            context="Product meeting",
            participants=["Alice", "Bob"]
        )

        response = await servicer.ExtractRequirements(request, mock_context)

        assert response.success is True
        assert response.meeting_id == "meeting_001"
        assert response.questions_count == 3

    @pytest.mark.asyncio
    async def test_extract_requirements_error(self, servicer, mock_agent, mock_context):
        """Test error handling in extract requirements."""
        mock_agent.ingest_meeting = AsyncMock(side_effect=Exception("LLM error"))

        request = requirement_pb2.ExtractRequest(
            content="Some content",
            source="chat"
        )

        response = await servicer.ExtractRequirements(request, mock_context)

        assert response.success is False
        assert "LLM error" in response.error


@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Proto files not generated")
class TestSearchRequirements:
    """Tests for SearchRequirements endpoint."""

    @pytest.mark.asyncio
    async def test_search_requirements_placeholder(self, servicer, mock_context):
        """Test search returns empty (placeholder implementation)."""
        request = requirement_pb2.SearchRequest(
            keyword="test",
            chat_id="chat_001",
            page=1,
            page_size=10
        )

        response = await servicer.SearchRequirements(request, mock_context)

        assert len(response.requirements) == 0
        assert response.total == 0
