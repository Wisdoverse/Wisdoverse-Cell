"""Tests for idempotent event handling via state machine guards."""
from agents.capabilities.development.models.schemas import VALID_TRANSITIONS


class TestIdempotencyGuards:
    """Verify state machine guards prevent duplicate processing."""

    def test_qa_result_only_processed_in_reviewing(self):
        """qa.acceptance-completed should only be processed when status=reviewing."""
        assert "completed" in VALID_TRANSITIONS["reviewing"]
        assert "completed" not in VALID_TRANSITIONS["pending"]
        assert "completed" not in VALID_TRANSITIONS["executing"]

    def test_completed_is_terminal(self):
        """Once completed, no further transitions allowed."""
        assert VALID_TRANSITIONS["completed"] == set()

    def test_expired_is_terminal(self):
        """Once expired, no further transitions allowed."""
        assert VALID_TRANSITIONS["expired"] == set()

    def test_failed_only_retries_to_planning(self):
        """Failed tasks can only go back to planning (retry), nothing else."""
        assert VALID_TRANSITIONS["failed"] == {"planning"}

    def test_duplicate_pending_to_planning(self):
        """pending -> planning is valid (first processing)."""
        assert "planning" in VALID_TRANSITIONS["pending"]

    def test_all_active_states_can_fail(self):
        """All active states should be able to transition to failed."""
        active_states = [
            "pending",
            "planning",
            "awaiting_approval",
            "executing",
            "security_scanning",
            "mr_creating",
            "mr_created",
            "qa_triggered",
            "reviewing",
        ]
        for state in active_states:
            assert "failed" in VALID_TRANSITIONS[state], f"{state} cannot fail"
