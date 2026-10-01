from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.capabilities.evolution.app import release_routes
from shared.capabilities.evolution.core.release_use_cases import SkillReleaseUseCase
from shared.config import settings
from shared.evolution.release_contract import SkillReleaseCommand, sign_command
from shared.middleware.error_handler import http_exception_handler

_INTERNAL_KEY = "receiver-internal-test-key"
_SIGNING_KEY = "release-command-signing-test-key-long-enough"


class _Store:
    def __init__(self) -> None:
        self.apply_calls: list[SkillReleaseCommand] = []
        self.get_command_calls: list[tuple[str, dict[str, object]]] = []

    async def apply(self, command: SkillReleaseCommand) -> dict[str, str]:
        self.apply_calls.append(command)
        return {"deployment_id": command.deployment_id, "status": "accepted"}

    async def get(self, deployment_id: str) -> dict[str, str] | None:
        if deployment_id == "known-deployment":
            return {"deployment_id": deployment_id, "status": "applied"}
        return None

    async def get_command(
        self,
        command_id: str,
        *,
        skill_id: str | None = None,
        baseline_version: int | None = None,
        candidate_version: int | None = None,
    ) -> dict[str, str] | None:
        self.get_command_calls.append((command_id, {
            "skill_id": skill_id,
            "baseline_version": baseline_version,
            "candidate_version": candidate_version,
        }))
        if command_id == "known-command":
            return {"command_id": command_id, "status": "applied"}
        return None

    async def get_skill_config(self, skill_id: str, version: str) -> None:
        return None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "internal_service_key", _INTERNAL_KEY)
    monkeypatch.setattr(settings, "evolution_deployment_signing_key", SecretStr(_SIGNING_KEY))
    app = FastAPI()
    app.include_router(release_routes.router)
    store = _Store()
    app.state.receiver_store = store

    async def use_case_override():
        yield SkillReleaseUseCase(
            store, settings.evolution_deployment_signing_key.get_secret_value()
        )

    app.dependency_overrides[release_routes.get_release_use_case] = use_case_override
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    with TestClient(app) as test_client:
        yield test_client


def _command(*, expires_at: datetime | None = None) -> SkillReleaseCommand:
    return SkillReleaseCommand(
        command_id="command-1",
        deployment_id="deployment-1",
        company_id="company-1",
        proposal_id="proposal-1",
        evaluation_report_id="report-1",
        evaluation_hash="a" * 64,
        skill_id="skill-1",
        agent_id="agent-1",
        baseline_version=1,
        candidate_version=2,
        baseline_config_hash="b" * 64,
        candidate_config_hash="c" * 64,
        action="shadow",
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=5),
    )


def _headers(command: SkillReleaseCommand, *, signature: str | None = None) -> dict[str, str]:
    return {
        "X-Internal-Key": _INTERNAL_KEY,
        "X-Evolution-Signature": signature or sign_command(command, _SIGNING_KEY),
    }


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["message"]
    assert response.headers["X-Error-Code"] == code


def test_release_routes_require_internal_key(client: TestClient) -> None:
    response = client.get("/api/v1/evolution/skill-releases/known-deployment")
    _assert_error(response, 401, "internal_auth.unauthorized")

    response = client.get(
        "/api/v1/evolution/skill-releases/known-deployment",
        headers={"X-Internal-Key": "wrong"},
    )
    _assert_error(response, 401, "internal_auth.unauthorized")


def test_valid_signed_release_command_is_accepted(client: TestClient) -> None:
    command = _command()
    response = client.post(
        "/api/v1/evolution/skill-releases",
        json=command.model_dump(mode="json"),
        headers=_headers(command),
    )
    assert response.status_code == 200
    assert response.json() == {"deployment_id": "deployment-1", "status": "accepted"}


@pytest.mark.parametrize(
    ("signature", "expiry_offset", "expected_code"),
    [
        ("invalid", 5, "evolution.evolution_command_signature_invalid"),
        (None, -5, "evolution.evolution_command_expired"),
    ],
)
def test_invalid_or_expired_release_command_has_error_envelope(
    client: TestClient,
    signature: str | None,
    expiry_offset: int,
    expected_code: str,
) -> None:
    command = _command(expires_at=datetime.now(UTC) + timedelta(minutes=expiry_offset))
    response = client.post(
        "/api/v1/evolution/skill-releases",
        json=command.model_dump(mode="json"),
        headers=_headers(command, signature=signature),
    )
    _assert_error(response, 401, expected_code)


def test_missing_signing_key_fails_with_error_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "evolution_deployment_signing_key", SecretStr(""))
    command = _command()
    response = client.post(
        "/api/v1/evolution/skill-releases",
        json=command.model_dump(mode="json"),
        headers=_headers(command),
    )
    _assert_error(response, 401, "evolution.evolution_deployment_signing_key_required")


def test_receipt_lookup_returns_payload_or_structured_not_found(client: TestClient) -> None:
    found = client.get(
        "/api/v1/evolution/skill-releases/known-deployment",
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    assert found.status_code == 200
    assert found.json() == {"deployment_id": "known-deployment", "status": "applied"}

    missing = client.get(
        "/api/v1/evolution/skill-releases/missing",
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    _assert_error(missing, 404, "evolution.skill_release_not_found")


def test_command_receipt_forwards_complete_version_fence_without_apply(client: TestClient) -> None:
    response = client.get(
        "/api/v1/evolution/skill-release-commands/known-command",
        params={"skill_id": "skill-1", "baseline_version": 4, "candidate_version": 5},
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    assert response.status_code == 200
    assert response.json() == {"command_id": "known-command", "status": "applied"}
    store = client.app.state.receiver_store
    assert store.get_command_calls == [(
        "known-command",
        {"skill_id": "skill-1", "baseline_version": 4, "candidate_version": 5},
    )]
    assert store.apply_calls == []


def test_command_receipt_rejects_partial_version_fence(client: TestClient) -> None:
    response = client.get(
        "/api/v1/evolution/skill-release-commands/known-command",
        params={"skill_id": "skill-1", "baseline_version": 4},
        headers={"X-Internal-Key": _INTERNAL_KEY},
    )
    _assert_error(response, 422, "evolution.incomplete_release_lookup")
    assert client.app.state.receiver_store.get_command_calls == []
    assert client.app.state.receiver_store.apply_calls == []
