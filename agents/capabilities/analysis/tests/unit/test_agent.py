"""
Unit Tests - AnalysisAgent

测试 AnalysisAgent 的初始化、事件处理和请求处理逻辑。
"""
from unittest.mock import AsyncMock

import pytest

from shared.schemas.event import Event, EventTypes


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.connect = AsyncMock()
    bus.disconnect = AsyncMock()
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus


@pytest.fixture
def mock_db_manager():
    db = AsyncMock()
    db.create_tables = AsyncMock()
    db.close = AsyncMock()
    return db


@pytest.fixture
def agent(mock_db_manager, mock_event_bus):
    from agents.capabilities.analysis.service.agent import AnalysisAgent

    a = AnalysisAgent(db=mock_db_manager, bus=mock_event_bus)
    # 注入 mock 的 core 组件
    a._daily = AsyncMock()
    a._weekly = AsyncMock()
    a._milestone = AsyncMock()
    a._quality = AsyncMock()
    return a


class TestAgentInit:
    def test_agent_id(self, agent):
        """agent_id 应为 analysis-agent"""
        assert agent.agent_id == "analysis-agent"

    def test_subscribed_events(self, agent):
        """应订阅 sync.completed 事件"""
        assert EventTypes.SYNC_COMPLETED in agent.subscribed_events

    def test_published_events(self, agent):
        """应发布日报/周报/风险/质量事件"""
        assert EventTypes.REPORT_DAILY_GENERATED in agent.published_events
        assert EventTypes.REPORT_WEEKLY_GENERATED in agent.published_events
        assert EventTypes.ANALYSIS_RISK_DETECTED in agent.published_events
        assert EventTypes.ANALYSIS_QUALITY_EVALUATED in agent.published_events


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_handle_event_sync_completed(self, agent):
        """收到 sync.completed 事件后应生成日报、检查里程碑、评估质量，并返回事件"""
        agent._daily.generate.return_value = {"content": "日报", "summary": "摘要"}
        agent._daily.push_to_chat.return_value = True
        agent._milestone.check.return_value = [
            {"type": "blocked_subtasks", "severity": "warning", "message": "test"}
        ]
        agent._milestone.push_risks.return_value = True
        agent._quality.evaluate_all.return_value = [{"task": "T1", "quality": "合格"}]

        event = Event.create(
            event_type=EventTypes.SYNC_COMPLETED,
            source_agent="sync-agent",
            payload={"synced": 10},
            trace_id="trace-001",
        )

        result_events = await agent.handle_event(event)

        # 应产生日报、风险、质量三个事件（非周五不产生周报）
        event_types = [e.event_type for e in result_events]
        assert EventTypes.REPORT_DAILY_GENERATED in event_types
        assert EventTypes.ANALYSIS_RISK_DETECTED in event_types
        assert EventTypes.ANALYSIS_QUALITY_EVALUATED in event_types

        agent._daily.generate.assert_called_once()
        agent._daily.push_to_chat.assert_called_once_with("日报")
        agent._milestone.check.assert_called_once()
        agent._quality.evaluate_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_event_no_risks(self, agent):
        """无风险时不应产生 ANALYSIS_RISK_DETECTED 事件"""
        agent._daily.generate.return_value = {"content": "日报", "summary": "摘要"}
        agent._daily.push_to_chat.return_value = True
        agent._milestone.check.return_value = []
        agent._quality.evaluate_all.return_value = []

        event = Event.create(
            event_type=EventTypes.SYNC_COMPLETED,
            source_agent="sync-agent",
            payload={},
        )

        result_events = await agent.handle_event(event)
        event_types = [e.event_type for e in result_events]
        assert EventTypes.ANALYSIS_RISK_DETECTED not in event_types
        assert EventTypes.ANALYSIS_QUALITY_EVALUATED not in event_types

    @pytest.mark.asyncio
    async def test_handle_event_unknown_type(self, agent):
        """未知事件类型应返回空列表"""
        event = Event.create(
            event_type="unknown.event",
            source_agent="other-agent",
            payload={},
        )
        result = await agent.handle_event(event)
        assert result == []

    @pytest.mark.asyncio
    async def test_handle_event_daily_error_continues(self, agent):
        """日报生成失败不应阻止后续里程碑检查和质量评估"""
        agent._daily.generate.side_effect = Exception("bitable error")
        agent._milestone.check.return_value = [
            {"type": "low_progress", "severity": "warning", "message": "进度低"}
        ]
        agent._milestone.push_risks.return_value = True
        agent._quality.evaluate_all.return_value = []

        event = Event.create(
            event_type=EventTypes.SYNC_COMPLETED,
            source_agent="sync-agent",
            payload={},
        )

        result_events = await agent.handle_event(event)
        event_types = [e.event_type for e in result_events]
        # 日报失败，但里程碑风险事件仍应产生
        assert EventTypes.REPORT_DAILY_GENERATED not in event_types
        assert EventTypes.ANALYSIS_RISK_DETECTED in event_types


class TestHandleRequest:
    @pytest.mark.asyncio
    async def test_handle_request_daily(self, agent):
        """action=daily_report 应调用日报生成"""
        agent._daily.generate.return_value = {
            "content": "日报内容",
            "summary": "共 3 个任务",
            "stats": {"total": 3},
        }

        result = await agent.handle_request({"action": "daily_report"})

        assert result["content"] == "日报内容"
        assert result["summary"] == "共 3 个任务"
        agent._daily.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_weekly(self, agent):
        """action=weekly_report 应调用周报生成"""
        agent._weekly.generate.return_value = {
            "content": "周报内容",
            "summary": "本周完成 5 个任务",
        }

        result = await agent.handle_request({"action": "weekly_report"})

        assert result["content"] == "周报内容"
        agent._weekly.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_check_milestones(self, agent):
        """action=check_milestones 应返回风险列表"""
        agent._milestone.check.return_value = [
            {"type": "blocked_subtasks", "severity": "critical", "message": "阻塞"}
        ]

        result = await agent.handle_request({"action": "check_milestones"})

        assert len(result["risks"]) == 1
        assert result["risks"][0]["severity"] == "critical"
        agent._milestone.check.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_unknown(self, agent):
        """未知 action 应返回 error"""
        result = await agent.handle_request({"action": "nonexistent"})
        assert "error" in result
        assert result["error"] == "unknown action"

    @pytest.mark.asyncio
    async def test_handle_request_no_action(self, agent):
        """无 action 字段应返回 error"""
        result = await agent.handle_request({})
        assert "error" in result
