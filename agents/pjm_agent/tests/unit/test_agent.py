"""
Unit Tests - PMAgent

Tests PMAgent initialization, event handling, and request handling.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.app import UNKNOWN_ACTION_ERROR_CODE
from shared.schemas.event import Event, EventTypes


class AsyncSessionContext:
    """Minimal async context manager for mocked db sessions."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


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
    # Inject mock core components.
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
        """agent_id is pjm-agent."""
        assert agent.agent_id == "pjm-agent"

    def test_subscribed_events(self, agent):
        """Agent subscribes to core event types."""
        assert EventTypes.SYNC_COMPLETED in agent.subscribed_events
        assert EventTypes.ANALYSIS_RISK_DETECTED in agent.subscribed_events
        assert EventTypes.CHAT_PM_QUERY in agent.subscribed_events
        assert len(agent.subscribed_events) >= 3

    def test_published_events(self, agent):
        """Agent publishes alert and chat response events."""
        assert EventTypes.PM_ALERT_TRIGGERED in agent.published_events
        assert EventTypes.CHAT_PM_RESPONSE in agent.published_events
        assert EventTypes.PM_DECOMPOSITION_FAILED in agent.published_events
        assert EventTypes.PM_APPROVAL_TIMEOUT in agent.published_events
        assert EventTypes.PM_TASKS_READY_FOR_DEV in agent.published_events
        assert EventTypes.SYNC_TASK_NEEDS_DECOMPOSE in agent.published_events
        assert len(agent.published_events) >= 2


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_uses_injected_health_store(
        self,
        mock_db_manager,
        mock_event_bus,
    ):
        from agents.pjm_agent.service.agent import PMAgent

        health_store = AsyncMock()
        health_store.is_database_ready = AsyncMock(return_value=True)
        agent = PMAgent(
            db=mock_db_manager,
            bus=mock_event_bus,
            health_store=health_store,
        )
        agent._config = MagicMock()
        agent._config.members = ["pm"]

        result = await agent.health_check()

        assert result == {"database": True, "config_loaded": True}
        health_store.is_database_ready.assert_awaited_once()


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_handle_event_sync_completed(self, agent):
        """sync.completed triggers alert checks."""
        agent._alert.check_all.return_value = [
            {"type": "deadline", "severity": "critical", "task": "T1", "message": "已逾期 2 天"},
        ]

        event = Event.create(
            event_type=EventTypes.SYNC_COMPLETED,
            source_agent="sync-module",
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
        """No PM_ALERT_TRIGGERED event is produced when there are no alerts."""
        agent._alert.check_all.return_value = []

        event = Event.create(
            event_type=EventTypes.SYNC_COMPLETED,
            source_agent="sync-module",
            payload={},
        )

        result_events = await agent.handle_event(event)

        agent._alert.check_all.assert_called_once()
        agent._push.push_alerts.assert_not_called()
        assert len(result_events) == 0

    @pytest.mark.asyncio
    async def test_handle_event_risk_detected(self, agent):
        """analysis.risk-detected records risk information."""
        event = Event.create(
            event_type=EventTypes.ANALYSIS_RISK_DETECTED,
            source_agent="analysis-module",
            payload={"risks": [{"type": "blocked", "message": "阻塞"}]},
            trace_id="trace-002",
        )

        result_events = await agent.handle_event(event)

        # _handle_risks only logs and produces no new events.
        assert result_events == []

    @pytest.mark.asyncio
    async def test_handle_event_chat_query(self, agent):
        """chat.pm-query returns a PM response event."""
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
    async def test_handle_event_chat_query_failure_uses_error_code(self, agent):
        """chat.pm-query failure responses include a stable error code."""
        agent._alert.check_all = AsyncMock(side_effect=RuntimeError("db down"))

        event = Event.create(
            event_type=EventTypes.CHAT_PM_QUERY,
            source_agent="chat-agent",
            payload={"user_id": "user-001", "query": "项目状态"},
            trace_id="trace-003",
        )

        result_events = await agent.handle_event(event)

        response = result_events[0].payload["response"]
        assert response == {
            "error": "Failed to retrieve PM status: RuntimeError",
            "error_code": "pm_chat_query_failed",
        }

    @pytest.mark.asyncio
    async def test_handle_event_unknown_type(self, agent):
        """Unknown event types return an empty list."""
        event = Event.create(
            event_type="unknown.event",
            source_agent="other-agent",
            payload={},
        )
        result = await agent.handle_event(event)
        assert result == []

    @pytest.mark.asyncio
    async def test_decompose_failure_publishes_failed_event_with_trace(self, agent):
        agent._decomposition_orchestrator = AsyncMock()
        agent._decomposition_orchestrator.handle_decompose = AsyncMock(
            side_effect=RuntimeError("decompose unavailable")
        )
        agent._decomposition_orchestrator.publish_event_via_outbox = AsyncMock()

        event = Event.create(
            event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
            source_agent="sync-module",
            payload={"title": "Login flow"},
            trace_id="trace-decompose",
        )

        result = await agent.handle_event(event)

        assert result == []
        published = agent._decomposition_orchestrator.publish_event_via_outbox.await_args.args[0]
        assert published.event_type == EventTypes.PM_DECOMPOSITION_FAILED
        assert published.metadata.trace_id == "trace-decompose"
        assert published.payload["requirement_title"] == "Login flow"
        agent._event_bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_approval_timeout_publishes_via_outbox(self, agent):
        """Approval timeout notification is staged through the PJM outbox."""
        agent._decomposition_orchestrator = AsyncMock()
        agent._decomposition_orchestrator.publish_event_via_outbox = AsyncMock()
        stale_record = MagicMock(
            id="dec_001",
            created_at=datetime.now(UTC) - timedelta(hours=25),
        )
        agent._decomposition_store = MagicMock()
        agent._decomposition_store.list_stale_pending = AsyncMock(return_value=[stale_record])

        await agent.check_approval_timeouts()

        published = agent._decomposition_orchestrator.publish_event_via_outbox.await_args.args[0]
        assert published.event_type == EventTypes.PM_APPROVAL_TIMEOUT
        assert published.source_agent == "pjm-agent"
        assert published.payload["record_id"] == "dec_001"
        agent._event_bus.publish.assert_not_awaited()


class TestHandleRequest:
    @pytest.mark.asyncio
    async def test_handle_request_config(self, agent):
        """action=config returns configuration information."""
        agent._config.members = [{"name": "Alice"}]
        agent._config.projects = [{"name": "P1"}]
        agent._config.rules = {"截止日期预警天数": "3"}

        result = await agent.handle_request({"action": "config"})

        assert result["members"] == [{"name": "Alice"}]
        assert result["projects"] == [{"name": "P1"}]
        assert result["rules"] == {"截止日期预警天数": "3"}

    @pytest.mark.asyncio
    async def test_handle_request_alerts(self, agent):
        """action=alerts returns the alert list."""
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
        """action=refresh_config refreshes configuration."""
        result = await agent.handle_request({"action": "refresh_config"})

        assert result["status"] == "refreshed"
        agent._config.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_unknown(self, agent):
        """Unknown action returns an error."""
        result = await agent.handle_request({"action": "nonexistent"})
        assert "error" in result
        assert result["error"] == "unknown action"
        assert result["error_code"] == UNKNOWN_ACTION_ERROR_CODE

    @pytest.mark.asyncio
    async def test_handle_request_no_action(self, agent):
        """Missing action returns an error."""
        result = await agent.handle_request({})
        assert "error" in result
        assert result["error_code"] == UNKNOWN_ACTION_ERROR_CODE

    @pytest.mark.asyncio
    async def test_handle_request_report_errors_are_sanitized(self, agent):
        """Report failures do not return raw exception details to API callers."""
        agent._report = AsyncMock()
        agent._report.generate_daily = AsyncMock(
            side_effect=RuntimeError("Traceback: database password leaked")
        )

        result = await agent.handle_request({"action": "daily_report"})

        assert result == {"error": "report_failed", "error_code": "report_failed"}
