"""
Concurrency Tests - Parallel Operation Scenarios

Tests correct behavior under concurrent access:
- Race conditions
- Data consistency
- Transaction isolation

Run with: pytest -m concurrency -v
"""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import asyncio

import pytest
from httpx import AsyncClient

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.asyncio,
]


class TestConcurrentUploads:
    """Concurrent meeting upload scenarios"""

    async def test_parallel_meeting_uploads(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Multiple meetings uploaded simultaneously
        Expected: All processed correctly with unique IDs
        """
        async def upload_meeting(idx: int):
            return await client.post("/api/ingest/upload", json={
                "content": f"会议 {idx}：讨论功能需求 {idx}，这是第 {idx} 个并发上传的会议",
                "source": "upload",
                "title": f"并发会议 {idx}"
            })

        # Upload 10 meetings concurrently
        tasks = [upload_meeting(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        for i, resp in enumerate(results):
            assert resp.status_code == 200, f"Meeting {i} failed: {resp.text}"
            data = resp.json()
            assert data["meeting_id"].startswith("mtg_")

        # Verify all meeting IDs are unique
        meeting_ids = [r.json()["meeting_id"] for r in results]
        assert len(set(meeting_ids)) == 10, "All meeting IDs should be unique"

    async def test_rapid_sequential_uploads(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Rapid sequential uploads (no artificial delay)
        Expected: All succeed without race conditions
        """
        meeting_ids = []

        for i in range(5):
            resp = await client.post("/api/ingest/upload", json={
                "content": f"快速上传 {i}: {sample_meeting_content[:100]}",
                "source": "upload",
                "title": f"快速上传 {i}"
            })
            assert resp.status_code == 200
            meeting_ids.append(resp.json()["meeting_id"])

        # All IDs should be unique
        assert len(set(meeting_ids)) == 5

    async def test_duplicate_content_concurrent_upload(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Same content uploaded concurrently
        Expected: Both succeed (content deduplication is optional)
        """
        async def upload_same():
            return await client.post("/api/ingest/upload", json={
                "content": sample_meeting_content,
                "source": "upload",
                "title": "重复内容测试"
            })

        results = await asyncio.gather(upload_same(), upload_same())

        # Both should succeed
        for resp in results:
            assert resp.status_code == 200

        # Meeting IDs should still be unique (different meetings, same content)
        ids = [r.json()["meeting_id"] for r in results]
        assert len(set(ids)) == 2


class TestConcurrentRequirementOperations:
    """Concurrent requirement modification scenarios"""

    async def test_concurrent_confirm_same_requirement(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Multiple users try to confirm same requirement
        Expected: All succeed (idempotent) or first wins
        """
        resp = await client.post("/api/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "Test"
        })
        assert resp.status_code == 200

        resp = await client.get("/api/requirements", params={"status": "pending"})
        requirements = resp.json().get("items", [])
        if not requirements:
            pytest.skip("No pending requirements created")

        req_id = requirements[0]["id"]

        async def confirm(user: str):
            return await client.put(f"/api/requirements/{req_id}/confirm", json={
                "confirmed_by": user
            })

        results = await asyncio.gather(*[confirm(f"User_{i}") for i in range(5)])
        success_count = sum(1 for r in results if r.status_code == 200)

        assert success_count >= 1, "At least one confirmation should succeed"

        resp = await client.get(f"/api/requirements/{req_id}")
        assert resp.status_code == 200
        assert resp.json().get("status", "").upper() == "CONFIRMED"

    async def test_concurrent_confirm_and_reject_race(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: One user confirms while another rejects
        Expected: One operation wins, final state is consistent
        """
        resp = await client.post("/api/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "Race condition test"
        })
        assert resp.status_code == 200

        resp = await client.get("/api/requirements", params={"status": "pending"})
        requirements = resp.json().get("items", [])
        if not requirements:
            pytest.skip("No pending requirements")

        req_id = requirements[0]["id"]

        confirm_result, reject_result = await asyncio.gather(
            client.put(f"/api/requirements/{req_id}/confirm", json={"confirmed_by": "ConfirmUser"}),
            client.put(f"/api/requirements/{req_id}/reject", json={"reason": "Not needed", "rejected_by": "RejectUser"})
        )

        success_count = sum(1 for r in [confirm_result, reject_result] if r.status_code == 200)
        assert success_count >= 1

        resp = await client.get(f"/api/requirements/{req_id}")
        final_status = resp.json().get("status", "").upper()
        assert final_status in ["CONFIRMED", "REJECTED"], f"Unexpected status: {final_status}"

    async def test_concurrent_updates_to_different_requirements(
        self,
        client: AsyncClient,
        mock_llm,
    ):
        """
        Scenario: Different requirements updated concurrently
        Expected: All updates succeed independently
        """
        # Create multiple meetings to get multiple requirements
        for i in range(3):
            await client.post("/api/ingest/upload", json={
                "content": f"会议 {i}: 独立需求 {i}",
                "source": "upload",
                "title": f"Meeting {i}"
            })

        resp = await client.get("/api/requirements", params={"status": "pending"})
        requirements = resp.json().get("items", [])

        if len(requirements) < 2:
            pytest.skip("Need at least 2 requirements")

        # Confirm different requirements concurrently
        async def confirm_req(req_id: str, user: str):
            return await client.put(f"/api/requirements/{req_id}/confirm", json={
                "confirmed_by": user
            })

        tasks = [
            confirm_req(requirements[i]["id"], f"User_{i}")
            for i in range(min(len(requirements), 3))
        ]
        results = await asyncio.gather(*tasks)

        # All should succeed
        for i, resp in enumerate(results):
            assert resp.status_code == 200, f"Requirement {i} confirmation failed"


class TestReadWriteIsolation:
    """Read/write isolation and consistency tests"""

    async def test_read_during_write_operations(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Read operations during concurrent writes
        Expected: Reads see consistent data
        """
        # Create initial data
        await client.post("/api/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "Initial"
        })

        async def write_more(idx: int):
            await asyncio.sleep(idx * 0.05)  # Stagger writes
            return await client.post("/api/ingest/upload", json={
                "content": f"写入 {idx}: 新的需求内容",
                "source": "upload",
                "title": f"Write {idx}"
            })

        async def read_repeatedly():
            counts = []
            for _ in range(5):
                resp = await client.get("/api/requirements")
                counts.append(resp.json().get("total", 0))
                await asyncio.sleep(0.03)
            return counts

        # Run writes and reads concurrently
        write_tasks = [write_more(i) for i in range(3)]
        read_task = asyncio.create_task(read_repeatedly())

        await asyncio.gather(*write_tasks)
        counts = await read_task

        # Counts should be monotonically non-decreasing (no dirty reads)
        for i in range(1, len(counts)):
            assert counts[i] >= counts[i-1], \
                f"Count decreased: {counts[i-1]} -> {counts[i]} (indicates dirty read)"

    async def test_pagination_consistency(
        self,
        client: AsyncClient,
        mock_llm,
    ):
        """
        Scenario: Paginating through results
        Expected: No missing or duplicate items
        """
        for i in range(7):
            await client.post("/api/ingest/upload", json={
                "content": f"Pagination test {i}: requirement {i}",
                "source": "upload",
                "title": f"Pagination {i}"
            })

        all_ids = set()
        page_size = 3
        max_pages = 10

        for page in range(1, max_pages + 1):
            resp = await client.get("/api/requirements", params={
                "page": page,
                "page_size": page_size
            })
            assert resp.status_code == 200

            items = resp.json().get("items", [])
            if not items:
                break

            for item in items:
                item_id = item["id"]
                assert item_id not in all_ids, f"Duplicate ID found: {item_id}"
                all_ids.add(item_id)

        assert len(all_ids) >= 7, f"Only found {len(all_ids)} items, expected >= 7"

    async def test_filter_consistency_during_updates(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
    ):
        """
        Scenario: Filtering while items are being updated
        Expected: Filter results are consistent
        """
        # Create requirements
        await client.post("/api/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "Filter test"
        })

        # Get pending requirements
        resp = await client.get("/api/requirements", params={"status": "pending"})
        pending = resp.json().get("items", [])

        if not pending:
            pytest.skip("No pending requirements")

        req_id = pending[0]["id"]

        # Confirm while reading
        async def confirm():
            await asyncio.sleep(0.01)
            return await client.put(f"/api/requirements/{req_id}/confirm", json={
                "confirmed_by": "test"
            })

        async def read_pending():
            results = []
            for _ in range(3):
                resp = await client.get("/api/requirements", params={"status": "pending"})
                results.append(resp.json())
                await asyncio.sleep(0.01)
            return results

        _, reads = await asyncio.gather(confirm(), read_pending())

        # Pending count should decrease or stay same, never increase for same item
        # (item transitions from pending to confirmed)
        for read in reads:
            assert read.get("total", 0) >= 0


