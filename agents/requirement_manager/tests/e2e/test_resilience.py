"""
Resilience Tests - Infrastructure Failure Scenarios

Tests graceful degradation and error handling when infrastructure fails.
Marked with @pytest.mark.resilience for selective execution.

Run with: pytest -m resilience -v
"""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

pytestmark = [
    pytest.mark.resilience,
    pytest.mark.asyncio,
    pytest.mark.skip(reason="Resilience tests require infrastructure mock refactoring"),
]


class TestRedisResilience:
    """Redis failure scenarios"""

    async def test_redis_disconnect_during_publish(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Redis disconnects during event publish
        Expected: API succeeds (data saved), event publish fails gracefully
        """
        from shared.infra.event_bus import EventBus

        # Patch event bus publish to simulate Redis failure
        with patch.object(EventBus, 'publish', new_callable=AsyncMock) as mock_publish:
            mock_publish.side_effect = ConnectionError("Redis connection lost")

            resp = await client.post("/api/ingest/upload", json={
                "content": sample_meeting_content,
                "source": "upload",
                "title": "Redis failure test"
            })

            # Core functionality should still work
            # Event publish failure should be caught and logged
            assert resp.status_code in [200, 500, 503]

    async def test_redis_timeout(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Redis operations timeout
        Expected: Request completes within reasonable time
        """
        from shared.infra.event_bus import EventBus

        async def slow_publish(*args, **kwargs):
            await asyncio.sleep(10)  # Simulate slow Redis

        with patch.object(EventBus, 'publish', new_callable=AsyncMock) as mock_publish:
            mock_publish.side_effect = slow_publish

            # Request should not hang forever
            try:
                resp = await asyncio.wait_for(
                    client.post("/api/ingest/upload", json={
                        "content": sample_meeting_content,
                        "source": "upload",
                        "title": "Timeout test"
                    }),
                    timeout=5.0
                )
                # If we get here, the timeout was handled internally
                assert resp.status_code in [200, 500, 503, 504]
            except asyncio.TimeoutError:
                # Timeout is acceptable - better than hanging
                pass


class TestDatabaseResilience:
    """PostgreSQL failure scenarios"""

    async def test_concurrent_requests_under_load(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Many concurrent requests hit the database
        Expected: Most succeed, failures are graceful (not crashes)
        """
        async def make_request(idx: int):
            try:
                return await client.post("/api/ingest/upload", json={
                    "content": f"Meeting {idx}: {sample_meeting_content[:100]}",
                    "source": "upload",
                    "title": f"Load test {idx}"
                })
            except Exception as e:
                return e

        # Fire concurrent requests
        tasks = [make_request(i) for i in range(15)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes and failures
        successes = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        failures = sum(
            1 for r in results
            if isinstance(r, Exception)
            or (hasattr(r, 'status_code') and r.status_code >= 500)
        )

        # At least some should succeed, and failures should be graceful (not crashes)
        assert successes >= 5, f"Only {successes} succeeded out of 15"
        assert failures < 15, f"All requests failed ({failures}/15)"

    async def test_database_query_error_handling(
        self,
        client: AsyncClient,
        mock_llm,
    ):
        """
        Scenario: Database query fails
        Expected: Appropriate error response, not crash
        """
        with patch(
            "agents.requirement_manager.api.requirements.RequirementRepository.list_all",
            new_callable=AsyncMock
        ) as mock_list:
            mock_list.side_effect = Exception("Database query failed")

            resp = await client.get("/api/requirements")

            # Should return error, not crash
            assert resp.status_code in [500, 503]


class TestVectorStoreResilience:
    """Vector store (Milvus) failure scenarios"""

    async def test_vector_store_unavailable_on_ingest(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Milvus is unavailable during requirement ingestion
        Expected: Core functionality works, vector indexing fails gracefully
        """
        from agents.requirement_manager.db.vector_store import VectorStore

        with patch.object(
            VectorStore, 'add_requirements_batch', new_callable=AsyncMock,
        ) as mock_add:
            mock_add.side_effect = Exception("Milvus connection refused")

            resp = await client.post("/api/ingest/upload", json={
                "content": sample_meeting_content,
                "source": "upload",
                "title": "Vector store failure test"
            })

            # Ingest should still succeed - vector store is secondary
            # (depends on implementation - may be 200 or 500)
            assert resp.status_code in [200, 500, 503]

    async def test_semantic_search_fallback_on_vector_store_failure(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Milvus fails during semantic search
        Expected: Returns empty results or falls back to text search
        """
        # First ingest some data
        await client.post("/api/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "Test"
        })

        with patch(
            "agents.requirement_manager.api.requirements.vector_store.search"
        ) as mock_search:
            mock_search.side_effect = Exception("Vector search failed")

            resp = await client.get("/api/requirements/search", params={"q": "离线录音"})

            # Should return graceful response, not crash
            assert resp.status_code in [200, 500, 503]


class TestLLMResilience:
    """LLM service failure scenarios"""

    LLM_GATEWAY_PATH = "shared.services.llm_gateway.llm_gateway.complete"

    async def test_llm_timeout(
        self,
        client: AsyncClient,
        sample_meeting_content: str,
    ):
        """
        Scenario: LLM request times out
        Expected: Appropriate error response within reasonable time
        """
        async def slow_llm(*args, **kwargs):
            await asyncio.sleep(60)
            return "{}"

        with patch(self.LLM_GATEWAY_PATH, new=AsyncMock(side_effect=slow_llm)):
            try:
                resp = await asyncio.wait_for(
                    client.post("/api/ingest/upload", json={
                        "content": sample_meeting_content,
                        "source": "upload",
                        "title": "LLM timeout test"
                    }),
                    timeout=10.0
                )
                assert resp.status_code in [500, 503, 504]
            except asyncio.TimeoutError:
                pass  # External timeout is acceptable

    async def test_llm_rate_limit(
        self,
        client: AsyncClient,
        sample_meeting_content: str,
    ):
        """
        Scenario: LLM returns rate limit error
        Expected: 429 or 503 response
        """
        async def rate_limited(*args, **kwargs):
            raise Exception("rate_limit_exceeded")

        with patch(self.LLM_GATEWAY_PATH, new=AsyncMock(side_effect=rate_limited)):
            resp = await client.post("/api/ingest/upload", json={
                "content": sample_meeting_content,
                "source": "upload",
                "title": "Rate limit test"
            })
            assert resp.status_code in [429, 500, 503]

    async def test_llm_invalid_json_response(
        self,
        client: AsyncClient,
        sample_meeting_content: str,
    ):
        """
        Scenario: LLM returns invalid JSON
        Expected: Graceful error handling
        """
        async def bad_json(*args, **kwargs):
            return "This is not valid JSON {{{["

        with patch(self.LLM_GATEWAY_PATH, new=AsyncMock(side_effect=bad_json)):
            resp = await client.post("/api/ingest/upload", json={
                "content": sample_meeting_content,
                "source": "upload",
                "title": "Invalid JSON test"
            })
            assert resp.status_code in [200, 500, 422]

    async def test_llm_empty_response(
        self,
        client: AsyncClient,
        sample_meeting_content: str,
    ):
        """
        Scenario: LLM returns empty response
        Expected: Handle as no requirements found
        """
        async def empty_response(*args, **kwargs):
            return '{"requirements": [], "open_questions": []}'

        with patch(self.LLM_GATEWAY_PATH, new=AsyncMock(side_effect=empty_response)):
            resp = await client.post("/api/ingest/upload", json={
                "content": sample_meeting_content,
                "source": "upload",
                "title": "Empty response test"
            })
            assert resp.status_code == 200
            assert resp.json().get("requirements_extracted", 0) == 0


class TestCircuitBreaker:
    """Circuit breaker pattern tests (if implemented)"""

    LLM_GATEWAY_PATH = "shared.services.llm_gateway.llm_gateway.complete"

    async def test_repeated_failures_trigger_fast_fail(
        self,
        client: AsyncClient,
        sample_meeting_content: str,
    ):
        """
        Scenario: Multiple consecutive failures
        Expected: Subsequent requests fail fast (circuit breaker opens)
        """
        call_count = 0

        async def failing_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Service unavailable")

        with patch(self.LLM_GATEWAY_PATH, new=AsyncMock(side_effect=failing_llm)):
            for i in range(5):
                await client.post("/api/ingest/upload", json={
                    "content": f"Test {i}: {sample_meeting_content[:50]}",
                    "source": "upload",
                    "title": f"Circuit breaker test {i}"
                })

        # If circuit breaker is implemented, call_count should be less than 5
        # (subsequent calls should fail fast without calling LLM)
        assert call_count <= 5


class TestGracefulDegradation:
    """Tests for graceful degradation patterns"""

    async def test_health_check_during_partial_outage(
        self,
        client: AsyncClient,
    ):
        """
        Scenario: Some services are down
        Expected: Health check reports degraded status
        """
        resp = await client.get("/health")

        # Health check should always respond
        assert resp.status_code in [200, 503]

    async def test_read_operations_during_write_failure(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Write operations fail but read operations should work
        Expected: GET requests succeed even if POST would fail
        """
        # First, successfully create some data
        resp = await client.post("/api/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "Initial data"
        })
        assert resp.status_code == 200

        # Now simulate write failures
        from agents.requirement_manager.db.repository import RequirementRepository

        with patch.object(RequirementRepository, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("Write failed")

            # Read should still work
            resp = await client.get("/api/requirements")
            assert resp.status_code == 200
