from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.capabilities.sync.core.scope_execution_use_cases import (
    SyncScopeExecutionUseCase,
)
from shared.schemas.event import Event, EventTypes


class _EventFactory:
    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent="sync-module",
            payload=payload,
            trace_id=trace_id,
        )


def _use_case(*, publisher=None, metrics=None) -> SyncScopeExecutionUseCase:
    publisher = publisher or AsyncMock()
    publisher.publish_sync_event_via_outbox = AsyncMock()
    metrics = metrics or MagicMock()
    return SyncScopeExecutionUseCase(
        event_factory=_EventFactory(),
        event_publisher=publisher,
        metrics=metrics,
    )


@pytest.mark.asyncio
async def test_run_scope_publishes_start_and_completed_events() -> None:
    publisher = AsyncMock()
    publisher.publish_sync_event_via_outbox = AsyncMock()
    metrics = MagicMock()
    use_case = _use_case(publisher=publisher, metrics=metrics)

    result = await use_case.run_scope(
        scope="openproject",
        triggered_by="operator",
        trace_id="trace-sync",
        runner=AsyncMock(
            return_value={
                "status": "success",
                "processed": 3,
                "errors": ["late field"],
            }
        ),
    )

    assert result["status"] == "success"
    events = [call.args[0] for call in publisher.publish_sync_event_via_outbox.await_args_list]
    assert [event.event_type for event in events] == [
        EventTypes.SYNC_STARTED,
        EventTypes.SYNC_COMPLETED,
    ]
    assert events[0].payload == {"triggered_by": "operator", "scope": "openproject"}
    assert events[1].payload == {
        "synced_count": 3,
        "scope": "openproject",
        "errors": ["late field"],
    }
    assert events[1].metadata.trace_id == "trace-sync"
    metrics.record_sync_success.assert_called_once()
    metrics.record_sync_failure.assert_not_called()


@pytest.mark.asyncio
async def test_run_scope_combines_split_sync_error_lists() -> None:
    publisher = AsyncMock()
    publisher.publish_sync_event_via_outbox = AsyncMock()
    use_case = _use_case(publisher=publisher)

    await use_case.run_scope(
        scope="full",
        triggered_by="scheduler",
        trace_id=None,
        runner=AsyncMock(
            return_value={
                "status": "partial",
                "total_processed": 5,
                "op_to_feishu": {"errors": ["op"]},
                "feishu_to_op": {"errors": ["bitable"]},
                "errors": ["generic"],
            }
        ),
    )

    complete_event = publisher.publish_sync_event_via_outbox.await_args_list[1].args[0]
    assert complete_event.payload["synced_count"] == 5
    assert complete_event.payload["errors"] == ["op", "bitable", "generic"]


@pytest.mark.asyncio
async def test_run_scope_publishes_failed_event_when_runner_raises() -> None:
    publisher = AsyncMock()
    publisher.publish_sync_event_via_outbox = AsyncMock()
    metrics = MagicMock()
    use_case = _use_case(publisher=publisher, metrics=metrics)

    result = await use_case.run_scope(
        scope="feishu_bitable",
        triggered_by="scheduler",
        trace_id="trace-sync",
        runner=AsyncMock(side_effect=RuntimeError("sync exploded")),
    )

    assert result == {"status": "failed", "error": "sync exploded"}
    events = [call.args[0] for call in publisher.publish_sync_event_via_outbox.await_args_list]
    assert [event.event_type for event in events] == [
        EventTypes.SYNC_STARTED,
        EventTypes.SYNC_FAILED,
    ]
    assert events[1].payload == {
        "error": "sync exploded",
        "error_code": "sync_scope_failed",
        "scope": "feishu_bitable",
    }
    metrics.record_sync_failure.assert_called_once_with(triggered_by="scheduler")


@pytest.mark.asyncio
async def test_lifecycle_publish_failure_does_not_block_runner() -> None:
    publisher = AsyncMock()
    publisher.publish_sync_event_via_outbox = AsyncMock(
        side_effect=[RuntimeError("bus down"), None]
    )
    use_case = _use_case(publisher=publisher)
    runner = AsyncMock(return_value={"status": "success", "processed": 1})

    result = await use_case.run_scope(
        scope="openproject",
        triggered_by="operator",
        trace_id="trace-sync",
        runner=runner,
    )

    assert result["status"] == "success"
    runner.assert_awaited_once()
    assert publisher.publish_sync_event_via_outbox.await_count == 2
