"""
End-to-End gRPC Tests

Tests the Python gRPC server can handle requests.
"""
from unittest.mock import AsyncMock, patch

import pytest
from grpc import aio

# Import after patching to avoid loading real database
with patch("agents.capabilities.requirements.db.database.db_manager"):
    from agents.capabilities.requirements.grpc import requirement_pb2 as pb2
    from agents.capabilities.requirements.grpc import requirement_pb2_grpc as pb2_grpc
    from agents.capabilities.requirements.grpc.server import create_server


@pytest.fixture
async def grpc_server():
    """Start a test gRPC server."""
    # Create server with mock agent
    mock_agent = AsyncMock()

    with patch("agents.capabilities.requirements.grpc.servicer.db_manager") as mock_db:
        mock_session = AsyncMock()
        mock_db.session.return_value.__aenter__.return_value = mock_session

        server = await create_server(agent=mock_agent, port=50052)
        await server.start()

        yield server, mock_agent

        await server.stop(grace=0)


@pytest.fixture
async def grpc_channel():
    """Create a gRPC channel to the test server."""
    channel = aio.insecure_channel("localhost:50052")
    yield channel
    await channel.close()


class TestGRPCServer:
    """Test gRPC server functionality."""

    @pytest.mark.asyncio
    async def test_server_starts(self, grpc_server):
        """Server should start without errors."""
        server, _ = grpc_server
        assert server is not None

    @pytest.mark.asyncio
    async def test_health_check_via_grpc(self, grpc_server, grpc_channel):
        """Should be able to call HealthCheck via gRPC."""
        server, _ = grpc_server

        with patch("agents.capabilities.requirements.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            stub = pb2_grpc.RequirementServiceStub(grpc_channel)

            request = pb2.HealthRequest()
            response = await stub.HealthCheck(request)

            assert response.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_list_requirements_via_grpc(self, grpc_server, grpc_channel):
        """Should be able to list requirements via gRPC."""
        server, _ = grpc_server

        with patch("agents.capabilities.requirements.grpc.servicer.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            with patch("agents.capabilities.requirements.grpc.servicer.RequirementRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.list_all.return_value = []
                MockRepo.return_value = mock_repo

                stub = pb2_grpc.RequirementServiceStub(grpc_channel)

                request = pb2.ListRequest(page=1, page_size=20)
                response = await stub.ListRequirements(request)

                assert response.total == 0
                assert len(response.requirements) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
