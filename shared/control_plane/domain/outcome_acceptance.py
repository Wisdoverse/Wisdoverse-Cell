"""Business acceptance is a reviewed artifact bound to a successful real run."""

from __future__ import annotations

from typing import Any

from .execution_policy import ExecutionDenied


def validate_outcome(work: Any, run: Any, artifact: Any, *, reason: str, verdict: str) -> None:
    if verdict not in {"accepted", "rejected"} or not reason.strip():
        raise ExecutionDenied("acceptance_reason_and_verdict_required", 400)
    if work.status in {"completed", "cancelled"}:
        raise ExecutionDenied("work_item_closed")
    if (
        artifact.company_id != work.company_id
        or artifact.work_item_id != work.work_item_id
        or artifact.run_id != run.run_id
        or run.work_item_id != work.work_item_id
        or run.company_id != work.company_id
    ):
        raise ExecutionDenied("acceptance_evidence_link_mismatch", 400)
    if run.status != "succeeded" or not artifact.content_hash:
        raise ExecutionDenied("acceptance_successful_evidence_required", 400)
    output = (
        (run.output_events or [])[-1].get("payload", {}).get("output", {})
        if run.output_events
        else {}
    )
    if output.get("status") == "recorded" or not output:
        raise ExecutionDenied("recorded_run_is_not_business_output", 400)
