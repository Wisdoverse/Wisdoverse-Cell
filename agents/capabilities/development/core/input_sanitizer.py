"""Input sanitization for PJM task data before LLM processing."""
from __future__ import annotations

import re

from shared.evolution.prompt_safety_scanner import PromptSafetyScanner

from ..models.schemas import SanitizedTask, TaskInput

_SHELL_META_PATTERN = re.compile(r'[$`|;><]|\$\(')


class InputRejectedError(Exception):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__(f"Input rejected: {'; '.join(reasons)}")


class InputSanitizer:
    def __init__(self, scanner: PromptSafetyScanner | None = None):
        self._scanner = scanner or PromptSafetyScanner()

    def sanitize(self, task: TaskInput) -> SanitizedTask:
        violations: list[str] = []
        if len(task.title) > 200:
            violations.append(f"Title too long: {len(task.title)} > 200")
        if len(task.description) > 5000:
            violations.append(f"Description too long: {len(task.description)} > 5000")
        if _SHELL_META_PATTERN.search(task.title):
            violations.append("Shell metacharacters in title")
        combined = f"{task.title}\n{task.description}"
        scan_result = self._scanner.scan(combined)
        if not scan_result.is_safe:
            violations.extend(scan_result.violations)
        if violations:
            raise InputRejectedError(violations)
        return SanitizedTask(**task.model_dump())
