"""Typed work-package identity checks for PJM decomposition workflows."""

from __future__ import annotations

from typing import get_args, get_type_hints

from agents.pjm_agent.core.decomposition_approval_workflow import (
    DecompositionApprovalWorkflow,
    PJMOpenProjectWriterPort,
    StagedPJMEvent,
)
from agents.pjm_agent.core.decomposition_ports import (
    PJMDecompositionRecord,
    PJMDecompositionTransaction,
)
from agents.pjm_agent.core.decomposition_recovery_workflow import (
    DecompositionRecoveryWorkflow,
    PJMOpenProjectReadPort,
    StagedRecoveryEvent,
)
from agents.pjm_agent.core.decomposition_request_workflow import (
    DecompositionRequestWorkflow,
    PJMDecompositionEnginePort,
    PJMDecompositionFailurePushPort,
)
from agents.pjm_agent.core.domain.decomposition import (
    Decomposition,
    DecompositionStatusChanged,
    InvalidDecompositionTransitionError,
)
from agents.pjm_agent.core.domain.lifecycle.decomposition_lifecycle import DecompositionStatus
from shared.core.identifiers import OpenProjectProjectId, WorkPackageId


def test_work_package_id_preserves_openproject_integer_contract() -> None:
    wp_id = WorkPackageId(123)

    assert wp_id == 123
    assert isinstance(wp_id, int)


def test_openproject_project_id_preserves_integer_contract() -> None:
    project_id = OpenProjectProjectId(456)

    assert project_id == 456
    assert isinstance(project_id, int)


def test_pjm_decomposition_ports_use_work_package_id() -> None:
    record_hints = get_type_hints(PJMDecompositionRecord)

    assert record_hints["wp_id"] is WorkPackageId
    assert record_hints["project_id"] is OpenProjectProjectId
    assert record_hints["status"] is DecompositionStatus
    assert get_type_hints(PJMDecompositionTransaction.create)["wp_id"] is WorkPackageId
    assert get_type_hints(PJMDecompositionTransaction.create)["project_id"] is OpenProjectProjectId
    assert get_type_hints(PJMDecompositionTransaction.get_by_wp_id)["wp_id"] is WorkPackageId
    assert get_type_hints(PJMDecompositionTransaction.update_status)["wp_id"] is WorkPackageId
    assert (
        get_type_hints(PJMDecompositionTransaction.update_status)["status"] is DecompositionStatus
    )
    assert get_type_hints(PJMDecompositionTransaction.delete_by_wp_id)["wp_id"] is WorkPackageId


def test_pjm_decomposition_aggregate_uses_work_package_id() -> None:
    assert get_type_hints(Decomposition)["wp_id"] is WorkPackageId
    assert get_type_hints(Decomposition)["status"] is DecompositionStatus
    assert get_type_hints(DecompositionStatusChanged)["wp_id"] is WorkPackageId
    assert get_type_hints(DecompositionStatusChanged)["from_status"] is DecompositionStatus
    assert get_type_hints(DecompositionStatusChanged)["to_status"] is DecompositionStatus
    assert get_type_hints(InvalidDecompositionTransitionError.__init__)["wp_id"] is WorkPackageId
    assert (
        get_type_hints(InvalidDecompositionTransitionError.__init__)["from_status"]
        is DecompositionStatus
    )
    assert (
        get_type_hints(InvalidDecompositionTransitionError.__init__)["to_status"]
        is DecompositionStatus
    )


def test_pjm_approval_workflow_uses_work_package_id_boundary() -> None:
    staged_hints = get_type_hints(StagedPJMEvent)
    staged_wp_id_args = set(get_args(staged_hints["wp_id"]))

    assert (
        get_type_hints(DecompositionApprovalWorkflow.approve_decomposition)["wp_id"]
        is WorkPackageId
    )
    assert (
        get_type_hints(DecompositionApprovalWorkflow.reject_decomposition)["wp_id"] is WorkPackageId
    )
    assert get_type_hints(PJMOpenProjectWriterPort.write_wbs)["project_id"] is OpenProjectProjectId
    assert (
        get_type_hints(PJMOpenProjectWriterPort.write_task_subtasks)["project_id"]
        is OpenProjectProjectId
    )
    assert staged_wp_id_args == {WorkPackageId, type(None)}


def test_pjm_request_workflow_uses_work_package_id_boundary() -> None:
    assert get_type_hints(PJMDecompositionEnginePort.decompose)["wp_id"] is WorkPackageId
    assert get_type_hints(PJMDecompositionEnginePort.check_task_detail)["wp_id"] is WorkPackageId
    assert (
        get_type_hints(PJMDecompositionFailurePushPort.send_decompose_failure)["wp_id"]
        is WorkPackageId
    )
    assert (
        get_type_hints(DecompositionRequestWorkflow.request_decomposition_approval)["wp_id"]
        is WorkPackageId
    )


def test_pjm_recovery_workflow_uses_work_package_id_boundary() -> None:
    staged_hints = get_type_hints(StagedRecoveryEvent)
    staged_wp_id_args = set(get_args(staged_hints["wp_id"]))

    assert get_type_hints(PJMOpenProjectReadPort.get_work_package)["wp_id"] is WorkPackageId
    assert WorkPackageId in set(
        get_args(get_type_hints(DecompositionRecoveryWorkflow.retry_decompose)["wp_id"])
    )
    assert WorkPackageId in set(
        get_args(get_type_hints(DecompositionRecoveryWorkflow.get_decompose)["wp_id"])
    )
    assert staged_wp_id_args == {WorkPackageId, type(None)}