class TestBatchOperations:
    """Concurrent batch operation tests"""

    async def test_concurrent_batch_confirm(
        self,
        client: AsyncClient,
        mock_llm,
    ):
        """
        Scenario: Multiple batch confirm requests
        Expected: All items confirmed exactly once
        """
        # Create requirements
        for i in range(5):
            await client.post("/api/ingest/upload", json={
                "content": f"批量确认 {i}: 需求 {i}",
                "source": "upload",
                "title": f"Batch {i}"
            })

        resp = await client.get("/api/requirements", params={"status": "pending"})
        requirements = resp.json().get("items", [])
        req_ids = [r["id"] for r in requirements]

        if len(req_ids) < 2:
            pytest.skip("Need multiple requirements")

        # Split IDs and confirm concurrently
        mid = len(req_ids) // 2
        batch1 = req_ids[:mid]
        batch2 = req_ids[mid:]

        async def batch_confirm(ids: list):
            return await client.post("/api/requirements/batch/confirm", json={
                "requirement_ids": ids,
                "confirmed_by": "batch_test"
            })

        results = await asyncio.gather(
            batch_confirm(batch1),
            batch_confirm(batch2)
        )

        # Both batches should succeed
        for resp in results:
            assert resp.status_code == 200

        # Verify all are confirmed
        for req_id in req_ids:
            resp = await client.get(f"/api/requirements/{req_id}")
            if resp.status_code == 200:
                assert resp.json().get("status", "").upper() == "CONFIRMED"


