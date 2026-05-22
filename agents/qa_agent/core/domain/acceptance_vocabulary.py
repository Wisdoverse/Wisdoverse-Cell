"""QA acceptance verdict vocabulary.

Extracted from string literals in
``agents.qa_agent.core.acceptance_execution_use_cases``,
``agents.qa_agent.core.acceptance_runner``,
``agents.qa_agent.core.api_use_cases``, and
``agents.qa_agent.core.notifier``. Future PRs should replace literal
``"PASS"`` / ``"FAIL"`` / ``"WARN"`` / ``"SKIP"`` / ``"ERROR"`` /
``"L0"`` / ``"L1"`` strings with the constants in this module.

Vocabulary:

- ``GATE_VALUES`` — the verdict on the L0 gate that decides whether an
  acceptance run is blocking.
- ``L1_STATUS_VALUES`` — the verdict on the L1 checks.
- ``FINDING_STATUS_VALUES`` — the verdict on one individual finding.
- ``FINDING_LEVELS`` — the importance band each finding is filed under.

``is_blocking_finding`` is the single canonical place that answers the
question "should this finding fail the gate?".
"""

# L0 gate outcomes (used on AcceptanceRun and Summary.l0_gate).
GATE_PASS = "PASS"
GATE_FAIL = "FAIL"
GATE_ERROR = "ERROR"

GATE_VALUES: tuple[str, ...] = (GATE_PASS, GATE_FAIL, GATE_ERROR)

# L1 status outcomes (used on Summary.l1_status and AcceptanceRun.l1_status).
L1_PASS = "PASS"
L1_WARN = "WARN"
L1_FAIL = "FAIL"

L1_STATUS_VALUES: tuple[str, ...] = (L1_PASS, L1_WARN, L1_FAIL)

# Finding status (per finding in the report).
FINDING_PASS = "PASS"
FINDING_FAIL = "FAIL"
FINDING_WARN = "WARN"
FINDING_SKIP = "SKIP"

FINDING_STATUS_VALUES: tuple[str, ...] = (
    FINDING_PASS,
    FINDING_FAIL,
    FINDING_WARN,
    FINDING_SKIP,
)

# Finding levels (which gate the finding feeds).
FINDING_LEVEL_L0 = "L0"
FINDING_LEVEL_L1 = "L1"

FINDING_LEVELS: tuple[str, ...] = (FINDING_LEVEL_L0, FINDING_LEVEL_L1)


def is_blocking_finding(*, level: str, status: str) -> bool:
    """Return whether a finding makes the acceptance run fail the L0 gate."""
    return level == FINDING_LEVEL_L0 and status == FINDING_FAIL


def is_warning_finding(*, level: str, status: str) -> bool:
    """Return whether a finding should be surfaced as a non-blocking warning."""
    return level == FINDING_LEVEL_L1 and status == FINDING_WARN


__all__ = [
    "FINDING_FAIL",
    "FINDING_LEVELS",
    "FINDING_LEVEL_L0",
    "FINDING_LEVEL_L1",
    "FINDING_PASS",
    "FINDING_SKIP",
    "FINDING_STATUS_VALUES",
    "FINDING_WARN",
    "GATE_ERROR",
    "GATE_FAIL",
    "GATE_PASS",
    "GATE_VALUES",
    "L1_FAIL",
    "L1_PASS",
    "L1_STATUS_VALUES",
    "L1_WARN",
    "is_blocking_finding",
    "is_warning_finding",
]
