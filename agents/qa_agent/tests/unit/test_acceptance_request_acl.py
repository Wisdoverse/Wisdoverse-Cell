"""Tests for the QA inbound acceptance-request ACL."""

import pytest

from agents.qa_agent.adapters.acceptance_request_acl import (
    GitLabMergeRequestContext,
    OpenProjectWorkPackageContext,
    QAAcceptanceRequestACL,
)
from shared.schemas.event import Event, EventTypes


def test_code_committed_event_translates_to_qa_run_request() -> None:
    event = Event.create(
        event_type=EventTypes.CODE_COMMITTED,
        source_agent="ci",
        payload={
            "agent_name": "pjm_agent",
            "commit_sha": "abc1234567",
            "diff_ref": "main...feature",
            "files_changed": ["agents/pjm_agent/service/agent.py"],
            "branch": "feature/qa",
            "mr_iid": 12,
            "gitlab_project_id": 34,
            "wp_id": 99,
        },
    )

    envelope = QAAcceptanceRequestACL().from_code_committed(event)
    request = envelope.request

    assert request.agent_name == "pjm_agent"
    assert request.level == "all"
    assert request.commit_sha == "abc1234567"
    assert request.diff_ref == "main...feature"
    assert request.files_changed == ["agents/pjm_agent/service/agent.py"]
    assert request.branch == "feature/qa"
    assert request.mr_iid == 12
    assert request.gitlab_project_id == 34
    assert request.trigger == "event"
    assert request.requested_by == "code.committed"
    assert envelope.gitlab.mr_iid == 12
    assert envelope.openproject.work_package_id == 99


def test_run_requested_event_translates_to_qa_run_request() -> None:
    event = Event.create(
        event_type=EventTypes.QA_RUN_REQUESTED,
        source_agent="dev-agent",
        payload={
            "agent_name": "dev_agent",
            "level": "l0",
            "commit_sha": "def1234567",
            "files_changed": ["agents/dev_agent/service/agent.py"],
            "mr_iid": 22,
            "gitlab_project_id": 44,
            "requested_by": "dev-agent",
            "reason": "MR created",
            "work_package_id": 123,
        },
    )

    envelope = QAAcceptanceRequestACL().from_run_requested(event)
    request = envelope.request

    assert request.agent_name == "dev_agent"
    assert request.level == "l0"
    assert request.commit_sha == "def1234567"
    assert request.files_changed == ["agents/dev_agent/service/agent.py"]
    assert request.mr_iid == 22
    assert request.gitlab_project_id == 44
    assert request.trigger == "event"
    assert request.requested_by == "dev-agent"
    assert request.reason == "MR created"
    assert envelope.gitlab.gitlab_project_id == 44
    assert envelope.openproject.work_package_id == 123


def test_gitlab_merge_request_context_is_immutable() -> None:
    context = GitLabMergeRequestContext(mr_iid=1, gitlab_project_id=2)

    with pytest.raises(AttributeError):
        context.mr_iid = 3  # type: ignore[misc]


def test_openproject_work_package_context_accepts_optional_payload_ids() -> None:
    assert OpenProjectWorkPackageContext.from_event_payload({}).work_package_id is None
    assert (
        OpenProjectWorkPackageContext.from_event_payload({"wp_id": "123"}).work_package_id
        == 123
    )
    assert (
        OpenProjectWorkPackageContext.from_event_payload(
            {"work_package_id": 456}
        ).work_package_id
        == 456
    )
