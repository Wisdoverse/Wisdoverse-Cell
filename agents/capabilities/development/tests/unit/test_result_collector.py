from agents.capabilities.development.models.schemas import VALID_TRANSITIONS


def test_executing_to_security_scanning():
    assert "security_scanning" in VALID_TRANSITIONS["executing"]


def test_security_scanning_to_mr_creating():
    assert "mr_creating" in VALID_TRANSITIONS["security_scanning"]


def test_mr_created_to_qa_triggered():
    assert "qa_triggered" in VALID_TRANSITIONS["mr_created"]


def test_reviewing_to_completed():
    assert "completed" in VALID_TRANSITIONS["reviewing"]


def test_reviewing_to_failed():
    assert "failed" in VALID_TRANSITIONS["reviewing"]


def test_failed_can_retry():
    assert "planning" in VALID_TRANSITIONS["failed"]


def test_completed_is_terminal():
    assert VALID_TRANSITIONS["completed"] == set()
