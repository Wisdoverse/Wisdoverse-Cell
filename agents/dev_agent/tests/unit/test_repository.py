
from agents.dev_agent.db.repository import DevTaskRepository


class TestTransitionGuard:
    def test_valid_transition_pending_to_planning(self):
        repo = DevTaskRepository.__new__(DevTaskRepository)
        assert repo._is_valid_transition("pending", "planning")

    def test_invalid_transition_pending_to_completed(self):
        repo = DevTaskRepository.__new__(DevTaskRepository)
        assert not repo._is_valid_transition("pending", "completed")

    def test_failed_can_retry_to_planning(self):
        repo = DevTaskRepository.__new__(DevTaskRepository)
        assert repo._is_valid_transition("failed", "planning")

    def test_completed_is_terminal(self):
        repo = DevTaskRepository.__new__(DevTaskRepository)
        assert not repo._is_valid_transition("completed", "planning")
        assert not repo._is_valid_transition("completed", "failed")

    def test_all_states_can_go_to_failed(self):
        repo = DevTaskRepository.__new__(DevTaskRepository)
        for state in ["pending", "planning", "executing", "reviewing"]:
            assert repo._is_valid_transition(
                state, "failed"
            ), f"{state} -> failed should be valid"
