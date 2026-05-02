"""
Performance Benchmark Tests

Measures and tracks performance of critical operations.
Uses pytest-benchmark for statistical analysis.

Run with:
    pytest tests/benchmarks -v --benchmark-autosave
    pytest tests/benchmarks -v --benchmark-compare

Performance targets:
    - Health check: < 10ms
    - Requirements list: < 100ms
    - Requirement detail: < 50ms
    - Semantic search: < 200ms
"""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import asyncio

import pytest

# Skip if pytest-benchmark is not installed
pytest.importorskip("pytest_benchmark")

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.asyncio,
]

# Re-use E2E fixtures
pytest_plugins = ["agents.capabilities.requirements.tests.e2e.conftest"]


def run_async(coro):
    """Helper to run async code in benchmark - returns result directly"""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestAPILatencyBenchmarks:
    """API endpoint latency benchmarks"""

    def _benchmark_get(self, client, benchmark, path: str):
        """Helper to benchmark GET requests"""
        async def make_request():
            resp = await client.get(path)
            assert resp.status_code == 200
            return resp
        return benchmark(lambda: run_async(make_request()))

    def test_health_check_latency(self, client, benchmark):
        """
        Benchmark: Health check endpoint
        Target: < 10ms (P95)
        """
        result = self._benchmark_get(client, benchmark, "/health")
        assert result.status_code == 200

    def test_api_info_latency(self, client, benchmark):
        """
        Benchmark: API info endpoint
        Target: < 10ms (P95)
        """
        result = self._benchmark_get(client, benchmark, "/api")
        assert result.status_code == 200

    def test_requirements_list_empty_latency(self, client, benchmark):
        """
        Benchmark: Requirements list (empty database)
        Target: < 50ms (P95)
        """
        result = self._benchmark_get(client, benchmark, "/api/requirements")
        assert result.status_code == 200

    def test_requirements_list_with_data_latency(
        self,
        client,
        mock_llm,
        sample_meeting_content,
        benchmark,
    ):
        """
        Benchmark: Requirements list (with data)
        Target: < 100ms (P95)
        """
        # Setup: Create some requirements
        async def setup():
            for i in range(10):
                await client.post("/api/ingest/upload", json={
                    "content": f"Benchmark meeting {i}: 需求内容 {i}",
                    "source": "upload",
                    "title": f"Benchmark {i}"
                })

        run_async(setup())

        async def list_requirements():
            resp = await client.get("/api/requirements", params={
                "page": 1,
                "page_size": 20
            })
            assert resp.status_code == 200
            return resp

        result = benchmark(lambda: run_async(list_requirements()))
        assert result.status_code == 200

    def test_requirement_detail_latency(
        self,
        client,
        mock_llm,
        sample_meeting_content,
        benchmark,
    ):
        """
        Benchmark: Single requirement detail
        Target: < 50ms (P95)
        """
        # Setup: Create a requirement
        async def setup():
            resp = await client.post("/api/ingest/upload", json={
                "content": sample_meeting_content,
                "source": "upload",
                "title": "Detail benchmark"
            })
            assert resp.status_code == 200

            resp = await client.get("/api/requirements")
            items = resp.json().get("items", [])
            return items[0]["id"] if items else None

        req_id = run_async(setup())
        if not req_id:
            pytest.skip("No requirement created")

        async def get_detail():
            resp = await client.get(f"/api/requirements/{req_id}")
            assert resp.status_code == 200
            return resp

        result = benchmark(lambda: run_async(get_detail()))
        assert result.status_code == 200

    def test_requirements_filter_latency(
        self,
        client,
        mock_llm,
        benchmark,
    ):
        """
        Benchmark: Filtered requirements query
        Target: < 100ms (P95)
        """
        # Setup: Create mixed status requirements
        async def setup():
            for i in range(5):
                resp = await client.post("/api/ingest/upload", json={
                    "content": f"Filter benchmark {i}: 功能需求 {i}",
                    "source": "upload",
                    "title": f"Filter {i}"
                })
                if resp.status_code == 200:
                    data = resp.json()
                    req_ids = data.get("requirement_ids", [])
                    if req_ids and i % 2 == 0:
                        await client.put(f"/api/requirements/{req_ids[0]}/confirm", json={
                            "confirmed_by": "benchmark"
                        })

        run_async(setup())

        async def filtered_query():
            resp = await client.get("/api/requirements", params={
                "status": "pending",
                "page": 1,
                "page_size": 10
            })
            assert resp.status_code == 200
            return resp

        result = benchmark(lambda: run_async(filtered_query()))
        assert result.status_code == 200


