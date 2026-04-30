"""Task risk classification for HITL decision-making."""
from __future__ import annotations

import re

from ..models.schemas import RiskLevel, SanitizedTask

_CRITICAL_KEYWORDS = re.compile(
    r"\b(migration|infra|infrastructure|permission|secret|credential|"
    r"database\s+schema|alembic|docker-compose|helm|terraform)\b",
    re.IGNORECASE,
)
_HIGH_KEYWORDS = re.compile(
    r"\b(security|auth|encrypt|token|cross.agent|shared/|"
    r"middleware|gateway|certificate)\b",
    re.IGNORECASE,
)
_LOW_KEYWORDS = re.compile(
    r"\b(docs?|readme|comment|typo|tests?|spec|config|lint|format)\b",
    re.IGNORECASE,
)


class TaskRiskAssessor:
    def assess(self, task: SanitizedTask) -> RiskLevel:
        text = f"{task.title} {task.description}"
        files_text = " ".join(task.related_files)
        if _CRITICAL_KEYWORDS.search(text):
            return RiskLevel.CRITICAL
        if _HIGH_KEYWORDS.search(text) or "shared/" in files_text:
            return RiskLevel.HIGH
        if _LOW_KEYWORDS.search(text):
            return RiskLevel.LOW
        return RiskLevel.MEDIUM
