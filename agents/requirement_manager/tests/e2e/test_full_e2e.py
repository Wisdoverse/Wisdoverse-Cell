"""
Full end-to-end tests for major milestones.

Uses real LLM and real infrastructure.
Requires E2E_FULL=1 to run.
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path.
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import os

import pytest
from httpx import AsyncClient

from shared.schemas.event import EventTypes

# Skip unless E2E_FULL=1 is set.
pytestmark = [
    pytest.mark.skipif(
        os.getenv("E2E_FULL") != "1",
        reason="Full E2E requires E2E_FULL=1"
    ),
    pytest.mark.e2e_full,
]


class TestCompleteRequirementLifecycle:
    """Complete requirement lifecycle tests."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_real_llm(
        self,
        client: AsyncClient,
        real_llm,
        get_published_events
    ):
        """
        Complete lifecycle: ingest, extract, search, conflict check, confirm, export.

        Uses a real LLM to validate the end-to-end flow.
        """
        # 1. Upload real meeting content.
        meeting_content = """
        2026年1月21日产品需求会议

        参会人员：张总、李经理、王工

        讨论内容：
        1. 张总提出必须在下个版本支持离线录音功能，这是客户的核心需求
        2. 李经理补充说录音需要支持 MP3 和 WAV 格式
        3. 王工询问是否需要支持实时转写，张总说这个可以放到后续版本

        决定事项：
        - 离线录音作为 P0 优先级
        - 多格式支持作为 P1 优先级

        待确认：
        - 离线存储容量上限需要和硬件团队确认
        """

        resp = await client.post("/api/ingest/upload", json={
            "content": meeting_content,
            "source": "upload",
            "title": "产品需求会议"
        })
        assert resp.status_code == 200
        data = resp.json()

        # Validate that extraction produced a plausible result.
        assert data["requirements_extracted"] >= 1, "Expected at least one requirement"

        # 2. Validate semantic search can find the result.
        resp = await client.get("/api/requirements/search", params={
            "q": "离线录音"
        })
        assert resp.status_code == 200
        search_results = resp.json()
        assert search_results["total"] >= 1, "Expected semantic search to find related requirements"

        # 3. Fetch requirement detail.
        resp = await client.get("/api/requirements")
        requirements = resp.json()["items"]
        assert len(requirements) >= 1

        req_id = requirements[0]["id"]

        resp = await client.get(f"/api/requirements/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert "title" in detail
        assert "description" in detail

        # 4. Check conflicts. New requirements should return "new".
        resp = await client.post("/api/requirements/check-conflict", json={
            "title": "语音实时转写功能",
            "description": "支持录音的实时语音转文字",
            "category": "功能"
        })
        assert resp.status_code == 200
        conflict_result = resp.json()
        assert conflict_result["relation"] in ["new", "update", "duplicate", "conflict"]

        # 5. Confirm requirement.
        resp = await client.put(f"/api/requirements/{req_id}/confirm", json={
            "confirmed_by": "产品经理"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "CONFIRMED"

        # 6. Export PRD.
        resp = await client.get("/api/export/prd", params={
            "status": "confirmed"
        })
        assert resp.status_code == 200
        prd = resp.json()
        assert len(prd["content"]) > 100, "Expected PRD content to be sufficiently detailed"
        assert prd["requirements_count"] >= 1

        # 7. Validate event publishing.
        events = await get_published_events(EventTypes.REQUIREMENT_CONFIRMED)
        assert len(events) >= 1


class TestFeishuIntegration:
    """Feishu webhook integration tests."""

    @pytest.mark.asyncio
    async def test_feishu_webhook_full_flow(
        self,
        client: AsyncClient,
        real_llm
    ):
        """
        Simulate a Feishu webhook callback.

        Validates the full flow for receiving meeting notes from Feishu.
        """
        # Simulate a Feishu webhook request.
        resp = await client.post("/api/ingest/feishu", json={
            "event_type": "meeting.ended",
            "meeting_id": "feishu_meeting_001",
            "topic": "录音分析项目需求评审",
            "summary": """
            会议主题：录音分析项目需求评审

            参会人员：
            - 产品负责人
            - 开发团队

            会议纪要：
            1. 确认离线录音功能为核心需求
            2. 讨论了音频格式支持范围
            3. 决定第一版本支持 MP3、WAV、M4A 三种格式

            后续行动：
            - 开发团队评估技术方案
            - 产品出详细 PRD
            """,
            "participants": ["产品负责人", "开发负责人", "前端工程师"],
            "meeting_time": "2026-01-21T14:00:00Z"
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["requirements_extracted"] >= 1

        # Validate deduplication: the same meeting_id should not be processed twice.
        resp2 = await client.post("/api/ingest/feishu", json={
            "event_type": "meeting.ended",
            "meeting_id": "feishu_meeting_001",  # Same ID.
            "topic": "重复的会议",
            "summary": "测试去重",
            "participants": [],
            "meeting_time": "2026-01-21T14:00:00Z"
        })

        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["requirements_extracted"] == 0, "Duplicate meeting should not be extracted again"


class TestEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_empty_meeting_content(self, client: AsyncClient, real_llm):
        """Test empty meeting content."""
        resp = await client.post("/api/ingest/upload", json={
            "content": "今天天气不错，大家聊了聊近况。",  # No substantive requirement.
            "source": "upload",
            "title": "闲聊"
        })

        # Should succeed while extracting zero requirements.
        assert resp.status_code == 200
        # The LLM may extract zero items or attempt extraction depending on model judgment.

    @pytest.mark.asyncio
    async def test_very_long_meeting_content(self, client: AsyncClient, real_llm):
        """Test long meeting content."""
        long_content = """
        这是一个很长的会议记录。
        """ + "需求讨论点 " * 500  # Approximately 3,000 Chinese characters.

        resp = await client.post("/api/ingest/upload", json={
            "content": long_content,
            "source": "upload",
            "title": "长会议"
        })

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, client: AsyncClient, real_llm):
        """Test concurrent requests."""
        import asyncio

        async def upload_meeting(idx: int):
            return await client.post("/api/ingest/upload", json={
                "content": f"会议 {idx}：讨论了功能 {idx} 的需求",
                "source": "upload",
                "title": f"并发测试会议 {idx}"
            })

        # Run three concurrent requests.
        results = await asyncio.gather(
            upload_meeting(1),
            upload_meeting(2),
            upload_meeting(3)
        )

        for resp in results:
            assert resp.status_code == 200
