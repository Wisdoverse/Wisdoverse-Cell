"""Run a resumable synthetic operating-report first-success walkthrough.

Example::

    python scripts/first_success.py --base-url http://localhost:8000 \
      --company-id cmp_wisdoverse_cell --run-key report-demo \
      --checkpoint .artifacts/first-success-report-demo.json \
      --review-reason "Reviewed the linked synthetic sample report."

The fixture executor is invoked by the already-gated Control Plane local
process adapter. This CLI never enables adapters, changes server policy, or
approves execution. To run the separate deployed-agent workflow, use
``--workflow agent-http``; it reports the known service endpoints as pending
because the repository does not define a complete linked handoff contract.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

CONTROL_PLANE_PREFIX = "/api/v1/control-plane"
FIXTURE_PATH = Path(__file__).with_name("fixtures") / "operating_report.json"
ACTOR_ID = "first-success-cli"
AGENT_ID = "first-success-operating-report"
ALLOWLIST_KEY = "process:first-success-operating-report"
EXECUTOR_ACTION = "generate_operating_report"
AGENT_WORKFLOW_ENDPOINTS = (
    {
        "role": "Requirement Manager",
        "method": "POST",
        "path": "/api/v1/ingest/upload",
        "source": "agents/requirement_manager/api/ingest.py",
    },
    {
        "role": "Requirement Manager",
        "method": "POST",
        "path": "/api/v1/requirements/{requirement_id}/analyze",
        "source": "agents/requirement_manager/api/requirements.py",
    },
    {
        "role": "PJM",
        "method": "GET/POST",
        "path": "/api/v1/pm/decompose/{wp_id}[/retry|/approve|/reject]",
        "source": "agents/pjm_agent/api/decomposition.py",
    },
    {
        "role": "Dev",
        "method": "GET/POST",
        "path": "/api/v1/dev/tasks[/...|/{task_id}/retry|/approve|/cancel]",
        "source": "agents/dev_agent/api/dev.py",
    },
    {
        "role": "QA",
        "method": "POST",
        "path": "/api/v1/qa/run",
        "source": "agents/qa_agent/api/qa.py",
    },
)


class FirstSuccessError(RuntimeError):
    """Expected, safe-to-display first-success failure."""


class ResourceNotFound(FirstSuccessError):
    """The requested Control Plane resource does not exist."""


class JsonApi(Protocol):
    def get(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]: ...

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RunOptions:
    base_url: str
    company_id: str
    run_key: str
    checkpoint: Path
    review_reason: str | None = None
    workflow: str = "synthetic-report"
    runtime_urls: dict[str, str | None] | None = None


class ControlPlaneApi:
    """Small JSON HTTP client; response/error bodies are never printed."""

    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self.base_url = _validate_base_url(base_url).rstrip("/")
        self._headers = {"Accept": "application/json"}
        self._headers.update(headers or {})

    def get(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        return self._request("GET", path + query)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, body)

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self.base_url}{CONTROL_PLANE_PREFIX}{path}"
        data = (
            json.dumps(body, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if body
            else None
        )
        headers = dict(self._headers)
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise ResourceNotFound("Control Plane resource was not found.") from None
            raise FirstSuccessError(
                f"Control Plane request failed (HTTP {exc.code}); response details were redacted."
            ) from None
        except (URLError, TimeoutError, OSError):
            raise FirstSuccessError(
                "Control Plane request failed; connection details were redacted."
            ) from None
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise FirstSuccessError("Control Plane returned an invalid JSON response.") from None
        if not isinstance(result, dict):
            raise FirstSuccessError("Control Plane returned an unexpected response shape.")
        return result


def headers_from_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Build auth headers exclusively from environment variables."""

    environment_values: Mapping[str, str] = os.environ if environment is None else environment
    headers: dict[str, str] = {}
    internal_key = environment_values.get("INTERNAL_SERVICE_KEY", "").strip()
    operator_token = environment_values.get("CONTROL_PLANE_OPERATOR_TOKEN", "").strip()
    if internal_key:
        headers["X-Internal-Key"] = internal_key
    if operator_token:
        headers["X-Control-Plane-Operator-Token"] = operator_token
    return headers


