"""
冒烟测试 - 验证核心业务路径

每次提交触发，<30秒完成。
使用 Mock LLM，真实数据库和 Redis。
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from httpx import AsyncClient

from shared.schemas.event import EventTypes

# 所有 smoke 测试统一超时 30 秒，防止单个测试卡死拖垮整个 pipeline
pytestmark = pytest.mark.timeout(30)


class TestHealthCheck:
    """健康检查"""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        """验证健康检查端点"""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_api_info_endpoint(self, client: AsyncClient):
        """验证 API 信息端点"""
        resp = await client.get("/api/v1")
        assert resp.status_code == 200
        data = resp.json()
        assert "endpoints" in data


class TestCoreWorkflow:
    """核心路径：上传会议 → 提取需求 → 确认需求"""

    @pytest.mark.asyncio
    async def test_ingest_extract_confirm_flow(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str,
        get_published_events
    ):
        """
        完整核心流程测试

        1. 上传会议内容
        2. 验证需求已提取
        3. 查询待确认需求
        4. 确认需求
        5. 验证事件已发布
        """
        # 1. 上传会议内容
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

        # 2. 查询提取的需求
        resp = await client.get("/api/v1/requirements", params={"status": "pending"})
        assert resp.status_code == 200
        requirements = resp.json()["items"]
        assert len(requirements) >= 1, (
            f"Expected >=1 pending requirements, got {len(requirements)}"
        )

        req_id = requirements[0]["id"]
        assert req_id.startswith("req_")

        # 3. 确认需求
        resp = await client.put(f"/api/v1/requirements/{req_id}/confirm", json={
            "confirmed_by": "测试用户"
        })
        assert resp.status_code == 200, (
            f"Confirm failed: {resp.status_code} {resp.text}"
        )
        confirmed = resp.json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["confirmed_by"] == "测试用户"

        # 4. 验证需求确认事件已发布
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
        拒绝流程测试

        1. 上传会议内容
        2. 拒绝需求
        3. 验证事件已发布
        """
        # 1. 上传
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "测试会议"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )

        # 2. 获取需求
        resp = await client.get("/api/v1/requirements", params={"status": "pending"})
        assert resp.status_code == 200
        requirements = resp.json()["items"]
        assert len(requirements) >= 1, (
            f"Expected >=1 pending requirements, got {len(requirements)}"
        )
        req_id = requirements[0]["id"]

        # 3. 拒绝需求
        resp = await client.put(f"/api/v1/requirements/{req_id}/reject", json={
            "reason": "不符合产品方向",
            "rejected_by": "产品经理"
        })
        assert resp.status_code == 200, (
            f"Reject failed: {resp.status_code} {resp.text}"
        )
        rejected = resp.json()
        assert rejected["status"] == "rejected"

        # 4. 验证拒绝事件
        events = await get_published_events(EventTypes.REQUIREMENT_REJECTED)
        assert len(events) >= 1, "Expected REQUIREMENT_REJECTED event"


class TestQueryFeatures:
    """查询功能测试"""

    @pytest.mark.asyncio
    async def test_requirements_list_pagination(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str
    ):
        """测试需求列表分页"""
        # 上传会议内容
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "测试会议"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )

        # 查询第一页
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
        """测试需求详情"""
        # 上传会议内容
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "测试会议"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )

        # 获取需求列表
        resp = await client.get("/api/v1/requirements")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1, (
            f"Expected >=1 requirements, got {len(items)}"
        )
        req_id = items[0]["id"]

        # 获取详情
        resp = await client.get(f"/api/v1/requirements/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == req_id
        assert "title" in detail
        assert "description" in detail


class TestExportFeatures:
    """导出功能测试"""

    @pytest.mark.asyncio
    async def test_export_prd(
        self,
        client: AsyncClient,
        mock_llm,
        sample_meeting_content: str
    ):
        """测试 PRD 导出"""
        # 上传并确认需求
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

        # 导出 PRD
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
        """测试问题清单导出"""
        # 上传会议内容（会生成待确认问题）
        resp = await client.post("/api/v1/ingest/upload", json={
            "content": sample_meeting_content,
            "source": "upload",
            "title": "测试会议"
        })
        assert resp.status_code == 200, (
            f"Upload failed: {resp.status_code} {resp.text}"
        )

        # 导出问题清单
        resp = await client.get("/api/v1/export/questions")
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
