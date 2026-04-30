"""
Prompt Safety Scanner — detects prompt injection patterns in LLM-generated system prompts.

Guards against common adversarial techniques such as instruction override, role hijacking,
system-prompt exfiltration, and HTML injection.
"""

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

MAX_PROMPT_LENGTH = 50_000


@dataclass
class ScanResult:
    """Result of a prompt safety scan."""

    is_safe: bool
    violations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in detection patterns: (compiled_regex, human_readable_message)
# ---------------------------------------------------------------------------

_BUILTIN_PATTERNS: list[tuple[str, str]] = [
    (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|constraints)",
        "Ignore instructions pattern detected",
    ),
    (
        r"(output|reveal|show|print|display)\s+(your\s+)?(system\s+prompt|instructions|rules)",
        "System prompt leak attempt",
    ),
    (
        r"you\s+are\s+now\s+\w+",
        "Role override attempt",
    ),
    (
        r"(no\s+restrictions|no\s+rules|no\s+limits|unrestricted)",
        "Restriction bypass attempt",
    ),
    (
        r"(forget|discard|override)\s+(everything|all|your\s+(?:rules|instructions))",
        "Memory override attempt",
    ),
    (
        r"<\s*/?(?:script|iframe|object|embed)",
        "HTML injection attempt",
    ),
]


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class PromptSafetyScanner:
    """Scans LLM-generated system prompts for injection and abuse patterns."""

    def __init__(
        self,
        extra_patterns: list[tuple[str, str]] | None = None,
    ) -> None:
        """
        Args:
            extra_patterns: Optional list of ``(regex_pattern, violation_message)`` tuples
                            to extend the built-in pattern set.
        """
        combined = list(_BUILTIN_PATTERNS)
        if extra_patterns:
            combined.extend(extra_patterns)

        # Pre-compile all patterns for performance; all matches are case-insensitive.
        self._patterns: list[tuple[re.Pattern[str], str]] = [
            (re.compile(pattern, re.IGNORECASE), message)
            for pattern, message in combined
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, prompt: str) -> ScanResult:
        """Scan *prompt* for injection patterns and validation violations.

        Returns a :class:`ScanResult` whose ``is_safe`` flag is ``True`` only
        when no violations are found.
        """
        violations: list[str] = []

        # --- Structural validation ---
        if not prompt or not prompt.strip():
            violations.append("Prompt is empty or too short")
            return ScanResult(is_safe=False, violations=violations)

        if len(prompt) > MAX_PROMPT_LENGTH:
            violations.append("Prompt length exceeds max")
            return ScanResult(is_safe=False, violations=violations)

        # --- Pattern matching ---
        for compiled, message in self._patterns:
            if compiled.search(prompt):
                violations.append(message)

        return ScanResult(is_safe=len(violations) == 0, violations=violations)