def run_first_success(options: RunOptions, api: JsonApi | None = None) -> dict[str, Any]:
    """Run the synthetic fixture path or return honest agent-flow status."""

    if options.workflow == "agent-http":
        return agent_workflow_pending(
            options.base_url,
            runtime_urls=options.runtime_urls,
            headers=headers_from_environment(),
        )
    if options.workflow != "synthetic-report":
        raise FirstSuccessError("Unsupported first-success workflow.")
    if options.review_reason is not None and not options.review_reason.strip():
        raise FirstSuccessError("Review reason must contain non-whitespace text.")
    _validate_run_key(options.run_key)
    _validate_company_id(options.company_id)
    origin_fingerprint = _origin_fingerprint(options.base_url)
    checkpoint = _load_checkpoint(
        options.checkpoint,
        company_id=options.company_id,
        run_key=options.run_key,
        origin_fingerprint=origin_fingerprint,
    )
    checkpoint["_checkpoint_path"] = str(options.checkpoint)
    api = api or ControlPlaneApi(options.base_url, headers_from_environment())
    fixture = _load_fixture()
    started = time.perf_counter()

    company = _ensure_company(api, checkpoint, options.company_id)
    budget = _ensure_budget_policy(api, checkpoint, company)
    goal = _ensure_goal(api, checkpoint, company, options.run_key)
    agent = _ensure_agent(api, checkpoint, company, options.run_key, budget["budget_id"])
    work_item = _ensure_work_item(api, checkpoint, company, goal, agent, options.run_key)
    if not checkpoint["timings"].get("setup_time_seconds"):
        checkpoint["timings"]["setup_time_seconds"] = round(time.perf_counter() - started, 6)
    _save_checkpoint(options.checkpoint, checkpoint)

    run_started = time.perf_counter()
    run, artifact_id, output = _ensure_run_and_evidence(
        api, checkpoint, company, goal, agent, work_item, options.run_key, fixture
    )
    budget_usage = _ensure_budget_usage(
        api, checkpoint, company["company_id"], budget["budget_id"], run["run_id"]
    )
    if not checkpoint["timings"].get("output_time_seconds"):
        checkpoint["timings"]["output_time_seconds"] = round(time.perf_counter() - run_started, 6)
    checkpoint["run_id"] = run["run_id"]
    checkpoint["artifact_id"] = artifact_id
    checkpoint["status"] = "awaiting_explicit_review"
    _save_checkpoint(options.checkpoint, checkpoint)

    acceptance: dict[str, Any] | None = None
    closed = False
    if options.review_reason:
        if not options.review_reason.strip():
            raise FirstSuccessError("Review reason must contain non-whitespace text.")
        acceptance, closed = _review_and_close(
            api,
            checkpoint,
            work_item,
            artifact_id,
            options.review_reason.strip(),
            options.run_key,
        )

    checkpoint["status"] = "completed" if closed else "awaiting_explicit_review"
    checkpoint["accepted"] = bool(acceptance and acceptance.get("verdict") == "accepted")
    checkpoint["closed"] = closed
    _save_checkpoint(options.checkpoint, checkpoint)

    safe_output = _safe_operating_report(output)
    return {
        "status": checkpoint["status"],
        "workflow": "synthetic-report",
        "synthetic": True,
        "company_id": company["company_id"],
        "goal_id": goal["goal_id"],
        "agent_id": agent["agent_id"],
        "work_item_id": work_item["work_item_id"],
        "run_id": run["run_id"],
        "artifact_id": artifact_id,
        "budget_id": budget["budget_id"],
        "budget_usage_id": budget_usage["usage_id"],
        "budget_cost_usd": budget_usage["cost_usd"],
        "acceptance_id": acceptance.get("acceptance_id") if acceptance else None,
        "accepted": checkpoint["accepted"],
        "closed": closed,
        "timings": dict(checkpoint["timings"]),
        "operating_report": safe_output,
        "note": "All report metrics are synthetic sample values, not company results.",
    }


RUNTIME_NAMES = ("requirement_manager", "pjm", "dev", "qa")
FIXED_SOFTWARE_CASES = (
    {
        "case_id": "software-requirement-intake",
        "expectation": "requirement content is accepted and linked",
    },
    {
        "case_id": "software-planning-handoff",
        "expectation": "a requirement produces a linked work package",
    },
    {
        "case_id": "software-development-handoff",
        "expectation": "work package produces verifiable implementation evidence",
    },
    {
        "case_id": "software-qa-handoff",
        "expectation": "QA result references the same work and implementation",
    },
)


