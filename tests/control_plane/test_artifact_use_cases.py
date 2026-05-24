"""Artifact use-case tests."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.artifact_use_cases import create_artifact_with_audit
from shared.control_plane.domain.artifact import InvalidArtifactError
from shared.control_plane.models import Artifact, ArtifactType, CompanyContext
from shared.control_plane.store_factory import ControlPlaneStores
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_artifact_creation_uses_domain_policy_and_audit(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company = await stores.companies.create_company(
        CompanyContext(company_id="cmp_artifact_domain", name="Artifact Domain Test")
    )

    artifact = await create_artifact_with_audit(
        stores.artifacts,
        Artifact(
            company_id=company.company_id,
            artifact_type=ArtifactType.REPORT,
            title="  Evidence report  ",
            uri="  urn:wisdoverse-cell:artifact:evidence  ",
            content_hash="sha256:test",
            metadata={"source": "operator"},
        ),
        created_by="human:operator",
    )
    audits = await stores.audit_events.list_audit_events(
        company_id=company.company_id,
        target_type="artifact",
    )

    assert artifact.title == "Evidence report"
    assert artifact.uri == "urn:wisdoverse-cell:artifact:evidence"
    assert artifact.artifact_type == ArtifactType.REPORT.value
    assert len(audits) == 1
    assert audits[0].action == EventTypes.ARTIFACT_CREATED
    assert audits[0].actor_id == "human:operator"
    assert audits[0].detail["domain_event"] == "ArtifactCreated"
    assert audits[0].detail["artifact_type"] == ArtifactType.REPORT.value
    assert audits[0].detail["has_content_hash"] is True
    assert "Evidence report" not in str(audits[0].detail)
    assert "artifact:evidence" not in str(audits[0].detail)


@pytest.mark.asyncio
async def test_artifact_creation_rejects_missing_uri(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company = await stores.companies.create_company(
        CompanyContext(company_id="cmp_artifact_missing_uri", name="Artifact Domain Test")
    )

    with pytest.raises(InvalidArtifactError, match="uri_required"):
        await create_artifact_with_audit(
            stores.artifacts,
            Artifact(
                company_id=company.company_id,
                artifact_type=ArtifactType.REPORT,
                title="Evidence report",
                uri=" ",
            ),
            created_by="human:operator",
        )
