"""
Progress calculator for deriving OpenProject progress from Feishu subtask state.
"""
from typing import Any

from .domain.sync_values import is_completed_subtask_status


def calculate_progress_from_subtasks(subtasks: list[dict[str, Any]]) -> int:
    """
    Calculate completion percentage from subtask status values.

    Completed-status vocabulary intentionally includes localized Feishu table
    values and English statuses through the Sync domain value helper.
    """
    if not subtasks:
        return 0

    total = len(subtasks)
    completed = sum(
        1 for s in subtasks
        if is_completed_subtask_status(s.get("subtask_status"))
    )

    return round(completed / total * 100)
