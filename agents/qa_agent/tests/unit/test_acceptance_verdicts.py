"""Unit tests for the QA acceptance verdict vocabulary."""

from agents.qa_agent.core.domain.acceptance_verdicts import (
    FINDING_FAIL,
    FINDING_LEVEL_L0,
    FINDING_LEVEL_L1,
    FINDING_LEVELS,
    FINDING_PASS,
    FINDING_SKIP,
    FINDING_STATUS_VALUES,
    FINDING_WARN,
    GATE_ERROR,
    GATE_FAIL,
    GATE_PASS,
    GATE_VALUES,
    L1_FAIL,
    L1_PASS,
    L1_STATUS_VALUES,
    L1_WARN,
    is_blocking_finding,
    is_warning_finding,
)


def test_gate_values_enumerated():
    assert set(GATE_VALUES) == {GATE_PASS, GATE_FAIL, GATE_ERROR}


def test_l1_status_values_enumerated():
    assert set(L1_STATUS_VALUES) == {L1_PASS, L1_WARN, L1_FAIL}


def test_finding_statuses_enumerated():
    assert set(FINDING_STATUS_VALUES) == {
        FINDING_PASS,
        FINDING_FAIL,
        FINDING_WARN,
        FINDING_SKIP,
    }


def test_finding_levels_enumerated():
    assert set(FINDING_LEVELS) == {FINDING_LEVEL_L0, FINDING_LEVEL_L1}


def test_l0_fail_finding_is_blocking():
    assert is_blocking_finding(level=FINDING_LEVEL_L0, status=FINDING_FAIL)


def test_l0_pass_finding_is_not_blocking():
    assert not is_blocking_finding(level=FINDING_LEVEL_L0, status=FINDING_PASS)


def test_l0_warn_finding_is_not_blocking():
    """Only FAIL at L0 blocks; WARN at L0 is non-blocking."""
    assert not is_blocking_finding(level=FINDING_LEVEL_L0, status=FINDING_WARN)


def test_l1_fail_finding_is_not_blocking():
    """L1 findings never block the gate, even on FAIL status."""
    assert not is_blocking_finding(level=FINDING_LEVEL_L1, status=FINDING_FAIL)


def test_l1_warn_finding_is_warning():
    assert is_warning_finding(level=FINDING_LEVEL_L1, status=FINDING_WARN)


def test_l0_warn_is_not_warning_finding():
    """A warning finding is L1+WARN; L0+WARN is not in the canonical bucket."""
    assert not is_warning_finding(level=FINDING_LEVEL_L0, status=FINDING_WARN)


def test_l1_pass_is_not_warning_finding():
    assert not is_warning_finding(level=FINDING_LEVEL_L1, status=FINDING_PASS)


def test_constants_use_uppercase_strings():
    """Vocabulary must remain uppercase to match existing string literals in code."""
    assert all(s.isupper() for s in GATE_VALUES)
    assert all(s.isupper() for s in L1_STATUS_VALUES)
    assert all(s.isupper() for s in FINDING_STATUS_VALUES)
    assert all(s.isupper() for s in FINDING_LEVELS)
