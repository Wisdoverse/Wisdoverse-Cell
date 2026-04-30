"""Tests for coordinator-related EventTypes constants."""
from shared.schemas.event import EventTypes


def test_coordinator_command_event_type():
    assert EventTypes.COORDINATOR_COMMAND == "coordinator.command"


def test_coordinator_response_event_type():
    assert EventTypes.COORDINATOR_RESPONSE == "coordinator.response"


def test_coordinator_dispatch_event_type():
    assert EventTypes.COORDINATOR_DISPATCH == "coordinator.dispatch"


def test_task_notification_event_type():
    assert EventTypes.TASK_NOTIFICATION == "task.notification"


def test_task_progress_event_type():
    assert EventTypes.TASK_PROGRESS == "task.progress"


def test_pm_prd_ready_event_type():
    assert EventTypes.PM_PRD_READY == "pm.prd-ready"
