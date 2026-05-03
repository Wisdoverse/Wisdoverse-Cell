"""
完整端到端测试 - 大里程碑时执行

真实 LLM + 真实基础设施
需要设置 E2E_FULL=1 才会执行
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import os

import pytest
from httpx import AsyncClient

from shared.schemas.event import EventTypes

# 跳过条件：未设置 E2E_FULL=1
pytestmark = [
    pytest.mark.skipif(
        os.getenv("E2E_FULL") != "1",
        reason="Full E2E 需要设置 E2E_FULL=1"
    ),
    pytest.mark.e2e_full,
]


class TestCompleteRequirementLifecycle:
    """完整需求生命周期测试"""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_real_llm(
        self,
        client: AsyncClient,
        real_llm,
        get_published_events
    ):
        """
        完整生命周期：导入 → 提取 → 搜索 → 冲突检测 → 确认 → 导出

        使用真实 LLM，验证端到端流程。
        """
        # 1. 上传真实会议内容
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

        # 验证提取结果合理
        assert data["requirements_extracted"] >= 1, "应该至少提取出1个需求"

        # 2. 验证语义搜索能找到
        resp = await client.get("/api/requirements/search", params={
            "q": "离线录音"
        })
        assert resp.status_code == 200
        search_results = resp.json()
        assert search_results["total"] >= 1, "语义搜索应该能找到相关需求"

        # 3. 获取需求详情
        resp = await client.get("/api/requirements")
        requirements = resp.json()["items"]
        assert len(requirements) >= 1

        req_id = requirements[0]["id"]

        resp = await client.get(f"/api/requirements/{req_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert "title" in detail
        assert "description" in detail

        # 4. 检测冲突（对于新需求应该返回 "new"）
        resp = await client.post("/api/requirements/check-conflict", json={
            "title": "语音实时转写功能",
            "description": "支持录音的实时语音转文字",
            "category": "功能"
        })
        assert resp.status_code == 200
        conflict_result = resp.json()
        assert conflict_result["relation"] in ["new", "update", "duplicate", "conflict"]

        # 5. 确认需求
        resp = await client.put(f"/api/requirements/{req_id}/confirm", json={
            "confirmed_by": "产品经理"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "CONFIRMED"

        # 6. 导出 PRD
        resp = await client.get("/api/export/prd", params={
            "status": "confirmed"
        })
        assert resp.status_code == 200
        prd = resp.json()
        assert len(prd["content"]) > 100, "PRD 内容应该足够丰富"
        assert prd["requirements_count"] >= 1

        # 7. 验证事件发布
        events = await get_published_events(EventTypes.REQUIREMENT_CONFIRMED)
        assert len(events) >= 1


class TestFeishuIntegration:
    """飞书 Webhook 集成测试"""

    @pytest.mark.asyncio
    async def test_feishu_webhook_full_flow(
        self,
        client: AsyncClient,
        real_llm
    ):
        """
        模拟飞书 Webhook 回调

        验证从飞书接收会议纪要的完整流程。
        """
        # 模拟飞书 Webhook 请求
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

        # 验证去重：同一 meeting_id 不应重复处理
        resp2 = await client.post("/api/ingest/feishu", json={
            "event_type": "meeting.ended",
            "meeting_id": "feishu_meeting_001",  # 相同 ID
            "topic": "重复的会议",
            "summary": "测试去重",
            "participants": [],
            "meeting_time": "2026-01-21T14:00:00Z"
        })

        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["requirements_extracted"] == 0, "重复会议不应再次提取需求"


class TestEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_empty_meeting_content(self, client: AsyncClient, real_llm):
        """测试空会议内容"""
        resp = await client.post("/api/ingest/upload", json={
            "content": "今天天气不错，大家聊了聊近况。",  # 无实质需求
            "source": "upload",
            "title": "闲聊"
        })

        # 应该成功，但提取0个需求
        assert resp.status_code == 200
        # LLM 可能提取0个或尝试提取，取决于模型判断

    @pytest.mark.asyncio
    async def test_very_long_meeting_content(self, client: AsyncClient, real_llm):
        """测试长会议内容"""
        long_content = """
        这是一个很长的会议记录。
        """ + "需求讨论点 " * 500  # 约 3000 字

        resp = await client.post("/api/ingest/upload", json={
            "content": long_content,
            "source": "upload",
            "title": "长会议"
        })

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, client: AsyncClient, real_llm):
        """测试并发请求"""
        import asyncio

        async def upload_meeting(idx: int):
            return await client.post("/api/ingest/upload", json={
                "content": f"会议 {idx}：讨论了功能 {idx} 的需求",
                "source": "upload",
                "title": f"并发测试会议 {idx}"
            })

        # 并发 3 个请求
        results = await asyncio.gather(
            upload_meeting(1),
            upload_meeting(2),
            upload_meeting(3)
        )

        for resp in results:
            assert resp.status_code == 200
