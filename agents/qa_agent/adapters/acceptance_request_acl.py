"""Anti-corruption layer for inbound QA acceptance requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.schemas.event import Event
from shared.schemas.event_payloads import CodeCommittedPayload, QARunRequestedPayload

from ..models.schemas import QARunRequest


@dataclass(frozen=True, slots=True)
class GitLabMergeRequestContext:
    """GitLab merge-request context translated from an inbound event."""

    mr_iid: int | None
    gitlab_project_id: int | None
    commit_sha: str | None = None
    diff_ref: str | None = None
    branch: str | None = None
    files_changed: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_code_committed(
        cls,
        payload: CodeCommittedPayload,
    ) -> GitLabMergeRequestContext:
        """Translate the published code-committed payload to QA MR context."""
        return cls(
            mr_iid=payload.mr_iid,
            gitlab_project_id=payload.gitlab_project_id,
            commit_sha=payload.commit_sha,
            diff_ref=payload.diff_ref,
            branch=payload.branch,
            files_changed=tuple(payload.files_changed),
        )

    @classmethod
    def from_run_requested(
        cls,
        payload: QARunRequestedPayload,
    ) -> GitLabMergeRequestContext:
        """Translate the published QA-run request payload to QA MR context."""
        return cls(
            mr_iid=payload.mr_iid,
            gitlab_project_id=payload.gitlab_project_id,
            commit_sha=payload.commit_sha,
            files_changed=tuple(payload.files_changed),
        )


@dataclass(frozen=True, slots=True)
class OpenProjectWorkPackageContext:
    """Optional OpenProject work-package context carried by upstream events."""

    work_package_id: int | None = None

    @classmethod
    def from_event_payload(
        cls,
        payload: dict[str, Any],
    ) -> OpenProjectWorkPackageContext:
        """Translate optional work-package ids without changing the event schema."""
        raw_value = payload.get("work_package_id", payload.get("wp_id"))
        if raw_value is None:
            return cls()
        return cls(work_package_id=int(raw_value))


@dataclass(frozen=True, slots=True)
class QAAcceptanceRequestEnvelope:
    """QA-local request plus translated source-system context."""

    request: QARunRequest
    gitlab: GitLabMergeRequestContext
    openproject: OpenProjectWorkPackageContext


class QAAcceptanceRequestACL:
    """Translate external event payloads into QA-local acceptance requests."""

    def from_code_committed(self, event: Event) -> QAAcceptanceRequestEnvelope:
        """Build a QA run request from a code.committed integration event."""
        payload = CodeCommittedPayload.model_validate(event.payload)
        mr_context = GitLabMergeRequestContext.from_code_committed(payload)
        op_context = OpenProjectWorkPackageContext.from_event_payload(event.payload)
        return QAAcceptanceRequestEnvelope(
            request=QARunRequest(
                agent_name=payload.agent_name,
                level="all",
                commit_sha=mr_context.commit_sha,
                diff_ref=mr_context.diff_ref,
                files_changed=list(mr_context.files_changed),
                branch=mr_context.branch,
                mr_iid=mr_context.mr_iid,
                gitlab_project_id=mr_context.gitlab_project_id,
                trigger="event",
                requested_by="code.committed",
            ),
            gitlab=mr_context,
            openproject=op_context,
        )

    def from_run_requested(self, event: Event) -> QAAcceptanceRequestEnvelope:
        """Build a QA run request from a qa.run-requested integration event."""
        payload = QARunRequestedPayload.model_validate(event.payload)
        mr_context = GitLabMergeRequestContext.from_run_requested(payload)
        op_context = OpenProjectWorkPackageContext.from_event_payload(event.payload)
        return QAAcceptanceRequestEnvelope(
            request=QARunRequest(
                agent_name=payload.agent_name,
                level=payload.level,
                commit_sha=mr_context.commit_sha,
                files_changed=list(mr_context.files_changed),
                mr_iid=mr_context.mr_iid,
                gitlab_project_id=mr_context.gitlab_project_id,
                trigger="event",
                requested_by=payload.requested_by,
                reason=payload.reason,
            ),
            gitlab=mr_context,
            openproject=op_context,
        )


__all__ = [
    "GitLabMergeRequestContext",
    "OpenProjectWorkPackageContext",
    "QAAcceptanceRequestEnvelope",
    "QAAcceptanceRequestACL",
]
