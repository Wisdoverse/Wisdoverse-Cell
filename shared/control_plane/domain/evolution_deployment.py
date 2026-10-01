"""Evidence and lifecycle policy for L1 releases."""

from typing import Any

from .execution_policy import ExecutionDenied

TARGET_STATES = {
    "shadow": "shadow",
    "canary": "canary",
    "promote": "active",
    "rollback": "rolled_back",
}
ALLOWED_ACTIONS = {
    None: {"shadow"},
    "shadow": {"canary", "rollback"},
    "canary": {"promote", "rollback"},
    "active": {"rollback"},
    "rolled_back": set(),
}


def validate_release(
    *,
    tier: str,
    state: str | None,
    action: str,
    report: dict[str, Any],
    baseline_ref: str,
    candidate_ref: str,
) -> None:
    if tier != "L1":
        raise ExecutionDenied("only_l1_skill_release_supported", 400)
    if action not in ALLOWED_ACTIONS.get(state, set()):
        raise ExecutionDenied("invalid_skill_release_transition")
    if (
        report["baseline"]["config_revision"] != baseline_ref
        or report["candidate"]["config_revision"] != candidate_ref
    ):
        raise ExecutionDenied("evaluation_skill_version_mismatch", 400)
    if action in {"canary", "promote"}:
        if report.get("eligible") is not True:
            raise ExecutionDenied("evaluation_release_gates_failed", 403)
        if min(report["baseline"]["sample_count"], report["candidate"]["sample_count"]) < 50:
            raise ExecutionDenied("live_release_sample_count_required", 403)
        if (
            report["candidate"]["accepted_outcome_rate"]
            < report["baseline"]["accepted_outcome_rate"]
        ):
            raise ExecutionDenied("candidate_outcome_regression", 403)
