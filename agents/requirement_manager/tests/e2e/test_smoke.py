"""
Smoke tests for core business paths.

Runs on each commit and finishes in under 30 seconds.
Uses a mock LLM with real database and Redis infrastructure.
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path.
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from httpx import AsyncClient

from shared.schemas.event import EventTypes

# Keep every smoke test under 30 seconds to avoid blocking the pipeline.
pytestmark = pytest.mark.timeout(30)


class TestHealthCheck:
    """Health check tests."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        """Validate the health endpoint."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_api_info_endpoint(self, client: AsyncClient):
        """Validate the API info endpoint."""
        resp = await client.get("/api/v1")
        assert resp.status_code == 200
        data = resp.json()
        assert "endpoints" in data


class TestCoreWorkflow:
    """Core path: upload meeting, extract requirements, confirm requirement."""

    @pytest.mark.asyncio
    async def test_ingest_extract_confirm_flow(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
        get_published_events
    ):
        """
        Full core flow test.

        1. Upload meeting content.
        2. Validate that requirements were extracted.
        3. Query pending requirements.
        4. Confirm a requirement.
        5. Validate that the event was published.
        """
        # 1. Upload meeting content.
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "需求讨论会"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )
        data = resp.json()
        assert data["requirements_extracted"] >= 1, (
            f"Expected >=1 requirements, got {data['requirements_extracted']}. "
            f"Response: {data}"
        )
        meeting_id = data["meeting_id"]
        assert meeting_id.startswith("mtg_")

        # 2. Query extracted requirements.
        resp = await client.get("/api/v1/requirements", params={"status": "pending"})
        assert resp.status_code == 200
        requirements = resp.json()["items"]
        assert len(requirements) >= 1, (
            f"Expected >=1 pending requirements, got {len(requirements)}"
        )

        req_id = requirements[0]["id"]
        assert req_id.startswith("req_")

        # 3. Confirm requirement.
        resp = await client.put(f"/api/v1/requirements/{req_id}/confirm", json={
            "confirmed_by": "测试用户"
        })
        assert resp.status_code == 200, (
            f"Confirm failed: {resp.status_code} {resp.text}"
        )
        confirmed = resp.json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["confirmed_by"] == "测试用户"

        # 4. Validate that the requirement confirmation event was published.
        events = await get_published_events(EventTypes.REQUIREMENT_CONFIRMED)
        assert len(events) >= 1, "Expected REQUIREMENT_CONFIRMED event"
        assert events[0].payload["requirement_id"] == req_id

    @pytest.mark.asyncio
    async def test_ingest_and_reject_flow(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
        get_published_events
    ):
        """
        Rejection flow test.

        1. Upload meeting content.
        2. Reject a requirement.
        3. Validate that the event was published.
        """
        # 1. Upload.
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "测试会议"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )

        # 2. Fetch requirements.
        resp = await client.get("/api/v1/requirements", params={"status": "pending"})
        assert resp.status_code == 200
        requirements = resp.json()["items"]
        assert len(requirements) >= 1, (
            f"Expected >=1 pending requirements, got {len(requirements)}"
        )
        req_id = requirements[0]["id"]

        # 3. Reject requirement.
        resp = await client.put(f"/api/v1/requirements/{req_id}/reject", json={
            "reason": "不符合产品方向",
            "rejected_by": "产品经理"
        })
        assert resp.status_code == 200, (
            f"Reject failed: {resp.status_code} {resp.text}"
        )
        rejected = resp.json()
        assert rejected["status"] == "rejected"

        # 4. Validate rejection event.
        events = await get_published_events(EventTypes.REQUIREMENT_REJECTED)
        assert len(events) >= 1, "Expected REQUIREMENT_REJECTED event"


class TestQueryFeatures:
    """Query feature tests."""

    @pytest.mark.asyncio
    async def test_requirements_list_pagination(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str
    ):
        """Test requirement list pagination."""
        # Upload meeting content.
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "测试会议"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )

        # Query the first page.
        resp = await client.get("/api/v1/requirements", params={
            "page": 1,
            "page_size": 2
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "items" in data
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_requirement_detail(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str
    ):
        """Test requirement detail."""
        # Upload meeting content.
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "测试会议"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )

        # Fetch requirement list.
        resp = await client.get("/api/v1/requirements")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1, (
            f"Expected >=1 requirements, got {len(items)}"
        )
        req_id = items[0]["id"]

        # Fetch detail.
        resp = await client.get(f"/api/v1/requirements/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == req_id
        assert "title" in detail
        assert "description" in detail


class TestExportFeatures:
    """Export feature tests."""

    @pytest.mark.asyncio
    async def test_export_prd(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str
    ):
        """Test PRD export."""
        # Upload and confirm a requirement.
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "测试会议"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )

        resp = await client.get("/api/v1/requirements")
        items = resp.json()["items"]
        assert len(items) >= 1
        req_id = items[0]["id"]

        resp = await client.put(f"/api/v1/requirements/{req_id}/confirm", json={
            "confirmed_by": "测试"
        })
        assert resp.status_code == 200

        # Export PRD.
        resp = await client.get("/api/v1/export/prd", params={
            "status": "confirmed"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert data["format"] == "markdown"

    @pytest.mark.asyncio
    async def test_export_questions(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str
    ):
        """Test open question list export."""
        # Upload meeting content that generates open questions.
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "测试会议"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )

        # Export open questions.
        resp = await client.get("/api/v1/export/questions")
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
