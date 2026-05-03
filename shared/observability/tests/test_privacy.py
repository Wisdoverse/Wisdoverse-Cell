"""Tests for PII-safe observability helpers."""

from shared.observability.privacy import hash_identifier


def test_hash_identifier_is_stable_and_non_reversible() -> None:
    raw = "ou_raw_user"

    result = hash_identifier(raw)

    assert result == hash_identifier(raw)
    assert result != raw
    assert len(result) == 12


def test_hash_identifier_handles_empty_values() -> None:
    assert hash_identifier("") == ""
    assert hash_identifier(None) == ""
