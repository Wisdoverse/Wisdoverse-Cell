"""Input validation for agent payloads — size limits and injection detection."""

import json
import re

from shared.utils.logger import get_logger

logger = get_logger("input_validator")

# Injection patterns (case-insensitive) — aligned with prompt_safety_scanner.py
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"(show|reveal|print|output)\s+(me\s+)?(your|the)\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+\w+.*?(without|no)\s+(restrictions|rules|limits)", re.IGNORECASE),
    re.compile(r"(forget|disregard)\s+(everything|all|your)\s+(you|instructions|rules)", re.IGNORECASE),
    re.compile(r"<\s*script\b", re.IGNORECASE),
]


class InputValidationError(ValueError):
    """Raised when input validation fails."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


class InputValidator:
    """Validates agent input payloads for size and injection attacks."""

    def __init__(self, *, max_payload_bytes: int = 1_000_000):
        self.max_payload_bytes = max_payload_bytes

    def validate(self, payload: dict) -> None:
        """Validate a payload dict. Raises InputValidationError on failure."""
        self._check_size(payload)
        self._check_injection(payload)

    def _check_size(self, payload: dict) -> None:
        size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if size > self.max_payload_bytes:
            logger.warning("payload_too_large", size=size, limit=self.max_payload_bytes)
            raise InputValidationError(
                "payload_too_large",
                f"Payload is {size} bytes, limit is {self.max_payload_bytes}",
            )

    def _check_injection(self, payload: dict) -> None:
        for text in self._extract_strings(payload):
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(text):
                    logger.warning(
                        "injection_detected",
                        pattern=pattern.pattern[:60],
                        text_preview=text[:100],
                    )
                    raise InputValidationError(
                        "injection_detected",
                        f"Suspicious pattern in input: {pattern.pattern[:60]}",
                    )

    def _extract_strings(self, obj, *, _depth: int = 0) -> list[str]:
        """Recursively extract all string values from nested dicts/lists."""
        if _depth > 10:
            return []
        strings = []
        if isinstance(obj, str):
            strings.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                strings.extend(self._extract_strings(v, _depth=_depth + 1))
        elif isinstance(obj, list):
            for item in obj:
                strings.extend(self._extract_strings(item, _depth=_depth + 1))
        return strings
