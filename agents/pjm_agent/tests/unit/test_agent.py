"""
Unit Tests - PMAgent

测试 PMAgent 的初始化、事件处理和请求处理逻辑。
"""

from unittest.mock import AsyncMock, MagicMock

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
    db.session = MagicMock()
    return db


@pytest.fixture
def agent(mock_db_manager, mock_event_bus):
    from agents.pjm_agent.service.agent import PMAgent

    a = PMAgent(db=mock_db_manager, bus=mock_event_bus)
    # 注入 mock 的 core 组件
    a._config = MagicMock()
    a._config.members = []
    a._config.projects = []
    a._config.rules = {}
    a._config.refresh = AsyncMock()
    a._config.get_rule = MagicMock(return_value="3")

    a._alert = AsyncMock()
    a._alert.check_all = AsyncMock(return_value=[])

    a._push = AsyncMock()
    a._push.push_alerts = AsyncMock(return_value=True)
    return a


class TestAgentInit:
    def test_agent_id(self, agent):
        """agent_id 应为 pjm-agent"""
        assert agent.agent_id == "pjm-agent"

    def test_subscribed_events(self, agent):
        """应订阅核心事件类型"""
        assert EventTypes.SYNC_COMPLETED in agent.subscribed_events
        assert EventTypes.ANALYSIS_RISK_DETECTED in agent.subscribed_events
        assert EventTypes.CHAT_PM_QUERY in agent.subscribed_events
        assert len(agent.subscribed_events) >= 3

    def test_published_events(self, agent):
        """应发布预警触发和聊天响应事件"""
        assert EventTypes.PM_ALERT_TRIGGERED in agent.published_events
        assert EventTypes.CHAT_PM_RESPONSE in agent.published_events
        assert len(agent.published_events) >= 2


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_handle_event_sync_completed(self, agent):
        """收到 sync.completed 事件后应执行预警检查"""
        agent._alert.check_all.return_value = [
            {"type": "deadline", "severity": "critical", "task": "T1", "message": "已逾期 2 天"},
        ]

        event = Event.create(
            event_type=EventTypes.SYNC_COMPLETED,
            source_agent="sync-agent",
            payload={"synced": 10},
            trace_id="trace-001",
        )

        result_events = await agent.handle_event(event)

        agent._alert.check_all.assert_called_once()
        agent._push.push_alerts.assert_called_once()
        event_types = [e.event_type for e in result_events]
        assert EventTypes.PM_ALERT_TRIGGERED in event_types

    @pytest.mark.asyncio
    async def test_handle_event_sync_completed_no_alerts(self, agent):
        """无预警时不应产生 PM_ALERT_TRIGGERED 事件"""
        agent._alert.check_all.return_value = []

        event = Event.create(
            event_type=EventTypes.SYNC_COMPLETED,
            source_agent="sync-agent",
            payload={},
        )

        result_events = await agent.handle_event(event)

        agent._alert.check_all.assert_called_once()
        agent._push.push_alerts.assert_not_called()
        assert len(result_events) == 0

    @pytest.mark.asyncio
    async def test_handle_event_risk_detected(self, agent):
        """收到 analysis.risk-detected 事件后应记录风险"""
        event = Event.create(
            event_type=EventTypes.ANALYSIS_RISK_DETECTED,
            source_agent="analysis-agent",
            payload={"risks": [{"type": "blocked", "message": "阻塞"}]},
            trace_id="trace-002",
        )

        result_events = await agent.handle_event(event)

        # _handle_risks 只做日志记录，不产生新事件
        assert result_events == []

    @pytest.mark.asyncio
    async def test_handle_event_chat_query(self, agent):
        """收到 chat.pm-query 事件后应返回 PM 响应事件"""
        agent._config.members = [{"name": "Alice"}]
        agent._config.projects = [{"name": "P1"}]
        agent._alert.check_all.return_value = [
            {"type": "deadline", "severity": "warning", "task": "T1", "message": "即将到期"},
        ]

        event = Event.create(
            event_type=EventTypes.CHAT_PM_QUERY,
            source_agent="chat-agent",
            payload={"user_id": "user-001", "query": "项目状态"},
            trace_id="trace-003",
        )

        result_events = await agent.handle_event(event)

        assert len(result_events) == 1
        assert result_events[0].event_type == EventTypes.CHAT_PM_RESPONSE
        assert result_events[0].payload["user_id"] == "user-001"
        assert "response" in result_events[0].payload

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


class TestHandleRequest:
    @pytest.mark.asyncio
    async def test_handle_request_config(self, agent):
        """action=config 应返回配置信息"""
        agent._config.members = [{"name": "Alice"}]
        agent._config.projects = [{"name": "P1"}]
        agent._config.rules = {"截止日期预警天数": "3"}

        result = await agent.handle_request({"action": "config"})

        assert result["members"] == [{"name": "Alice"}]
        assert result["projects"] == [{"name": "P1"}]
        assert result["rules"] == {"截止日期预警天数": "3"}

    @pytest.mark.asyncio
    async def test_handle_request_alerts(self, agent):
        """action=alerts 应返回预警列表"""
        agent._alert.check_all.return_value = [
            {"type": "deadline", "severity": "critical", "task": "T1", "message": "已逾期"},
            {"type": "blocked", "severity": "warning", "task": "T2", "message": "阻塞"},
        ]

        result = await agent.handle_request({"action": "alerts"})

        assert "alerts" in result
        assert len(result["alerts"]) == 2
        agent._alert.check_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_refresh(self, agent):
        """action=refresh_config 应刷新配置"""
        result = await agent.handle_request({"action": "refresh_config"})

        assert result["status"] == "refreshed"
        agent._config.refresh.assert_called_once()

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