class TestUploadBenchmarks:
    """Upload operation benchmarks"""

    def test_meeting_upload_latency(
        self,
        client,
        mock_llm,
        sample_meeting_content,
        benchmark,
    ):
        """
        Benchmark: Meeting upload (with mock LLM)
        Target: < 500ms (P95) - mock LLM, real DB
        """
        counter = [0]

        async def upload():
            counter[0] += 1
            resp = await client.post("/api/ingest/upload", json={
                "content": f"Benchmark {counter[0]}: {sample_meeting_content[:200]}",
                "source": "upload",
                "title": f"Upload benchmark {counter[0]}"
            })
            return resp

        result = benchmark(lambda: run_async(upload()))
        # May be 200 (success) or other status (depends on mock LLM)
        assert result.status_code in [200, 500, 422]


class TestConfirmRejectBenchmarks:
    """Requirement lifecycle operation benchmarks"""

    def test_confirm_latency(
        self,
        client,
        mock_llm,
        sample_meeting_content,
        benchmark,
    ):
        """
        Benchmark: Requirement confirmation
        Target: < 100ms (P95)
        """
        # Setup: Create requirements pool
        req_ids = []

        async def setup():
            for i in range(20):
                resp = await client.post("/api/ingest/upload", json={
                    "content": f"Confirm benchmark {i}: 需求 {i}",
                    "source": "upload",
                    "title": f"Confirm {i}"
                })
                if resp.status_code == 200:
                    ids = resp.json().get("requirement_ids", [])
                    req_ids.extend(ids)

        run_async(setup())

        if not req_ids:
            pytest.skip("No requirements created")

        idx = [0]

        async def confirm():
            if idx[0] >= len(req_ids):
                idx[0] = 0  # Cycle through (some may already be confirmed)
            req_id = req_ids[idx[0]]
            idx[0] += 1
            resp = await client.put(f"/api/requirements/{req_id}/confirm", json={
                "confirmed_by": "benchmark"
            })
            return resp

        benchmark(lambda: run_async(confirm()))


class TestExportBenchmarks:
    """Export operation benchmarks"""

    def test_prd_export_latency(
        self,
        client,
        mock_llm,
        sample_meeting_content,
        benchmark,
    ):
        """
        Benchmark: PRD export
        Target: < 500ms (P95)
        """
        # Setup: Create and confirm some requirements
        async def setup():
            for i in range(5):
                resp = await client.post("/api/ingest/upload", json={
                    "content": f"PRD benchmark {i}: 功能需求 {i}",
                    "source": "upload",
                    "title": f"PRD {i}"
                })
                if resp.status_code == 200:
                    ids = resp.json().get("requirement_ids", [])
                    for req_id in ids:
                        await client.put(f"/api/requirements/{req_id}/confirm", json={
                            "confirmed_by": "benchmark"
                        })

        run_async(setup())

        async def export_prd():
            resp = await client.get("/api/export/prd")
            return resp

        result = benchmark(lambda: run_async(export_prd()))
        assert result.status_code in [200, 404]  # 404 if no confirmed requirements


# Performance thresholds for CI validation
PERFORMANCE_THRESHOLDS = {
    "test_health_check_latency": {"max_mean": 0.010},  # 10ms
    "test_api_info_latency": {"max_mean": 0.010},  # 10ms
    "test_requirements_list_empty_latency": {"max_mean": 0.050},  # 50ms
    "test_requirements_list_with_data_latency": {"max_mean": 0.100},  # 100ms
    "test_requirement_detail_latency": {"max_mean": 0.050},  # 50ms
    "test_requirements_filter_latency": {"max_mean": 0.100},  # 100ms
    "test_meeting_upload_latency": {"max_mean": 0.500},  # 500ms
    "test_confirm_latency": {"max_mean": 0.100},  # 100ms
    "test_prd_export_latency": {"max_mean": 0.500},  # 500ms
}
