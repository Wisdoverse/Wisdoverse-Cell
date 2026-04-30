"""
Tests for ApprovalGateway — Feishu card-based human approval for collaboration patterns.

Covers:
1. Skips if < 20 shadow runs → returns False
2. Sends approval card when >= 20 runs → returns True
3. Report contains pattern name, run count, success rate — NO raw prompts
4. Rejects unauthorized user_id → returns False
5. Approves: sets status=active, approved_by
6. Rejects: sets status=retired
7. Feishu send failure → returns False (logged)
8. No feishu service configured → still returns True (report generated)
9. Pattern not found → returns False
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.evolution.collaboration.approval_gateway import ApprovalGateway
from shared.evolution.collaboration.models import PatternStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_store():
    store = AsyncMock()
    store.get_pattern = AsyncMock()
    store.approve_pattern = AsyncMock()
    store.update_status = AsyncMock()
    return store


@pytest.fixture
def mock_feishu():
    feishu = AsyncMock()
    feishu.send_text = AsyncMock()
    return feishu


def make_pattern(shadow_count=25):
    """Create a mock pattern with N shadow results."""
    pattern = MagicMock()
    pattern.pattern_id = "pat_test"
    pattern.name = "Test Pattern"
    pattern.trigger_event = "sync.completed"
    pattern.steps = [{"step_id": "s1"}, {"step_id": "s2"}]
    pattern.shadow_results = [
        {"steps": [{"success": True}, {"success": True}]}
        for _ in range(shadow_count)
    ]
    return pattern


# ---------------------------------------------------------------------------
# Tests: maybe_request_approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMaybeRequestApproval:
    # 1. Skips if < 20 shadow runs
    async def test_skips_if_insufficient_shadow_runs(self, mock_store):
        pattern = make_pattern(shadow_count=19)
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(
            pattern_store=mock_store,
            admin_chat_id="chat_001",
        )
        result = await gateway.maybe_request_approval("pat_test")

        assert result is False

    async def test_skips_exactly_at_boundary(self, mock_store):
        """Boundary: exactly MIN_SHADOW_RUNS - 1 = 19 runs → skip."""
        pattern = make_pattern(shadow_count=ApprovalGateway.MIN_SHADOW_RUNS - 1)
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(pattern_store=mock_store, admin_chat_id="chat_001")
        result = await gateway.maybe_request_approval("pat_test")

        assert result is False

    # 2. Sends approval card when >= 20 runs
    async def test_sends_card_when_enough_runs(self, mock_store, mock_feishu):
        pattern = make_pattern(shadow_count=20)
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(
            pattern_store=mock_store,
            feishu_service=mock_feishu,
            admin_chat_id="chat_001",
        )
        result = await gateway.maybe_request_approval("pat_test")

        assert result is True
        mock_feishu.send_text.assert_called_once()
        call_kwargs = mock_feishu.send_text.call_args
        assert call_kwargs.kwargs["chat_id"] == "chat_001"

    async def test_sends_card_with_more_than_minimum_runs(self, mock_store, mock_feishu):
        pattern = make_pattern(shadow_count=50)
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(
            pattern_store=mock_store,
            feishu_service=mock_feishu,
            admin_chat_id="chat_001",
        )
        result = await gateway.maybe_request_approval("pat_test")

        assert result is True

    # 3. Report content: name, run count, success rate — no raw prompts
    async def test_report_contains_required_metrics(self, mock_store, mock_feishu):
        pattern = make_pattern(shadow_count=20)
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(
            pattern_store=mock_store,
            feishu_service=mock_feishu,
            admin_chat_id="chat_001",
        )
        await gateway.maybe_request_approval("pat_test")

        sent_text = mock_feishu.send_text.call_args.kwargs["text"]
        assert "Test Pattern" in sent_text
        assert "20" in sent_text          # shadow run count
        assert "100%" in sent_text        # success rate (all steps succeed)
        assert "pat_test" in sent_text    # pattern id

    async def test_report_calculates_partial_success_rate(self, mock_store, mock_feishu):
        """Half of runs have a failing step → success rate = 50%."""
        pattern = MagicMock()
        pattern.pattern_id = "pat_partial"
        pattern.name = "Partial Pattern"
        pattern.trigger_event = "sync.completed"
        pattern.steps = [{"step_id": "s1"}]
        # 10 successful runs, 10 failed runs (one step fails)
        pattern.shadow_results = (
            [{"steps": [{"success": True}]}] * 10
            + [{"steps": [{"success": False}]}] * 10
        )
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(
            pattern_store=mock_store,
            feishu_service=mock_feishu,
            admin_chat_id="chat_001",
        )
        await gateway.maybe_request_approval("pat_partial")

        sent_text = mock_feishu.send_text.call_args.kwargs["text"]
        assert "50%" in sent_text

    async def test_report_no_raw_prompts(self, mock_store, mock_feishu):
        """Report must not contain raw prompt text."""
        raw_prompt = "SECRET_PROMPT_CONTENT"
        pattern = make_pattern(shadow_count=20)
        # Inject raw prompt into a field that should NOT appear in report
        pattern.trigger_condition = raw_prompt
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(
            pattern_store=mock_store,
            feishu_service=mock_feishu,
            admin_chat_id="chat_001",
        )
        await gateway.maybe_request_approval("pat_test")

        sent_text = mock_feishu.send_text.call_args.kwargs["text"]
        assert raw_prompt not in sent_text

    # 7. Feishu send failure → returns False
    async def test_feishu_send_failure_returns_false(self, mock_store, mock_feishu):
        pattern = make_pattern(shadow_count=25)
        mock_store.get_pattern.return_value = pattern
        mock_feishu.send_text.side_effect = RuntimeError("connection refused")

        gateway = ApprovalGateway(
            pattern_store=mock_store,
            feishu_service=mock_feishu,
            admin_chat_id="chat_001",
        )
        result = await gateway.maybe_request_approval("pat_test")

        assert result is False

    # 8. No feishu service configured → still returns True
    async def test_no_feishu_service_still_returns_true(self, mock_store):
        pattern = make_pattern(shadow_count=25)
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(
            pattern_store=mock_store,
            feishu_service=None,
            admin_chat_id="",
        )
        result = await gateway.maybe_request_approval("pat_test")

        assert result is True

    # 9. Pattern not found → returns False
    async def test_pattern_not_found_returns_false(self, mock_store):
        mock_store.get_pattern.return_value = None

        gateway = ApprovalGateway(pattern_store=mock_store, admin_chat_id="chat_001")
        result = await gateway.maybe_request_approval("pat_missing")

        assert result is False

    async def test_empty_shadow_results_returns_false(self, mock_store):
        pattern = make_pattern(shadow_count=0)
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(pattern_store=mock_store, admin_chat_id="chat_001")
        result = await gateway.maybe_request_approval("pat_test")

        assert result is False

    async def test_none_shadow_results_returns_false(self, mock_store):
        pattern = MagicMock()
        pattern.pattern_id = "pat_none"
        pattern.shadow_results = None
        mock_store.get_pattern.return_value = pattern

        gateway = ApprovalGateway(pattern_store=mock_store, admin_chat_id="chat_001")
        result = await gateway.maybe_request_approval("pat_none")

        assert result is False


# ---------------------------------------------------------------------------
# Tests: process_approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProcessApproval:
    # 4. Rejects unauthorized user_id → returns False
    async def test_rejects_unauthorized_user(self, mock_store):
        gateway = ApprovalGateway(
            pattern_store=mock_store,
            admin_user_ids=["admin_001"],
        )
        result = await gateway.process_approval("pat_test", user_id="hacker_99", approved=True)

        assert result is False
        mock_store.approve_pattern.assert_not_called()
        mock_store.update_status.assert_not_called()

    async def test_rejects_when_no_admins_configured(self, mock_store):
        gateway = ApprovalGateway(
            pattern_store=mock_store,
            admin_user_ids=[],
        )
        result = await gateway.process_approval("pat_test", user_id="some_user", approved=True)

        assert result is False

    # 5. Approves: calls approve_pattern with approved_by
    async def test_approved_calls_approve_pattern(self, mock_store):
        gateway = ApprovalGateway(
            pattern_store=mock_store,
            admin_user_ids=["admin_001", "admin_002"],
        )
        result = await gateway.process_approval("pat_test", user_id="admin_001", approved=True)

        assert result is True
        mock_store.approve_pattern.assert_called_once_with(
            "pat_test", approved_by="admin_001"
        )
        mock_store.update_status.assert_not_called()

    async def test_second_admin_can_approve(self, mock_store):
        gateway = ApprovalGateway(
            pattern_store=mock_store,
            admin_user_ids=["admin_001", "admin_002"],
        )
        result = await gateway.process_approval("pat_test", user_id="admin_002", approved=True)

        assert result is True
        mock_store.approve_pattern.assert_called_once_with(
            "pat_test", approved_by="admin_002"
        )

    # 6. Rejects: sets status=retired
    async def test_rejected_sets_status_retired(self, mock_store):
        gateway = ApprovalGateway(
            pattern_store=mock_store,
            admin_user_ids=["admin_001"],
        )
        result = await gateway.process_approval("pat_test", user_id="admin_001", approved=False)

        assert result is True
        mock_store.update_status.assert_called_once_with("pat_test", PatternStatus.RETIRED)
        mock_store.approve_pattern.assert_not_called()