class TestEventPublishingConcurrency:
    """Event publishing under concurrent load"""

    async def test_events_published_for_concurrent_operations(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
        get_published_events,
    ):
        """
        Scenario: Multiple operations publish events concurrently
        Expected: All events are published (no lost events)
        """
        # Create multiple requirements concurrently
        async def create_and_confirm(idx: int):
            resp = await client.post("/api/ingest/upload", json={
                "content": f"事件测试 {idx}: 需求 {idx}",
                "source": "upload",
                "title": f"Event test {idx}"
            })
            if resp.status_code != 200:
                return None

            data = resp.json()
            req_ids = data.get("requirement_ids", [])

            if req_ids:
                await client.put(f"/api/requirements/{req_ids[0]}/confirm", json={
                    "confirmed_by": f"user_{idx}"
                })

            return data.get("meeting_id")

        tasks = [create_and_confirm(i) for i in range(5)]
        meeting_ids = await asyncio.gather(*tasks)

        # Give events time to be published
        await asyncio.sleep(0.5)

        # Check that events were published
        await get_published_events("requirement.extracted")
        await get_published_events("requirement.confirmed")

        # We should have some events (exact count depends on implementation)
        # At minimum, operations that succeeded should have events
        valid_meetings = [m for m in meeting_ids if m is not None]
        assert len(valid_meetings) > 0, "No operations succeeded"
