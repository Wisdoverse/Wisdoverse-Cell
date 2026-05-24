"""QA acceptance verdict vocabulary.

Wraps the shared QA acceptance Published Language from
``shared.core.qa_acceptance`` with QA-domain names.

Vocabulary:

- ``GATE_VALUES`` — the verdict on the L0 gate that decides whether an
  acceptance run is blocking.
- ``L1_STATUS_VALUES`` — the verdict on the L1 checks.
- ``L2_STATUS_VALUES`` — the L2 report status alphabet.
- ``FINDING_STATUS_VALUES`` — the verdict on one individual finding.
- ``FINDING_LEVELS`` — the importance band each finding is filed under.

``is_blocking_finding`` is the single canonical place that answers the
question "should this finding fail the gate?".
``is_failing_gate`` is the canonical place that answers the gate-level
question "does this run block the merge?".
"""

from shared.core.qa_acceptance import (
    QA_FINDING_FAIL,
    QA_FINDING_INFO,
    QA_FINDING_LEVEL_L0,
    QA_FINDING_LEVEL_L1,
    QA_FINDING_LEVEL_L2,
    QA_FINDING_LEVELS,
    QA_FINDING_PASS,
    QA_FINDING_SKIP,
    QA_FINDING_STATUS_VALUES,
    QA_FINDING_WARN,
    QA_GATE_ERROR,
    QA_GATE_FAIL,
    QA_GATE_PASS,
    QA_GATE_VALUES,
    QA_L1_ERROR,
    QA_L1_PASS,
    QA_L1_STATUS_VALUES,
    QA_L1_WARN,
    QA_L2_INFO,
    QA_L2_STATUS_VALUES,
    is_qa_blocking_finding,
    is_qa_gate_failing,
    is_qa_informational_finding,
    is_qa_warning_finding,
)

# L0 gate outcomes (used on AcceptanceRun and Summary.l0_gate).
GATE_PASS = QA_GATE_PASS
GATE_FAIL = QA_GATE_FAIL
GATE_ERROR = QA_GATE_ERROR

GATE_VALUES = QA_GATE_VALUES

# L1 status outcomes (used on Summary.l1_status and AcceptanceRun.l1_status).
L1_PASS = QA_L1_PASS
L1_WARN = QA_L1_WARN
L1_ERROR = QA_L1_ERROR

L1_STATUS_VALUES = QA_L1_STATUS_VALUES

# L2 report outcomes (used on Summary.l2_report and AcceptanceRun.l2_status).
L2_INFO = QA_L2_INFO

L2_STATUS_VALUES = QA_L2_STATUS_VALUES

# Finding status (per finding in the report).
FINDING_PASS = QA_FINDING_PASS
FINDING_FAIL = QA_FINDING_FAIL
FINDING_WARN = QA_FINDING_WARN
FINDING_INFO = QA_FINDING_INFO
FINDING_SKIP = QA_FINDING_SKIP

FINDING_STATUS_VALUES = QA_FINDING_STATUS_VALUES

# Finding levels (which gate the finding feeds).
FINDING_LEVEL_L0 = QA_FINDING_LEVEL_L0
FINDING_LEVEL_L1 = QA_FINDING_LEVEL_L1
FINDING_LEVEL_L2 = QA_FINDING_LEVEL_L2

FINDING_LEVELS = QA_FINDING_LEVELS


def is_failing_gate(l0_gate: str) -> bool:
    """Return whether the L0 gate blocks the merge."""
    return is_qa_gate_failing(l0_gate)


def is_blocking_finding(*, level: str, status: str) -> bool:
    """Return whether a finding makes the acceptance run fail the L0 gate."""
    return is_qa_blocking_finding(level=level, status=status)


def is_warning_finding(*, level: str, status: str) -> bool:
    """Return whether a finding should be surfaced as a non-blocking warning."""
    return is_qa_warning_finding(level=level, status=status)


def is_informational_finding(*, level: str, status: str) -> bool:
    """Return whether a finding belongs to the L2 informational report bucket."""
    return is_qa_informational_finding(level=level, status=status)


__all__ = [
    "FINDING_FAIL",
    "FINDING_INFO",
    "FINDING_LEVELS",
    "FINDING_LEVEL_L0",
    "FINDING_LEVEL_L1",
    "FINDING_LEVEL_L2",
    "FINDING_PASS",
    "FINDING_SKIP",
    "FINDING_STATUS_VALUES",
    "FINDING_WARN",
    "GATE_ERROR",
    "GATE_FAIL",
    "GATE_PASS",
    "GATE_VALUES",
    "L1_ERROR",
    "L1_PASS",
    "L1_STATUS_VALUES",
    "L1_WARN",
    "L2_INFO",
    "L2_STATUS_VALUES",
    "is_blocking_finding",
    "is_failing_gate",
    "is_informational_finding",
    "is_warning_finding",
]
