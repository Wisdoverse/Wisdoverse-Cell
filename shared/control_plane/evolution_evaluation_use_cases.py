"""Use cases for recording and listing fixed-case evolution comparisons."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from shared.evolution.evaluation_batch import (
    EvaluationBatch,
    EvaluationPolicy,
    compare_evaluations,
)

from .evolution_evaluation_models import (
    EvolutionEvaluationReport,
    new_evaluation_report_id,
)
from .evolution_evaluation_ports import ControlPlaneEvolutionEvaluationStore
from .models import AuditEvent

EVALUATION_REPORT_VERSION = "fixed-case-evaluation-v1"


class EvolutionEvaluationProposalNotFoundError(Exception):
    """Raised when the proposal is missing or owned by another company."""


class EvolutionEvaluationCompatibilityError(ValueError):
    """Raised when evaluation arms cannot be compared as one fixed batch."""


async def record_evaluation_comparison(
    store: ControlPlaneEvolutionEvaluationStore,
    *,
    company_id: str,
    proposal_id: str,
    baseline: EvaluationBatch,
    candidate: EvaluationBatch,
    policy: EvaluationPolicy,
    actor_id: str = "api",
) -> EvolutionEvaluationReport:
    """Validate and append an immutable proposal-linked comparison report."""

    proposal = await store.get_evolution_proposal(proposal_id)
    if proposal is None or proposal.company_id != company_id:
        raise EvolutionEvaluationProposalNotFoundError(proposal_id)

    comparison = compare_evaluations(baseline, candidate, policy)
    incompatible = {"evaluation_cases_mismatch", "budget_mismatch"}
    if incompatible.intersection(comparison.reasons):
        raise EvolutionEvaluationCompatibilityError(
            ",".join(reason for reason in comparison.reasons if reason in incompatible)
        )

    baseline_payload = baseline.model_dump(mode="json")
    candidate_payload = candidate.model_dump(mode="json")
    policy_payload = policy.model_dump(mode="json")
    report_id = new_evaluation_report_id()
    report = EvolutionEvaluationReport(
        evaluation_report_id=report_id,
        company_id=company_id,
        proposal_id=proposal_id,
        baseline_skill_version_id=baseline.config_revision,
        candidate_skill_version_id=candidate.config_revision,
        dataset_revision=baseline.dataset_revision,
        baseline_batch_hash=_content_hash(baseline_payload),
        candidate_batch_hash=_content_hash(candidate_payload),
        baseline_batch=baseline_payload,
        candidate_batch=candidate_payload,
        policy=policy_payload,
        comparison_report=comparison.model_dump(mode="json"),
        evaluator_version=EVALUATION_REPORT_VERSION,
    )
    created = await store.create_evaluation_report(report)
    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action="evolution_evaluation.recorded",
            target_type="evolution_evaluation_report",
            target_id=created.evaluation_report_id,
            actor_type="user",
            actor_id=actor_id,
            detail={
                "proposal_id": proposal_id,
                "evaluation_report_id": created.evaluation_report_id,
                "baseline_skill_version_id": created.baseline_skill_version_id,
                "candidate_skill_version_id": created.candidate_skill_version_id,
                "eligible": comparison.eligible,
                "baseline_batch_hash": created.baseline_batch_hash,
                "candidate_batch_hash": created.candidate_batch_hash,
            },
        )
    )
    return created


async def list_evaluation_comparisons(
    store: ControlPlaneEvolutionEvaluationStore,
    *,
    company_id: str,
    proposal_id: str,
) -> list[EvolutionEvaluationReport]:
    """List fixed-case reports after enforcing proposal company ownership."""

    proposal = await store.get_evolution_proposal(proposal_id)
    if proposal is None or proposal.company_id != company_id:
        raise EvolutionEvaluationProposalNotFoundError(proposal_id)
    return await store.list_evaluation_reports(
        company_id=company_id,
        proposal_id=proposal_id,
    )


def _content_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "EVALUATION_REPORT_VERSION",
    "EvolutionEvaluationCompatibilityError",
    "EvolutionEvaluationProposalNotFoundError",
    "list_evaluation_comparisons",
    "record_evaluation_comparison",
]
