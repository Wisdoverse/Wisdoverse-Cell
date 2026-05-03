"""PII-safe helpers for logs, metrics, and traces."""

import hashlib
from typing import Any


def hash_identifier(value: Any, *, length: int = 12) -> str:
    """Return a short one-way hash for identifiers that may contain PII."""
    text = str(value or "")
    if not text:
        return ""
    return hashlib.sha256(text.encode()).hexdigest()[:length]
