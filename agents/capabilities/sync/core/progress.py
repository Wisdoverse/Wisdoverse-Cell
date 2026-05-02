"""
Progress Calculator - 根据飞书子任务状态计算 OP 进度
"""
from typing import Any


def calculate_progress_from_subtasks(subtasks: list[dict[str, Any]]) -> int:
    """
    根据子任务完成状态计算进度百分比。

    完成状态关键词: 已完成, 完成, Done, Closed
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
