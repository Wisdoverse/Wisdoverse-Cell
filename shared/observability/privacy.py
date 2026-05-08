"""PII-safe helpers for logs, metrics, traces, and LLM boundaries."""

import hashlib
import re
from collections.abc import Mapping
from typing import Any

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_CANDIDATE_RE = re.compile(r"(?<!\w)\+?\d[\d .()/-]{9,}\d(?!\w)")
_PLATFORM_ID_RE = re.compile(r"\b(?:ou|oc|on|un)_[A-Za-z0-9_-]{8,}\b")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_API_KEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|"
    r"sk-ant-[A-Za-z0-9_-]{16,}|"
    r"gsk_[A-Za-z0-9_-]{16,}|"
    r"ghp_[A-Za-z0-9_]{16,}|"
    r"glpat-[A-Za-z0-9_-]{16,}|"
    r"xox[baprs]-[A-Za-z0-9-]{16,})\b"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"[A-Za-z0-9_-]{0,32}"
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token|"
    r"secret|password|authorization|signature|auth|encoding[_-]?aes[_-]?key|"
    r"encrypt[_-]?key)"
    r"[A-Za-z0-9_-]{0,32}"
    r"\s*[:=]\s*)([\"']?)[^\s,\"'}\]]+"
)
_URL_SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:access[_-]?token|refresh[_-]?token|token|api[_-]?key|key|"
    r"secret|signature|password|auth|code)=)[^&#\s]+"
)
_URL_SCHEME_RE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]{0,20}://")
_URL_AUTHORITY_TERMINATORS = frozenset("/?# \t\r\n")

_REDACTED_SECRET = "[REDACTED_SECRET]"
_REDACTED_BYTES = "[REDACTED_BYTES]"

_SENSITIVE_KEY_NAMES = {
    "api_key",
    "apikey",
    "app_secret",
    "auth",
    "auth_token",
    "authorization",
    "client_secret",
    "encoding_aes_key",
    "encrypt_key",
    "password",
    "refresh_token",
    "secret",
    "signature",
    "token",
}


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    if normalized in _SENSITIVE_KEY_NAMES:
        return True
    return (
        normalized.endswith("_secret")
        or normalized.endswith("_password")
        or normalized.endswith("_signature")
        or (normalized.endswith("_token") and not normalized.endswith("_tokens"))
        or normalized.endswith("_api_key")
    )


def redact_sensitive_text(text: str) -> str:
    """Remove secrets and direct PII-like identifiers from free-form text."""
    redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    redacted = _PLATFORM_ID_RE.sub("[REDACTED_PLATFORM_ID]", redacted)
    redacted = _JWT_RE.sub(_REDACTED_SECRET, redacted)
    redacted = _API_KEY_RE.sub(_REDACTED_SECRET, redacted)
    redacted = _BEARER_RE.sub(f"Bearer {_REDACTED_SECRET}", redacted)
    redacted = _URL_SECRET_QUERY_RE.sub(r"\1[REDACTED_SECRET]", redacted)
    redacted = _redact_url_credentials(redacted)
    redacted = _SECRET_ASSIGNMENT_RE.sub(r"\1\2[REDACTED_SECRET]", redacted)

    def _redact_phone(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) >= 11:
            return "[REDACTED_PHONE]"
        return match.group(0)

    return _PHONE_CANDIDATE_RE.sub(_redact_phone, redacted)


def _redact_url_credentials(text: str) -> str:
    """Redact passwords from URLs without using a backtracking authority regex."""
    pieces: list[str] = []
    cursor = 0

    for match in _URL_SCHEME_RE.finditer(text):
        authority_start = match.end()
        authority_end = authority_start
        while authority_end < len(text) and text[authority_end] not in _URL_AUTHORITY_TERMINATORS:
            authority_end += 1

        authority = text[authority_start:authority_end]
        at_index = authority.rfind("@")
        colon_index = authority.find(":")
        if at_index < 0 or colon_index < 0 or colon_index > at_index:
            continue

        pieces.append(text[cursor : authority_start + colon_index + 1])
        pieces.append(_REDACTED_SECRET)
        pieces.append(authority[at_index:])
        cursor = authority_end

    if not pieces:
        return text

    pieces.append(text[cursor:])
    return "".join(pieces)


def redact_for_observability(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact data before it reaches logs, metrics, or traces."""
    if _depth > 10:
        return "[REDACTED_DEPTH_LIMIT]"
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, bytes):
        digest = hashlib.sha256(value).hexdigest()[:16]
        return f"{_REDACTED_BYTES}:sha256:{digest}:len:{len(value)}"
    if isinstance(value, BaseException):
        return redact_sensitive_text(f"{type(value).__name__}: {value}")
    if isinstance(value, Mapping):
        return {
            key: (
                _REDACTED_SECRET
                if _is_sensitive_key(key)
                else redact_for_observability(item, _depth=_depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_for_observability(item, _depth=_depth + 1) for item in value)
    if isinstance(value, list):
        return [redact_for_observability(item, _depth=_depth + 1) for item in value]
    if isinstance(value, set):
        return [redact_for_observability(item, _depth=_depth + 1) for item in value]
    return value


def hash_identifier(value: Any, *, length: int = 12) -> str:
    """Return a short one-way hash for identifiers that may contain PII."""
    text = str(value or "")
    if not text:
        return ""
    return hashlib.sha256(text.encode()).hexdigest()[:length]
