"""Published language for QA acceptance result contracts.

The QA Agent owns acceptance execution, but Dev and other downstream
contexts consume ``qa.acceptance-completed`` events. Those consumers must
not import ``agents.qa_agent`` internals, so stable event vocabulary lives
here as shared core contract data.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

QA_GATE_PASS = "PASS"
QA_GATE_FAIL = "FAIL"
QA_GATE_ERROR = "ERROR"
QA_GATE_VALUES: tuple[str, ...] = (
    QA_GATE_PASS,
    QA_GATE_FAIL,
    QA_GATE_ERROR,
)

QA_L1_PASS = "PASS"
QA_L1_WARN = "WARN"
QA_L1_ERROR = "ERROR"
QA_L1_STATUS_VALUES: tuple[str, ...] = (
    QA_L1_PASS,
    QA_L1_WARN,
    QA_L1_ERROR,
)

QA_L2_INFO = "INFO"
QA_L2_STATUS_VALUES: tuple[str, ...] = (QA_L2_INFO,)

QA_FINDING_PASS = "PASS"
QA_FINDING_FAIL = "FAIL"
QA_FINDING_WARN = "WARN"
QA_FINDING_INFO = "INFO"
QA_FINDING_SKIP = "SKIP"
QA_FINDING_STATUS_VALUES: tuple[str, ...] = (
    QA_FINDING_PASS,
    QA_FINDING_FAIL,
    QA_FINDING_WARN,
    QA_FINDING_INFO,
    QA_FINDING_SKIP,
)

QA_FINDING_LEVEL_L0 = "L0"
QA_FINDING_LEVEL_L1 = "L1"
QA_FINDING_LEVEL_L2 = "L2"
QA_FINDING_LEVELS: tuple[str, ...] = (
    QA_FINDING_LEVEL_L0,
    QA_FINDING_LEVEL_L1,
    QA_FINDING_LEVEL_L2,
)

QA_API_STATUS_PASSED = "passed"
QA_API_STATUS_FAILED = "failed"
QA_API_STATUS_WARN = "warn"
QA_API_STATUS_ERROR = "error"


def qa_l0_gate_from_summary(summary: Mapping[str, Any]) -> str:
    """Extract the L0 gate value from a QA acceptance event summary."""
    return str(summary.get("l0_gate", QA_GATE_ERROR))


def is_qa_gate_passing(l0_gate: str) -> bool:
    """Return whether the L0 gate passed."""
    return l0_gate == QA_GATE_PASS


def is_qa_gate_failing(l0_gate: str) -> bool:
    """Return whether the L0 gate blocks the merge."""
    return l0_gate == QA_GATE_FAIL


def is_qa_acceptance_passed(summary: Mapping[str, Any]) -> bool:
    """Return whether a QA acceptance summary is a passed gate."""
    return is_qa_gate_passing(qa_l0_gate_from_summary(summary))


def is_qa_acceptance_failed(summary: Mapping[str, Any]) -> bool:
    """Return whether a QA acceptance summary is a failed gate."""
    return is_qa_gate_failing(qa_l0_gate_from_summary(summary))


def qa_api_status_from_l0_gate(l0_gate: str) -> str:
    """Map a QA L0 gate value to the public API status vocabulary."""
    return {
        QA_GATE_PASS: QA_API_STATUS_PASSED,
        QA_GATE_FAIL: QA_API_STATUS_FAILED,
        QA_GATE_ERROR: QA_API_STATUS_ERROR,
    }.get(l0_gate, QA_API_STATUS_ERROR)


def is_qa_blocking_finding(*, level: str, status: str) -> bool:
    """Return whether a finding makes the QA acceptance run fail L0."""
    return level == QA_FINDING_LEVEL_L0 and status == QA_FINDING_FAIL


def is_qa_warning_finding(*, level: str, status: str) -> bool:
    """Return whether a finding should be surfaced as a warning."""
    return level == QA_FINDING_LEVEL_L1 and status == QA_FINDING_WARN


def is_qa_informational_finding(*, level: str, status: str) -> bool:
    """Return whether a finding belongs to the L2 informational bucket."""
    return level == QA_FINDING_LEVEL_L2 and status == QA_FINDING_INFO


__all__ = [
    "QA_FINDING_FAIL",
    "QA_FINDING_INFO",
    "QA_FINDING_LEVELS",
    "QA_FINDING_LEVEL_L0",
    "QA_FINDING_LEVEL_L1",
    "QA_FINDING_LEVEL_L2",
    "QA_FINDING_PASS",
    "QA_FINDING_SKIP",
    "QA_FINDING_STATUS_VALUES",
    "QA_FINDING_WARN",
    "QA_API_STATUS_ERROR",
    "QA_API_STATUS_FAILED",
    "QA_API_STATUS_PASSED",
    "QA_API_STATUS_WARN",
    "QA_GATE_ERROR",
    "QA_GATE_FAIL",
    "QA_GATE_PASS",
    "QA_GATE_VALUES",
    "QA_L1_ERROR",
    "QA_L1_PASS",
    "QA_L1_STATUS_VALUES",
    "QA_L1_WARN",
    "QA_L2_INFO",
    "QA_L2_STATUS_VALUES",
    "is_qa_acceptance_failed",
    "is_qa_acceptance_passed",
    "is_qa_blocking_finding",
    "is_qa_gate_failing",
    "is_qa_gate_passing",
    "is_qa_informational_finding",
    "is_qa_warning_finding",
    "qa_api_status_from_l0_gate",
    "qa_l0_gate_from_summary",
]
