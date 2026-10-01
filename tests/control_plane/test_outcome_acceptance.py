"""Business outcome review stays bound to intact, latest-run evidence."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.domain.execution_policy import ExecutionDenied
from shared.control_plane.execution_models import ExecutionLeaseTable
from shared.control_plane.execution_store import SqlAlchemyExecutionGovernanceStore
from shared.control_plane.models import (
    AgentRole,
    AgentRun,
    AgentRunStatus,
    Artifact,
    ArtifactType,
    CompanyContext,
    WorkItem,
    WorkItemStatus,
)
from shared.control_plane.outcome_store import SqlAlchemyOutcomeStore
from shared.control_plane.run_evidence import hash_evidence
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.tables import AgentRunTable, ArtifactTable, WorkItemTable


async def _seed_reviewable(
    session: AsyncSession,
    *,
    output: dict,
    company_id: str = "cmp_outcome",
    agent_id: str = "review-runner",
    run_id: str = "run_outcome_success",
) -> tuple[WorkItem, AgentRun, Artifact]:
    stores = ControlPlaneStores(session)
    await stores.companies.create_company(CompanyContext(company_id=company_id, name="Outcome Co"))
    work = await stores.work_items.create_work_item(
        WorkItem(
            company_id=company_id,
            title="Review a deliverable",
            status=WorkItemStatus.BLOCKED,
            owner_agent_id=agent_id,
        )
    )
    run = await stores.agent_runs.create_agent_run(
        AgentRun(
            run_id=run_id,
            company_id=company_id,
            agent_id=agent_id,
            status=AgentRunStatus.SUCCEEDED,
            work_item_id=work.work_item_id,
            input_event={"event_id": "evt_outcome_input"},
            output_events=[{"payload": {"output": output}}],
        )
    )
    evidence = {
        "schema_version": "1.0",
        "run_id": run_id,
        "company_id": company_id,
        "status": "succeeded",
        "events": {"output_event_ids": ["evt_outcome_output"]},
        "input_payload_hash": hash_evidence(run.input_event or {}),
        "output_payload_hash": hash_evidence({"output_events": run.output_events}),
    }
    artifact = await stores.artifacts.create_artifact(
        Artifact(
            company_id=company_id,
            artifact_type=ArtifactType.RUN_WALKTHROUGH,
            title="Runner evidence",
            uri=f"artifact://control-plane/runs/{run_id}/evidence",
            content_hash=hash_evidence(evidence),
            run_id=run_id,
            work_item_id=work.work_item_id,
            created_by_agent_id=agent_id,
            metadata={"evidence": evidence},
        )
    )
    await session.flush()
    return work, run, artifact


@pytest.mark.parametrize("output", [{"status": "recorded"}, {}])
@pytest.mark.asyncio
async def test_recorded_or_empty_executor_output_cannot_be_accepted(
    db_session: AsyncSession, output: dict
) -> None:
    work, _, artifact = await _seed_reviewable(db_session, output=output)

    with pytest.raises(ExecutionDenied, match="recorded_run_is_not_business_output"):
        await SqlAlchemyOutcomeStore(db_session).review(
            company_id=work.company_id,
            work_item_id=work.work_item_id,
            artifact_id=artifact.artifact_id,
            actor_id="reviewer",
            verdict="accepted",
            reason="The requested business outcome is present.",
        )


@pytest.mark.asyncio
async def test_artifact_evidence_tampering_is_rejected_before_acceptance(
    db_session: AsyncSession,
) -> None:
    work, _, artifact = await _seed_reviewable(
        db_session, output={"status": "ok", "response": {"report": "ready"}}
    )
    artifact_row = await db_session.get(ArtifactTable, artifact.artifact_id)
    assert artifact_row is not None
    artifact_row.metadata_json["evidence"]["status"] = "failed"
    await db_session.flush()

    with pytest.raises(ExecutionDenied, match="artifact_evidence_integrity_failed"):
        await SqlAlchemyOutcomeStore(db_session).review(
            company_id=work.company_id,
            work_item_id=work.work_item_id,
            artifact_id=artifact.artifact_id,
            actor_id="reviewer",
            verdict="accepted",
            reason="Review the original run evidence.",
        )


@pytest.mark.asyncio
async def test_new_execution_claim_revokes_prior_acceptance_and_prevents_close(
    db_session: AsyncSession,
) -> None:
    work, _, artifact = await _seed_reviewable(
        db_session, output={"status": "ok", "response": {"document": "v1"}}
    )
    stores = ControlPlaneStores(db_session)
    agent = await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=work.company_id,
            agent_id=work.owner_agent_id or "review-runner",
            display_name="Review Runner",
            adapter_type="process",
            permissions=["work.execute", "adapter:process", "tool:wakeup"],
            adapter_config={"command": ["python", "-c", "print('rerun')"], "max_cost_usd": 0},
        )
    )
    outcomes = SqlAlchemyOutcomeStore(db_session)
    await outcomes.review(
        company_id=work.company_id,
        work_item_id=work.work_item_id,
        artifact_id=artifact.artifact_id,
        actor_id="reviewer",
        verdict="accepted",
        reason="Reviewed the original deliverable.",
    )
    await db_session.commit()

    governance = SqlAlchemyExecutionGovernanceStore(db_session)
    ticket = await governance.claim(
        agent,
        run_id="run_outcome_rerun",
        payload={"task": "rerun"},
        work_item_id=work.work_item_id,
        goal_id=None,
        actor_id="operator",
        idempotency_key="outcome-rerun-key",
    )
    rerun = await stores.agent_runs.create_agent_run(
        AgentRun(
            run_id=ticket.run_id,
            company_id=work.company_id,
            agent_id=agent.agent_id,
            status=AgentRunStatus.RUNNING,
            work_item_id=work.work_item_id,
            started_at=datetime.now(UTC) + timedelta(seconds=1),
            input_event={"event_id": "evt_rerun_input"},
        )
    )
    await governance.settle(ticket, cost_usd=ticket.ceiling_usd, failed=True)
    await db_session.flush()

    current_work = await db_session.get(WorkItemTable, work.work_item_id)
    assert current_work is not None
    assert "acceptance_id" not in current_work.metadata_json
    assert "accepted_artifact_id" not in current_work.metadata_json
    assert rerun.run_id != artifact.run_id
    with pytest.raises(ExecutionDenied, match="accepted_artifact_required"):
        await stores.work_items.update_work_item_status(work.work_item_id, status="completed")


@pytest.mark.asyncio
async def test_active_and_uncertain_lease_blocks_work_mutation_until_controlled_recovery(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company_id = "cmp_outcome_lease"
    await stores.companies.create_company(CompanyContext(company_id=company_id, name="Lease Co"))
    agent = await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=company_id,
            agent_id="lease-runner",
            display_name="Lease Runner",
            adapter_type="process",
            adapter_config={"command": ["python", "-c", "pass"], "max_cost_usd": 0},
        )
    )
    work = await stores.work_items.create_work_item(
        WorkItem(
            company_id=company_id,
            title="Work with uncertain effects",
            status=WorkItemStatus.BLOCKED,
            owner_agent_id=agent.agent_id,
        )
    )
    run = await stores.agent_runs.create_agent_run(
        AgentRun(
            run_id="run_outcome_uncertain",
            company_id=company_id,
            agent_id=agent.agent_id,
            status=AgentRunStatus.RUNNING,
            work_item_id=work.work_item_id,
            input_event={"event_id": "evt_uncertain_input"},
        )
    )
    lease = ExecutionLeaseTable(
        execution_id="e" * 64,
        company_id=company_id,
        resource_id=f"work:{work.work_item_id}",
        intent_hash="a" * 64,
        run_id=run.run_id,
        owner_id="lease-owner",
        state="running",
        expires_at=datetime.now(UTC) + timedelta(minutes=2),
        created_at=datetime.now(UTC),
    )
    db_session.add(lease)
    await db_session.flush()
    governance = stores.executions

    with pytest.raises(ExecutionDenied, match="execution_control_or_recovery_required"):
        await stores.work_items.update_work_item_status(work.work_item_id, status="completed")
    with pytest.raises(ExecutionDenied, match="execution_control_or_recovery_required"):
        await stores.work_items.update_work_item_status(
            work.work_item_id, status="blocked", owner_agent_id="other-runner"
        )
    controlled = await governance.request_control(
        run_id=run.run_id,
        company_id=company_id,
        action="pause",
        reason="Pause while an operator examines external effects.",
        actor_id="operator",
    )
    assert controlled["state"] == "requested"
    assert lease.control_action == "pause"

    lease.state = "recovery_required"
    lease.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    recovered = await governance.recover(
        run_id=run.run_id,
        company_id=company_id,
        reason="Operator reconciled the uncertain process effects.",
        actor_id="operator",
    )
    await db_session.commit()
    assert recovered == {
        "run_id": run.run_id,
        "state": "failed",
        "handoff": "operator_reviewed_retry",
    }
    assert lease.state == "failed"


@pytest.mark.parametrize("review_first", [False, True])
@pytest.mark.asyncio
async def test_modified_run_payload_cannot_be_reviewed_or_closed(
    db_session: AsyncSession, review_first: bool
) -> None:
    work, run, artifact = await _seed_reviewable(
        db_session, output={"status": "ok", "response": {"report": "reviewed-v1"}}
    )
    outcomes = SqlAlchemyOutcomeStore(db_session)
    if review_first:
        await outcomes.review(
            company_id=work.company_id,
            work_item_id=work.work_item_id,
            artifact_id=artifact.artifact_id,
            actor_id="reviewer",
            verdict="accepted",
            reason="Reviewed the original report.",
        )
    stored_run = await db_session.get(AgentRunTable, run.run_id)
    assert stored_run is not None
    stored_run.output_events = [{"payload": {"output": {"status": "ok", "report": "changed-v2"}}}]
    await db_session.flush()
    with pytest.raises(ExecutionDenied, match="artifact_evidence_integrity_failed"):
        if review_first:
            await ControlPlaneStores(db_session).work_items.update_work_item_status(
                work.work_item_id, status="completed"
            )
        else:
            await outcomes.review(
                company_id=work.company_id,
                work_item_id=work.work_item_id,
                artifact_id=artifact.artifact_id,
                actor_id="reviewer",
                verdict="accepted",
                reason="Review the claimed original report.",
            )
