"""Tests for PII-safe observability helpers."""

from shared.observability.privacy import (
    hash_identifier,
    redact_for_observability,
    redact_sensitive_text,
)
from shared.utils.logger import get_logger, redact_log_event, setup_logging


def test_hash_identifier_is_stable_and_non_reversible() -> None:
    raw = "ou_raw_user"

    result = hash_identifier(raw)

    assert result == hash_identifier(raw)
    assert result != raw
    assert len(result) == 12


def test_hash_identifier_handles_empty_values() -> None:
    assert hash_identifier("") == ""
    assert hash_identifier(None) == ""


def test_redact_sensitive_text_masks_direct_pii_and_secrets() -> None:
    raw = (
        "Email user@example.com or +1 (415) 555-0199. "
        "OpenID ou_1234567890abcdef. "
        "Use Authorization: Bearer eyJabc.def.ghi and api_key=sk-1234567890abcdefghijklmnop. "
        "See https://example.com/path?token=raw-token"
    )

    redacted = redact_sensitive_text(raw)

    assert "user@example.com" not in redacted
    assert "+1 (415) 555-0199" not in redacted
    assert "ou_1234567890abcdef" not in redacted
    assert "eyJabc.def.ghi" not in redacted
    assert "sk-1234567890abcdefghijklmnop" not in redacted
    assert "raw-token" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_PLATFORM_ID]" in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_redact_for_observability_masks_sensitive_keys_and_nested_values() -> None:
    redacted = redact_for_observability(
        {
            "event": "provider error for admin@example.com",
            "input_tokens": 42,
            "api_key": "sk-1234567890abcdefghijklmnop",
            "nested": {
                "database_url": "postgresql://user:pg-secret@db/project_cell",
                "items": ["contact ou_1234567890abcdef"],
            },
        }
    )

    assert redacted["input_tokens"] == 42
    assert redacted["api_key"] == "[REDACTED_SECRET]"
    assert "admin@example.com" not in redacted["event"]
    assert "pg-secret" not in redacted["nested"]["database_url"]
    assert "ou_1234567890abcdef" not in redacted["nested"]["items"][0]


def test_redact_log_event_sanitizes_structlog_event_dict() -> None:
    processed = redact_log_event(
        None,
        "error",
        {
            "event": "request failed for user@example.com",
            "error": "invalid token=raw-secret",
            "input_tokens": 12,
        },
    )

    assert processed["input_tokens"] == 12
    assert "user@example.com" not in processed["event"]
    assert "raw-secret" not in processed["error"]


def test_configured_logger_redacts_exc_info_traceback(capsys) -> None:
    raw_secret = "token=raw-secret user@example.com"
    try:
        setup_logging(level="INFO", json_format=True)
        logger = get_logger("privacy-test")
        try:
            raise ValueError(raw_secret)
        except ValueError as exc:
            logger.error(
                "request failed for admin@example.com",
                error=str(exc),
                exc_info=True,
            )

        rendered = capsys.readouterr().out
    finally:
        setup_logging()

    assert raw_secret not in rendered
    assert "raw-secret" not in rendered
    assert "user@example.com" not in rendered
    assert "[REDACTED_SECRET]" in rendered
    assert "[REDACTED_EMAIL]" in rendered
