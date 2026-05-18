"""Unit tests for QAAgent."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from agents.qa_agent.db.repository import AcceptanceRunRepository
from agents.qa_agent.service.agent import QAAgent
from shared.app import UNKNOWN_ACTION_ERROR_CODE


@pytest.fixture
def mock_db():
    db = MagicMock()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=empty_result)

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    db.session = MagicMock(return_value=SessionContext())
    return db


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_runner():
    runner = AsyncMock()
    runner.run_json = AsyncMock(
        return_value={
            "summary": {
                "l0_gate": "PASS",
                "l1_check": "PASS",
                "l2_report": "INFO",
                "total_checks": 10,
                "l0_failures": 0,
                "l1_warnings": 0,
            },
            "results": [],
            "duration_seconds": 5.0,
            "exit_code": 0,
        }
    )
    runner.run_markdown = AsyncMock(return_value="## Report\nAll passed.")
    return runner


@pytest.fixture
def mock_notifier():
    notifier = AsyncMock()
    notifier.notify_all = AsyncMock(
        return_value={
            "eventbus": {"sent": True},
            "feishu": {"sent": False, "reason": "below_threshold"},
            "gitlab": {"sent": False, "reason": "no_mr"},
        }
    )
    return notifier


@pytest.fixture
def agent(mock_db, mock_bus, mock_runner, mock_notifier):
    return QAAgent(
        db=mock_db,
        bus=mock_bus,
        runner=mock_runner,
        notifier=mock_notifier,
    )


def _existing_run():
    return SimpleNamespace(
        id="run_existing",
        agent_name="pjm_agent",
        l0_status="PASS",
        l1_status="PASS",
        l2_status="INFO",
        total_checks=3,
        l0_failure_count=0,
        l1_warning_count=0,
        duration_seconds=1.0,
        runner_exit_code=0,
        raw_report={"summary": {"total_checks": 3}, "results": []},
        report_markdown=None,
        notification_summary={"eventbus": {"sent": True}},
    )


class TestAgentInit:
    def test_agent_id(self, agent):
        assert agent.agent_id == "qa-agent"

    def test_subscribed_events(self, agent):
        assert "code.committed" in agent.subscribed_events
        assert "qa.run-requested" in agent.subscribed_events

    def test_published_events(self, agent):
        assert "qa.acceptance-completed" in agent.published_events
        assert "qa.gate-failed" in agent.published_events


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_uses_injected_health_store(
        self,
        mock_db,
        mock_bus,
        mock_runner,
        mock_notifier,
    ):
        health_store = AsyncMock()
        health_store.is_database_ready = AsyncMock(return_value=True)
        agent = QAAgent(
            db=mock_db,
            bus=mock_bus,
            runner=mock_runner,
            notifier=mock_notifier,
            health_store=health_store,
        )

        result = await agent.health_check()

        assert result == {"database": True}
        health_store.is_database_ready.assert_awaited_once()


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_code_committed_triggers_acceptance(self, agent, mock_runner):
        from shared.schemas.event import Event

        event = Event.create(
            event_type="code.committed",
            source_agent="ci",
            payload={
                "agent_name": "pjm_agent",
                "commit_sha": "abc1234567",
            },
        )
        result = await agent.handle_event(event)

        assert result == []  # side effects only
        mock_runner.run_json.assert_called_once()
        call_args = mock_runner.run_json.call_args
        assert call_args[0][0] == "pjm_agent"

    @pytest.mark.asyncio
    async def test_run_requested_triggers_acceptance(self, agent, mock_runner):
        from shared.schemas.event import Event

        event = Event.create(
            event_type="qa.run-requested",
            source_agent="pjm-agent",
            payload={
                "agent_name": "sync_module",
                "level": "l0",
                "requested_by": "pjm-agent",
            },
        )
        result = await agent.handle_event(event)

        assert result == []
        mock_runner.run_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_replayed_event_skips_runner_and_notifier(self, agent, mock_runner, mock_notifier):
        from shared.schemas.event import Event

        event = Event.create(
            event_type="qa.run-requested",
            source_agent="pjm-agent",
            payload={
                "agent_name": "pjm_agent",
                "level": "l0",
                "requested_by": "pjm-agent",
            },
        )

        mock_get = AsyncMock(return_value=_existing_run())
        with patch.object(
            AcceptanceRunRepository,
            "get_by_trigger_event_id",
            mock_get,
        ):
            result = await agent.handle_event(event)

        assert result == []
        mock_get.assert_awaited_once_with(event.event_id)
        mock_runner.run_json.assert_not_called()
        mock_notifier.notify_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_persist_skips_notification_after_runner(
        self,
        agent,
        mock_runner,
        mock_notifier,
    ):
        from shared.schemas.event import Event

        event = Event.create(
            event_type="qa.run-requested",
            source_agent="pjm-agent",
            payload={
                "agent_name": "pjm_agent",
                "level": "l0",
                "requested_by": "pjm-agent",
            },
        )
        duplicate_error = IntegrityError(
            "insert qa_acceptance_runs",
            {},
            Exception("duplicate trigger_event_id"),
        )

        mock_get = AsyncMock(side_effect=[None, _existing_run()])
        with (
            patch.object(
                AcceptanceRunRepository,
                "get_by_trigger_event_id",
                mock_get,
            ),
            patch(
                "agents.qa_agent.service.agent.QAReportStore.save_execution_result",
                new=AsyncMock(side_effect=duplicate_error),
            ),
        ):
            result = await agent.handle_event(event)

        assert result == []
        assert mock_get.await_count == 2
        mock_runner.run_json.assert_called_once()
        mock_notifier.notify_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_event_returns_empty(self, agent):
        from shared.schemas.event import Event

        event = Event.create(
            event_type="unknown.event",
            source_agent="test",
            payload={},
        )
        result = await agent.handle_event(event)
        assert result == []


class TestHandleRequest:
    @pytest.mark.asyncio
    async def test_standard_describe_action(self, agent):
        result = await agent.handle_request({"action": "describe"})

        assert result["agent_id"] == "qa-agent"
        assert result["agent_name"] == "QA Agent"
        assert "qa.run-requested" in result["subscribed_events"]

    @pytest.mark.asyncio
    async def test_run_action(self, agent, mock_runner):
        result = await agent.handle_request(
            {
                "action": "run",
                "agent_name": "pjm_agent",
                "level": "l0",
            }
        )
        assert "summary" in result
        mock_runner.run_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_stats_action(self, agent):
        with patch.object(agent, "get_stats", new_callable=AsyncMock) as mock_stats:
            from agents.qa_agent.models.schemas import QARunStats

            mock_stats.return_value = QARunStats(
                days=30,
                total_runs=10,
                pass_runs=8,
                warn_runs=1,
                failed_runs=1,
                l0_fail_rate=0.1,
                avg_duration_seconds=5.0,
            )
            result = await agent.handle_request(
                {
                    "action": "stats",
                    "days": 30,
                }
            )
        assert result["total_runs"] == 10

    @pytest.mark.asyncio
    async def test_get_run_not_found_uses_error_code(self, agent):
        with patch.object(agent, "get_run", new_callable=AsyncMock) as mock_get_run:
            mock_get_run.return_value = None
            result = await agent.handle_request({"action": "get_run", "run_id": "qa_404"})

        assert result == {"error": "not found", "error_code": "qa_run_not_found"}

    @pytest.mark.asyncio
    async def test_unknown_action(self, agent):
        result = await agent.handle_request({"action": "invalid"})
        assert "error" in result
        assert result["error_code"] == UNKNOWN_ACTION_ERROR_CODE


class TestDerriveSeverity:
    def test_l0_fail_is_critical(self):
        assert QAAgent._derive_severity({"level": "L0", "status": "FAIL"}) == "critical"

    def test_l1_warn_is_medium(self):
        assert QAAgent._derive_severity({"level": "L1", "status": "WARN"}) == "medium"

    def test_l2_is_info(self):
        assert QAAgent._derive_severity({"level": "L2", "status": "INFO"}) == "info"

    def test_default_is_low(self):
        assert QAAgent._derive_severity({"level": "L0", "status": "PASS"}) == "low"
