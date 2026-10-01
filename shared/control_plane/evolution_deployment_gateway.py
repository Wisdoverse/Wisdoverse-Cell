"""Authenticated bounded release client; the owning runtime applies changes."""

from typing import Any

import httpx

from shared.config import settings
from shared.evolution.release_contract import SkillReleaseCommand, canonical_hash, sign_command


class HttpEvolutionDeploymentGateway:
    async def lookup(self, command: SkillReleaseCommand) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(
                settings.evolution_runtime_url.rstrip("/")
                + f"/api/v1/evolution/skill-release-commands/{command.command_id}",
                headers={"X-Internal-Key": settings.internal_service_key},
                params={
                    "skill_id": command.skill_id,
                    "baseline_version": command.baseline_version,
                    "candidate_version": command.candidate_version,
                },
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            value = response.json()
        if (
            not isinstance(value, dict)
            or value.get("command_id") != command.command_id
            or value.get("deployment_id") != command.deployment_id
            or value.get("payload_hash") != canonical_hash(command.model_dump(mode="json"))
            or not isinstance(value.get("response"), dict)
        ):
            raise ValueError("invalid_evolution_reconciliation")
        return dict(value["response"])

    async def apply(self, command: SkillReleaseCommand) -> dict[str, Any]:
        signature = sign_command(
            command, settings.evolution_deployment_signing_key.get_secret_value()
        )
        headers = {
            "X-Internal-Key": settings.internal_service_key,
            "X-Evolution-Signature": signature,
            "Idempotency-Key": command.command_id,
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.post(
                settings.evolution_runtime_url.rstrip("/") + "/api/v1/evolution/skill-releases",
                json=command.model_dump(mode="json"),
                headers=headers,
            )
            response.raise_for_status()
            value = response.json()
        if not isinstance(value, dict) or value.get("deployment_id") != command.deployment_id:
            raise ValueError("invalid_evolution_acknowledgement")
        return value
