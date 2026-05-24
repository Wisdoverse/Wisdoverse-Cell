"""Unit tests for the AcceptanceVerdict value object."""

from __future__ import annotations

import pytest

from agents.qa_agent.core.domain.acceptance_verdict import (
    AcceptanceVerdict,
    InvalidAcceptanceVerdictError,
)
from agents.qa_agent.core.domain.acceptance_vocabulary import (
    GATE_ERROR,
    GATE_FAIL,
    GATE_PASS,
    L1_ERROR,
    L1_PASS,
    L1_WARN,
    L2_INFO,
)


def test_construct_clean_run():
    v = AcceptanceVerdict(
        l0_gate=GATE_PASS,
        l1_status=L1_PASS,
        l2_status=L2_INFO,
    )
    assert v.is_clean
    assert not v.is_blocking


def test_blocking_run():
    v = AcceptanceVerdict(
        l0_gate=GATE_FAIL,
        l1_status=L1_PASS,
        l2_status=L2_INFO,
        l0_failure_count=2,
    )
    assert v.is_blocking
    assert not v.is_clean


def test_pass_with_warnings_is_not_clean():
    v = AcceptanceVerdict(
        l0_gate=GATE_PASS,
        l1_status=L1_WARN,
        l2_status=L2_INFO,
        l1_warning_count=3,
    )
    assert not v.is_clean
    assert not v.is_blocking


def test_gate_error_is_not_blocking_but_not_clean():
    """ERROR is its own category — surfaces an infra problem, not a fail-gate."""
    v = AcceptanceVerdict(
        l0_gate=GATE_ERROR,
        l1_status=L1_PASS,
        l2_status=L2_INFO,
    )
    assert not v.is_blocking
    assert not v.is_clean


def test_invalid_l0_gate_raises():
    with pytest.raises(InvalidAcceptanceVerdictError):
        AcceptanceVerdict(
            l0_gate="UNKNOWN",
            l1_status=L1_PASS,
            l2_status=L2_INFO,
        )


def test_invalid_l1_status_raises():
    with pytest.raises(InvalidAcceptanceVerdictError):
        AcceptanceVerdict(
            l0_gate=GATE_PASS,
            l1_status="UNKNOWN",
            l2_status=L2_INFO,
        )


def test_invalid_l2_status_raises():
    with pytest.raises(InvalidAcceptanceVerdictError):
        AcceptanceVerdict(
            l0_gate=GATE_PASS,
            l1_status=L1_PASS,
            l2_status="garbage",
        )


def test_negative_failure_count_raises():
    with pytest.raises(InvalidAcceptanceVerdictError):
        AcceptanceVerdict(
            l0_gate=GATE_FAIL,
            l1_status=L1_ERROR,
            l2_status=L2_INFO,
            l0_failure_count=-1,
        )


def test_negative_warning_count_raises():
    with pytest.raises(InvalidAcceptanceVerdictError):
        AcceptanceVerdict(
            l0_gate=GATE_PASS,
            l1_status=L1_WARN,
            l2_status=L2_INFO,
            l1_warning_count=-5,
        )


def test_verdict_is_immutable():
    v = AcceptanceVerdict(
        l0_gate=GATE_PASS,
        l1_status=L1_PASS,
        l2_status=L2_INFO,
    )
    with pytest.raises((AttributeError, Exception)):
        v.l0_gate = GATE_FAIL  # type: ignore[misc]


def test_verdict_equality_is_value_based():
    v1 = AcceptanceVerdict(
        l0_gate=GATE_FAIL,
        l1_status=L1_ERROR,
        l2_status=L2_INFO,
        l0_failure_count=2,
    )
    v2 = AcceptanceVerdict(
        l0_gate=GATE_FAIL,
        l1_status=L1_ERROR,
        l2_status=L2_INFO,
        l0_failure_count=2,
    )
    assert v1 == v2


def test_from_summary_uses_runner_summary_shape():
    v = AcceptanceVerdict.from_summary({
        "l0_gate": GATE_FAIL,
        "l1_check": L1_WARN,
        "l2_report": L2_INFO,
        "l0_failures": 2,
        "l1_warnings": 1,
    })

    assert v.l0_gate == GATE_FAIL
    assert v.l1_status == L1_WARN
    assert v.l2_status == L2_INFO
    assert v.l0_failure_count == 2
    assert v.l1_warning_count == 1


def test_l1_error_is_not_clean():
    v = AcceptanceVerdict(
        l0_gate=GATE_PASS,
        l1_status=L1_ERROR,
        l2_status=L2_INFO,
    )
    assert not v.is_clean
