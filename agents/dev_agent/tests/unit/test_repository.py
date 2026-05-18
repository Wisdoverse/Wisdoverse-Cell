
from agents.dev_agent.core.task_lifecycle import can_transition


class TestTransitionGuard:
    def test_valid_transition_pending_to_planning(self):
        assert can_transition("pending", "planning")

    def test_invalid_transition_pending_to_completed(self):
        assert not can_transition("pending", "completed")

    def test_failed_can_retry_to_planning(self):
        assert can_transition("failed", "planning")

    def test_completed_is_terminal(self):
        assert not can_transition("completed", "planning")
        assert not can_transition("completed", "failed")

    def test_all_states_can_go_to_failed(self):
        for state in ["pending", "planning", "executing", "reviewing"]:
            assert can_transition(state, "failed"), f"{state} -> failed should be valid"
