"""
Progress calculator for deriving OpenProject progress from Feishu subtask state.
"""
from typing import Any


def calculate_progress_from_subtasks(subtasks: list[dict[str, Any]]) -> int:
    """
    Calculate completion percentage from subtask status values.

    Completed-status keywords intentionally include localized Feishu table
    values and English statuses.
    """
    if not subtasks:
        return 0

    completed_keywords = {"已完成", "完成", "Done", "Closed", "已关闭"}
    total = len(subtasks)
    completed = sum(
        1 for s in subtasks
        if s.get("subtask_status", "") in completed_keywords
    )

    return round(completed / total * 100)
