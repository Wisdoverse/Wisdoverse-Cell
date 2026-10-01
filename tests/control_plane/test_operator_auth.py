"""Tests for server-owned operator identities and company/action scopes."""

import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from shared.control_plane.operator_auth import (
    OperatorPrincipal,
    authorize_control_plane_request,
    require_operator,
)


def request(
    *, method="GET", path="/api/v1/control-plane/companies/cmp_one", token="", actor="", body=b""
):
    headers = []
    if token:
        headers.append((b"x-control-plane-operator-token", token.encode()))
    if actor:
        headers.append((b"x-actor-id", actor.encode()))
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "server": ("test", 80),
        "client": ("test", 1234),
        "root_path": "",
        "path_params": {"company_id": "cmp_one"} if "/companies/" in path else {},
    }
    return Request(scope, receive)


def configure(monkeypatch, *, operators="", app_env="development", company="cmp_one"):
    monkeypatch.setattr(
        "shared.control_plane.operator_auth.settings",
        SimpleNamespace(
            control_plane_operators_json=operators,
            app_env=app_env,
            control_plane_company_id=company,
        ),
    )


@pytest.mark.public
def test_production_without_operator_configuration_fails_closed(monkeypatch):
    configure(monkeypatch, app_env="production")
    with pytest.raises(HTTPException) as error:
        asyncio.run(require_operator(request()))
    assert error.value.status_code == 503
    assert error.value.detail == "operator_auth_not_configured"


@pytest.mark.public
def test_configured_operator_rejects_invalid_token(monkeypatch):
    entry = {
        "actor_id": "operator:release",
        "token_sha256": hashlib.sha256(b"correct-test-token").hexdigest(),
        "companies": ["cmp_one"],
        "scopes": ["control-plane:read"],
    }
    configure(monkeypatch, operators=json.dumps([entry]))
    with pytest.raises(HTTPException) as error:
        asyncio.run(require_operator(request(token="wrong-test-token")))
    assert error.value.status_code == 401
    assert error.value.detail == "operator_token_invalid"


@pytest.mark.public
def test_configured_token_maps_to_server_owned_principal_and_hash(monkeypatch):
    token = "local-test-token-only"
    digest = hashlib.sha256(token.encode()).hexdigest()
    entry = {
        "actor_id": "operator:release",
        "token_sha256": digest,
        "companies": ["cmp_one"],
        "scopes": ["control-plane:read", "work:execute"],
        "role_ids": ["release-operator"],
    }
    configure(monkeypatch, operators=json.dumps([entry]))
    principal = asyncio.run(require_operator(request(token=token, actor="spoofed:actor")))
    assert principal == OperatorPrincipal(
        "operator:release",
        frozenset({"cmp_one"}),
        frozenset({"control-plane:read", "work:execute"}),
        frozenset({"release-operator"}),
    )
    assert token not in principal.actor_id
    assert digest == entry["token_sha256"]


@pytest.mark.public
def test_read_scope_cannot_execute_or_access_another_company():
    principal = OperatorPrincipal(
        "operator:reader", frozenset({"cmp_one"}), frozenset({"control-plane:read"})
    )
    with pytest.raises(HTTPException) as execute_error:
        principal.require("work:execute", "cmp_one")
    assert execute_error.value.status_code == 403
    with pytest.raises(HTTPException) as company_error:
        principal.require("control-plane:read", "cmp_other")
    assert company_error.value.status_code == 403


@pytest.mark.public
def test_caller_actor_header_cannot_grant_execution_scope(monkeypatch):
    token = "read-only-test-token"
    entry = {
        "actor_id": "operator:reader",
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "companies": ["cmp_one"],
        "scopes": ["control-plane:read"],
    }
    configure(monkeypatch, operators=json.dumps([entry]))
    req = request(
        method="POST",
        path="/api/v1/control-plane/agents/agent_one/run",
        token=token,
        actor="operator:admin",
        body=b'{"company_id":"cmp_one","actor_id":"operator:admin"}',
    )

    async def authorize():
        await anext(authorize_control_plane_request(req))

    with pytest.raises(HTTPException) as error:
        asyncio.run(authorize())
    assert error.value.status_code == 403
    principal = asyncio.run(require_operator(req))
    assert principal.actor_id == "operator:reader"