def _probe_runtime(name: str, base_url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Probe liveness/readiness and authenticated health detail only (read-only)."""
    origin = _validate_base_url(base_url)
    result: dict[str, Any] = {"runtime": name, "configured": True, "probes": {}}
    for label, path, auth in (
        ("liveness", "/health", False),
        ("readiness", "/health/ready", False),
        ("authenticated_readiness", "/health/ready/detail", True),
    ):
        request_headers = {"Accept": "application/json"}
        if auth:
            request_headers.update(headers)
        request = Request(f"{origin}{path}", headers=request_headers, method="GET")
        status: int | None = None
        body: dict[str, Any] = {}
        try:
            with urlopen(request, timeout=5) as response:
                status = response.status
                payload = response.read()
            decoded = json.loads(payload.decode("utf-8"))
            if isinstance(decoded, dict):
                body = decoded
        except HTTPError as exc:
            status = exc.code
        except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        result["probes"][label] = {
            "http_status": status,
            "ok": status is not None and 200 <= status < 300,
            "reported_status": body.get("status") if label != "authenticated_readiness" else None,
        }
    return result


def agent_workflow_pending(
    base_url: str,
    *,
    runtime_urls: dict[str, str | None] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Report fixed-case readiness and safe runtime probes, never workflow success."""

    _validate_base_url(base_url)
    urls = runtime_urls or {}
    probes = []
    for name in RUNTIME_NAMES:
        url = urls.get(name)
        if not url:
            probes.append({"runtime": name, "configured": False, "probes": {}})
        else:
            try:
                probes.append(_probe_runtime(name, url, headers or {}))
            except FirstSuccessError:
                probes.append(
                    {"runtime": name, "configured": True, "probes": {}, "url_valid": False}
                )
    return {
        "status": "pending",
        "workflow": "agent-http",
        "reason": (
            "The repository documents separate agent endpoints but no stable HTTP "
            "handoff contract that carries one accepted Requirement through PJM, "
            "Dev, and QA into a linked Control Plane artifact."
        ),
        "known_endpoints": list(AGENT_WORKFLOW_ENDPOINTS),
        "fixed_cases": list(FIXED_SOFTWARE_CASES),
        "runtime_probes": probes,
        "probe_scope": "read-only /health, /health/ready, and authenticated /health/ready/detail GETs",
        "completion_claimed": False,
        "next_contract_needed": (
            "Define and verify one company/work-item/run handoff across these services "
            "before automating the agent workflow."
        ),
    }


def run_fixture_executor(stdin: Any, stdout: Any, stderr: Any) -> int:
    """Read one runner request and emit a deterministic sample report as JSON."""

    try:
        request = json.load(stdin)
        fixture = request.get("input", {}).get("fixture")
        if not isinstance(fixture, dict) or fixture.get("synthetic") is not True:
            raise ValueError("fixture is not marked synthetic")
        metrics = fixture["metrics"]
        revenue = float(metrics["recognized_revenue_usd"])
        expense = float(metrics["operating_expense_usd"])
        report = {
            "synthetic": True,
            "report_type": "operating_report",
            "period": fixture["period"],
            "metrics": {
                "recognized_revenue_usd": revenue,
                "operating_expense_usd": expense,
                "net_operating_income_usd": round(revenue - expense, 2),
                "open_work_items": int(metrics["open_work_items"]),
                "at_risk_work_items": int(metrics["at_risk_work_items"]),
            },
            "metric_classification": "synthetic_sample",
            "notes": list(fixture.get("notes", [])),
        }
        response = {
            "schema_version": "1.0",
            "status": "succeeded",
            "summary": "Synthetic operating report generated by the local fixture executor.",
            "cost_usd": 0,
            "output": report,
            "artifact_references": [],
        }
        stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        stderr.write("invalid synthetic fixture input\n")
        return 2


def _ensure_company(api: JsonApi, checkpoint: dict[str, Any], company_id: str) -> dict[str, Any]:
    if checkpoint.get("company_step_complete"):
        company = api.get(f"/companies/{company_id}")
        _require_id(company, "company_id", company_id)
        return company
    try:
        company = api.get(f"/companies/{company_id}")
    except ResourceNotFound:
        try:
            company = api.post(
                "/companies",
                {
                    "company_id": company_id,
                    "name": "Wisdoverse Cell Synthetic First Success",
                    "mission": "Verify a synthetic operating-report workflow.",
                    "created_by": ACTOR_ID,
                    "metadata": {"synthetic_first_success": True},
                },
            )
        except FirstSuccessError:
            # A concurrent/resumed invocation may have created it after GET.
            company = api.get(f"/companies/{company_id}")
    _require_id(company, "company_id", company_id)
    checkpoint["company_id"] = company_id
    checkpoint["company_step_complete"] = True
    return company


def _ensure_budget_policy(
    api: JsonApi, checkpoint: dict[str, Any], company: dict[str, Any]
) -> dict[str, Any]:
    company_id = company["company_id"]
    budget_id = checkpoint.get("budget_id")
    policy: dict[str, Any] | None = None
    if budget_id:
        policy = api.get(f"/budgets/policies/{budget_id}", params={"company_id": company_id})
        _validate_company_budget(policy, company_id)
        return policy

    policy = _find_active_company_budget(api, company_id)
    if policy is None:
        try:
            policy = api.post(
                "/budgets/policies",
                {
                    "company_id": company_id,
                    "scope": "company",
                    "period": "total",
                    "limit_usd": 0.01,
                    "warning_threshold": 1.0,
                    "status": "active",
                    "created_by": ACTOR_ID,
                    "metadata": {
                        "purpose": "first_success_synthetic_executor",
                        "max_execution_cost_usd": 0,
                        "synthetic": True,
                    },
                },
            )
        except FirstSuccessError:
            # Another operator may have created the active policy between GET and POST.
            policy = _find_active_company_budget(api, company_id)
            if policy is None:
                raise
    _validate_company_budget(policy, company_id)
    budget_id = _require_text(policy.get("budget_id"), "budget_id")
    checkpoint["budget_id"] = budget_id
    _save_checkpoint_from_run(checkpoint)
    return policy


def _find_active_company_budget(api: JsonApi, company_id: str) -> dict[str, Any] | None:
    rows = cast(
        list[dict[str, Any]],
        api.get(
            "/budgets/policies",
            params={
                "company_id": company_id,
                "scope": "company",
                "status": "active",
                "limit": "100",
            },
        ).get("budget_policies", []),
    )
    policies = [
        row
        for row in rows
        if row.get("company_id") == company_id
        and row.get("scope") == "company"
        and row.get("status") == "active"
        and row.get("scope_id") is None
    ]
    return min(policies, key=lambda row: str(row.get("budget_id", ""))) if policies else None


def _validate_company_budget(policy: dict[str, Any], company_id: str) -> None:
    if (
        policy.get("company_id") != company_id
        or policy.get("scope") != "company"
        or policy.get("scope_id") is not None
        or policy.get("status") != "active"
    ):
        raise FirstSuccessError(
            "The linked budget policy is not an active company policy for this company."
        )


def _ensure_budget_usage(
    api: JsonApi,
    checkpoint: dict[str, Any],
    company_id: str,
    budget_id: str,
    run_id: str,
) -> dict[str, Any]:
    rows = cast(
        list[dict[str, Any]],
        api.get(
            "/budgets/usage",
            params={
                "company_id": company_id,
                "budget_id": budget_id,
                "run_id": run_id,
                "limit": "100",
            },
        ).get("usage", []),
    )
    usage = next(
        (
            row
            for row in rows
            if row.get("company_id") == company_id
            and row.get("budget_id") == budget_id
            and row.get("run_id") == run_id
        ),
        None,
    )
    if usage is None:
        raise FirstSuccessError("The run has no durable usage record linked to its budget.")
    if not _is_zero_cost(usage.get("cost_usd")):
        raise FirstSuccessError("The supposedly zero-cost fixture run recorded non-zero cost.")
    usage_id = _require_text(usage.get("usage_id"), "budget usage ID")
    prior_usage_id = checkpoint.get("budget_usage_id")
    if prior_usage_id and prior_usage_id != usage_id:
        raise FirstSuccessError("The budget usage record changed since the checkpoint was saved.")
    checkpoint["budget_usage_id"] = usage_id
    _save_checkpoint_from_run(checkpoint)
    return usage


def _ensure_goal(
    api: JsonApi,
    checkpoint: dict[str, Any],
    company: dict[str, Any],
    run_key: str,
) -> dict[str, Any]:
    company_id = company["company_id"]
    goal: dict[str, Any] | None = None
    if checkpoint.get("goal_id"):
        goal = api.get(f"/goals/{checkpoint['goal_id']}", params={"company_id": company_id})
        _require_id(goal, "goal_id", checkpoint["goal_id"])
        return goal
    rows = api.get(
        "/goals",
        params={
            "company_id": company_id,
            "search": f"Synthetic operating report {run_key}",
            "limit": "100",
        },
    ).get("goals", [])
    for row in rows:
        if (row.get("metadata") or {}).get("first_success_run_key") == run_key:
            goal = row
            break
    if goal is None:
        goal = api.post(
            "/goals",
            {
                "company_id": company_id,
                "title": f"Synthetic operating report {run_key}",
                "description": "Sample-only first-success walkthrough; no live metrics.",
                "status": "active",
                "success_metric": "A reviewed synthetic operating report is accepted.",
                "tags": ["synthetic", "first-success"],
                "created_by": ACTOR_ID,
                "metadata": {
                    "first_success_run_key": run_key,
                    "synthetic": True,
                    "metric_classification": "synthetic_sample",
                },
            },
        )
    goal_id = _require_text(goal.get("goal_id"), "goal_id")
    checkpoint["goal_id"] = goal_id
    return goal


def _ensure_agent(
    api: JsonApi,
    checkpoint: dict[str, Any],
    company: dict[str, Any],
    run_key: str,
    budget_id: str,
) -> dict[str, Any]:
    company_id = company["company_id"]
    if checkpoint.get("agent_id"):
        agent = api.get(f"/agents/{AGENT_ID}", params={"company_id": company_id})
        _validate_fixture_agent(agent, budget_id)
        return agent
    try:
        agent = api.get(f"/agents/{AGENT_ID}", params={"company_id": company_id})
    except ResourceNotFound:
        agent = api.post(
            "/agents",
            {
                "company_id": company_id,
                "agent_id": AGENT_ID,
                "display_name": "Synthetic Operating Report Fixture Executor",
                "agent_kind": "system_worker",
                "interaction_mode": "internal",
                "role": "reporter",
                "title": "Synthetic operating report",
                "domain": "operations",
                "adapter_type": "process",
                "adapter_config": _fixture_adapter_config(),
                "budget_policy_id": budget_id,
                "capabilities": ["generate_synthetic_operating_report"],
                "responsibilities": ["Produce fixture-only sample metrics."],
                "permissions": [
                    "work.execute",
                    "adapter:process",
                    f"tool:{EXECUTOR_ACTION}",
                ],
                "status": "active",
                "created_by": ACTOR_ID,
                "metadata": {
                    "first_success_run_key": run_key,
                    "synthetic": True,
                    "cost_ceiling_usd": 0,
                },
            },
        )
    _validate_fixture_agent(agent, budget_id)
    checkpoint["agent_id"] = AGENT_ID
    return agent


def _ensure_work_item(
    api: JsonApi,
    checkpoint: dict[str, Any],
    company: dict[str, Any],
    goal: dict[str, Any],
    agent: dict[str, Any],
    run_key: str,
) -> dict[str, Any]:
    company_id = company["company_id"]
    work_item: dict[str, Any] | None = None
    if checkpoint.get("work_item_id"):
        work_item = api.get(
            f"/work-items/{checkpoint['work_item_id']}", params={"company_id": company_id}
        )
        _require_id(work_item, "work_item_id", checkpoint["work_item_id"])
        return work_item
    external_ref = f"first-success:{run_key}"
    rows = api.get(
        "/work-items",
        params={
            "company_id": company_id,
            "search": f"Synthetic operating report {run_key}",
            "limit": "100",
        },
    ).get("work_items", [])
    for row in rows:
        if row.get("external_ref") == external_ref:
            work_item = row
            break
    if work_item is None:
        work_item = api.post(
            "/work-items",
            {
                "company_id": company_id,
                "title": f"Synthetic operating report {run_key}",
                "description": "Execute the sample report fixture and return its linked run evidence.",
                "status": "queued",
                "priority": "medium",
                "goal_id": goal["goal_id"],
                "owner_agent_id": agent["agent_id"],
                "source": "first_success_synthetic_fixture",
                "external_ref": external_ref,
                "approval_required": False,
                "created_by": ACTOR_ID,
                "metadata": {
                    "first_success_run_key": run_key,
                    "synthetic": True,
                    "metric_classification": "synthetic_sample",
                },
            },
        )
    work_item_id = _require_text(work_item.get("work_item_id"), "work_item_id")
    checkpoint["work_item_id"] = work_item_id
    return work_item


def _ensure_run_and_evidence(
    api: JsonApi,
    checkpoint: dict[str, Any],
    company: dict[str, Any],
    goal: dict[str, Any],
    agent: dict[str, Any],
    work_item: dict[str, Any],
    run_key: str,
    fixture: dict[str, Any],
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    company_id = company["company_id"]
    work_item_id = work_item["work_item_id"]
    run: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    if checkpoint.get("run_id"):
        run = api.get(f"/runs/{checkpoint['run_id']}")
    else:
        run = _find_prior_run(api, company_id, work_item_id, run_key)

    if run is None:
        response = api.post(
            f"/work-items/{work_item_id}/run",
            {
                "company_id": company_id,
                "agent_id": agent["agent_id"],
                "actor_id": ACTOR_ID,
                "idempotency_key": f"first-success:{run_key}:run",
                "input": {"first_success_run_key": run_key, "fixture": fixture},
            },
        )
        run = response.get("run")
        output = response.get("output")
        if not isinstance(run, dict):
            raise FirstSuccessError("Work execution returned no run record.")
        if run.get("status") != "succeeded":
            raise FirstSuccessError(
                "The fixture execution did not succeed; no acceptance was attempted."
            )
        checkpoint["run_id"] = _require_text(run.get("run_id"), "run_id")
        checkpoint["artifact_id"] = response.get("evidence_artifact_id")
        _save_checkpoint_from_run(checkpoint)
    else:
        if run.get("status") != "succeeded":
            raise FirstSuccessError(
                "A prior run is incomplete or failed; inspect it before any retry."
            )
        output = _output_from_run(run)

    run_id = _require_text(run.get("run_id"), "run_id")
    if output is None:
        output = _output_from_run(run)
    _validate_executor_output(output)
    artifact_id = checkpoint.get("artifact_id")
    artifact: dict[str, Any] | None
    if artifact_id:
        artifact = api.get(f"/artifacts/{artifact_id}", params={"company_id": company_id})
    else:
        artifact = _find_run_artifact(api, company_id, work_item_id, run_id)
    if artifact is None:
        # Successful run endpoint should provide this ID. Missing proof is a hard stop.
        raise FirstSuccessError("The successful run has no linked evidence artifact.")
    _validate_artifact(artifact, company_id, work_item_id, run_id)
    artifact_id = _require_text(artifact.get("artifact_id"), "artifact_id")
    checkpoint["run_id"] = run_id
    checkpoint["artifact_id"] = artifact_id
    checkpoint["goal_id"] = goal["goal_id"]
    _save_checkpoint_from_run(checkpoint)
    return run, artifact_id, output


def _find_prior_run(
    api: JsonApi, company_id: str, work_item_id: str, run_key: str
) -> dict[str, Any] | None:
    response = api.get(
        "/runs",
        params={"company_id": company_id, "work_item_id": work_item_id, "limit": "100"},
    )
    rows = response.get("runs", [])
    matching: list[dict[str, Any]] = []
    for row in rows:
        payload = (row.get("input_event") or {}).get("payload") or {}
        input_value = payload.get("input") or {}
        if input_value.get("first_success_run_key") == run_key:
            matching.append(row)
    if not matching:
        return None
    matching.sort(key=lambda row: str(row.get("started_at", "")), reverse=True)
    return matching[0]


def _find_run_artifact(
    api: JsonApi, company_id: str, work_item_id: str, run_id: str
) -> dict[str, Any] | None:
    rows = cast(
        list[dict[str, Any]],
        api.get(
            "/artifacts",
            params={
                "company_id": company_id,
                "run_id": run_id,
                "work_item_id": work_item_id,
                "limit": "100",
            },
        ).get("artifacts", []),
    )
    for row in rows:
        if row.get("run_id") == run_id and row.get("work_item_id") == work_item_id:
            return row
    return None


def _review_and_close(
    api: JsonApi,
    checkpoint: dict[str, Any],
    work_item: dict[str, Any],
    artifact_id: str,
    reason: str,
    run_key: str,
) -> tuple[dict[str, Any], bool]:
    company_id = checkpoint["company_id"]
    work_item_id = checkpoint["work_item_id"]
    current = api.get(f"/work-items/{work_item_id}", params={"company_id": company_id})
    metadata = current.get("metadata") or {}
    accepted_artifact = metadata.get("accepted_artifact_id")
    acceptance: dict[str, Any] | None = None
    if accepted_artifact:
        if accepted_artifact != artifact_id:
            raise FirstSuccessError("A different artifact is already accepted for this work item.")
        acceptance = {
            "acceptance_id": metadata.get("acceptance_id"),
            "artifact_id": artifact_id,
            "verdict": "accepted",
        }
    else:
        response = api.post(
            f"/work-items/{work_item_id}/accept",
            {
                "company_id": company_id,
                "artifact_id": artifact_id,
                "actor_id": ACTOR_ID,
                "verdict": "accepted",
                "reason": reason,
            },
        )
        acceptance = response.get("acceptance")
        if not isinstance(acceptance, dict) or acceptance.get("verdict") != "accepted":
            raise FirstSuccessError("Artifact review was not accepted; the work item remains open.")
        checkpoint["acceptance_id"] = acceptance.get("acceptance_id")
        _save_checkpoint_from_run(checkpoint)

    if current.get("status") == "completed":
        return acceptance, True
    if not (acceptance and acceptance.get("verdict") == "accepted"):
        return acceptance or {}, False
    api.post(
        f"/work-items/{work_item_id}/close",
        {
            "company_id": company_id,
            "status": "completed",
            "actor_id": ACTOR_ID,
            "reason": f"Explicit review completed for synthetic first-success run {run_key}.",
        },
    )
    checkpoint["acceptance_id"] = acceptance.get("acceptance_id")
    _save_checkpoint_from_run(checkpoint)
    return acceptance, True


def _fixture_adapter_config() -> dict[str, Any]:
    return {
        "action": EXECUTOR_ACTION,
        "allowlist_key": ALLOWLIST_KEY,
        "contract_version": "1.0",
        "command": [sys.executable, str(Path(__file__).resolve()), "--fixture-executor"],
        "max_cost_usd": 0,
        "timeout_sec": 30,
    }


def _validate_fixture_agent(agent: dict[str, Any], budget_id: str) -> None:
    config = agent.get("adapter_config") or {}
    required_permissions = {"work.execute", "adapter:process", f"tool:{EXECUTOR_ACTION}"}
    if (
        agent.get("agent_id") != AGENT_ID
        or agent.get("adapter_type") != "process"
        or agent.get("status") != "active"
        or config.get("allowlist_key") != ALLOWLIST_KEY
        or config.get("action") != EXECUTOR_ACTION
        or config.get("contract_version") != "1.0"
        or agent.get("budget_policy_id") != budget_id
        or not _is_zero_cost(config.get("max_cost_usd"))
        or not required_permissions.issubset(set(agent.get("permissions") or []))
    ):
        raise FirstSuccessError(
            "The existing fixture role does not match the required gated zero-cost contract."
        )


def _validate_executor_output(output: dict[str, Any]) -> None:
    if output.get("adapter") != "process":
        raise FirstSuccessError("The run did not use the local process fixture executor.")
    if not _is_zero_cost(output.get("cost_usd")):
        raise FirstSuccessError("The local fixture executor did not report zero cost.")
    report = output.get("response")
    if not isinstance(report, dict):
        raise FirstSuccessError("The versioned local fixture response has no report output.")
    if (
        report.get("synthetic") is not True
        or report.get("metric_classification") != "synthetic_sample"
    ):
        raise FirstSuccessError("The local executor output is not marked as synthetic sample data.")


def _safe_operating_report(output: dict[str, Any]) -> dict[str, Any]:
    report = output["response"]
    return {
        "period": str(report["period"]),
        "metric_classification": "synthetic_sample",
        "metrics": {
            key: report["metrics"][key]
            for key in (
                "recognized_revenue_usd",
                "operating_expense_usd",
                "net_operating_income_usd",
                "open_work_items",
                "at_risk_work_items",
            )
        },
    }


def _validate_artifact(
    artifact: dict[str, Any], company_id: str, work_item_id: str, run_id: str
) -> None:
    if (
        artifact.get("company_id") != company_id
        or artifact.get("work_item_id") != work_item_id
        or artifact.get("run_id") != run_id
        or not artifact.get("content_hash")
    ):
        raise FirstSuccessError("Run evidence is not linked to the expected company and work item.")


def _output_from_run(run: dict[str, Any]) -> dict[str, Any]:
    events = run.get("output_events") or []
    if events:
        payload = (events[-1].get("payload") or {}).get("output")
        if isinstance(payload, dict):
            return payload
    return {}


def _load_fixture() -> dict[str, Any]:
    try:
        value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise FirstSuccessError("The checked-in operating-report fixture is unavailable.") from None
    if not isinstance(value, dict):
        raise FirstSuccessError("The operating-report fixture has an invalid shape.")
    if value.get("synthetic") is not True:
        raise FirstSuccessError("The operating-report fixture must be marked synthetic.")
    return value


def _load_checkpoint(
    path: Path, *, company_id: str, run_key: str, origin_fingerprint: str
) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "company_id": company_id,
            "run_key": run_key,
            "origin_fingerprint": origin_fingerprint,
            "status": "started",
            "timings": {"setup_time_seconds": 0.0, "output_time_seconds": 0.0},
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise FirstSuccessError(
            "The checkpoint is unreadable; preserve it and inspect it manually."
        ) from None
    if not isinstance(value, dict):
        raise FirstSuccessError("The checkpoint has an invalid shape.")
    if (
        value.get("schema_version") != 1
        or value.get("company_id") != company_id
        or value.get("run_key") != run_key
        or value.get("origin_fingerprint") != origin_fingerprint
    ):
        raise FirstSuccessError(
            "Checkpoint company, run key, or API origin does not match this invocation."
        )
    value.setdefault("timings", {"setup_time_seconds": 0.0, "output_time_seconds": 0.0})
    return value


def _save_checkpoint(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    public_value = {key: item for key, item in value.items() if not key.startswith("_")}
    encoded = json.dumps(public_value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _save_checkpoint_from_run(checkpoint: dict[str, Any]) -> None:
    path_value = checkpoint.get("_checkpoint_path")
    if path_value:
        _save_checkpoint(Path(path_value), checkpoint)


def _validate_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise FirstSuccessError(
            "--base-url must be an HTTP(S) origin without credentials, path, query, or fragment."
        )
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise FirstSuccessError(
            "HTTP is allowed only for localhost; use HTTPS for remote services."
        )
    return value.strip().rstrip("/")


def _origin_fingerprint(base_url: str) -> str:
    parsed = urlsplit(_validate_base_url(base_url))
    origin = f"{parsed.scheme}://{parsed.netloc.lower()}"
    return hashlib.sha256(origin.encode()).hexdigest()


def _validate_run_key(value: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,47}", value):
        raise FirstSuccessError(
            "--run-key must use 1-48 lowercase letters, numbers, dots, _ or -. "
        )


def _validate_company_id(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", value):
        raise FirstSuccessError("--company-id contains unsupported characters.")


def _require_id(payload: dict[str, Any], field: str, expected: str) -> None:
    if payload.get(field) != expected:
        raise FirstSuccessError(f"Control Plane returned an unexpected {field}.")


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FirstSuccessError(f"Control Plane returned no {field}.")
    return value.strip()


def _is_zero_cost(value: Any) -> bool:
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Control Plane HTTP(S) origin")
    parser.add_argument(
        "--workflow",
        choices=("synthetic-report", "agent-http"),
        default="synthetic-report",
        help="Run the zero-cost local fixture or report the deployed-agent flow status.",
    )
    parser.add_argument(
        "--company-id", default=os.getenv("CONTROL_PLANE_COMPANY_ID", "cmp_first_success_demo")
    )
    parser.add_argument("--run-key", default="operating-report-demo")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path(".artifacts/first-success-operating-report.json"),
        help="Private checkpoint containing IDs only; reused to avoid duplicate work.",
    )
    parser.add_argument(
        "--review-reason",
        help="Explicitly accept the linked artifact and close the work item after review.",
    )
    parser.add_argument("--fixture-executor", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--requirement-manager-url", default=os.getenv("FIRST_SUCCESS_REQUIREMENT_MANAGER_URL")
    )
    parser.add_argument("--pjm-url", default=os.getenv("FIRST_SUCCESS_PJM_URL"))
    parser.add_argument("--dev-url", default=os.getenv("FIRST_SUCCESS_DEV_URL"))
    parser.add_argument("--qa-url", default=os.getenv("FIRST_SUCCESS_QA_URL"))
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--fixture-executor" in arguments:
        return run_fixture_executor(sys.stdin, sys.stdout, sys.stderr)
    args = _parser().parse_args(arguments)
    try:
        args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        lock_path = args.checkpoint.with_suffix(args.checkpoint.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a", encoding="utf-8") as lock_stream:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            options = RunOptions(
                base_url=args.base_url,
                company_id=args.company_id,
                run_key=args.run_key,
                checkpoint=args.checkpoint,
                review_reason=args.review_reason,
                workflow=args.workflow,
                runtime_urls={
                    "requirement_manager": args.requirement_manager_url,
                    "pjm": args.pjm_url,
                    "dev": args.dev_url,
                    "qa": args.qa_url,
                },
            )
            report = run_first_success(options)
    except BlockingIOError:
        print("Another first-success invocation holds this checkpoint lock.", file=sys.stderr)
        return 2
    except FirstSuccessError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
