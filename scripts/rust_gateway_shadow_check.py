#!/usr/bin/env python3
"""Rust gateway canary/shadow readiness check.

The script intentionally uses only the Python standard library so it can run in
developer shells, CI jobs, and production bastion sessions without installing
project dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_LEGACY_URL = "http://127.0.0.1:8080"
DEFAULT_RUST_URL = "http://127.0.0.1:18080"
EXPECTED_RUST_VERSION = "0.1.0-rust"
KNOWN_READY_STATUSES = {"ok", "degraded"}
REPORT_SCHEMA_VERSION = "rust-gateway-shadow/v1"
PROBE_USER_AGENT = "ProjectCell-RustGatewayShadowCheck/1.0"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("canary", "shadow"),
        nargs="?",
        default=os.getenv("RUST_GATEWAY_CHECK_MODE", "canary"),
    )
    args = parser.parse_args()

    legacy_url = normalize_url(os.getenv("LEGACY_GATEWAY_URL", DEFAULT_LEGACY_URL))
    rust_url = normalize_url(os.getenv("RUST_GATEWAY_URL", DEFAULT_RUST_URL))
    report_path = Path(
        os.getenv(
            "RUST_GATEWAY_SHADOW_REPORT",
            ".artifacts/rust-gateway-shadow-check.json",
        )
    )

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": args.mode,
        "started_at_unix": int(time.time()),
        "legacy_gateway_url": legacy_url,
        "rust_gateway_url": rust_url,
        "checks": [],
        "probes": {},
    }

    if args.mode == "shadow" and legacy_url == rust_url:
        add_check(
            report,
            "shadow.urls_differ",
            False,
            "LEGACY_GATEWAY_URL and RUST_GATEWAY_URL must point to different listeners",
        )
        return finish_report(report, report_path)

    rust_health = fetch_json(rust_url, "/health", "rust-health")
    rust_ready = fetch_json(rust_url, "/ready", "rust-ready")
    add_probe(report, "rust.health", rust_health)
    add_probe(report, "rust.ready", rust_ready)
    add_gateway_checks(report, "rust", rust_health, rust_ready, require_rust_version=True)

    if args.mode == "shadow":
        legacy_health = fetch_json(legacy_url, "/health", "legacy-health")
        legacy_ready = fetch_json(legacy_url, "/ready", "legacy-ready")
        add_probe(report, "legacy.health", legacy_health)
        add_probe(report, "legacy.ready", legacy_ready)
        add_gateway_checks(
            report,
            "legacy",
            legacy_health,
            legacy_ready,
            require_rust_version=False,
        )
        add_compare_checks(report, legacy_health, rust_health, legacy_ready, rust_ready)

    return finish_report(report, report_path)


def finish_report(report: dict[str, Any], report_path: Path) -> int:
    failed = [check for check in report["checks"] if not check["ok"]]
    report["ok"] = not failed
    report["failed_count"] = len(failed)
    report["finished_at_unix"] = int(time.time())

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    print(f"rust_gateway_{report['mode']}_report={report_path}")
    for check in report["checks"]:
        status = "ok" if check["ok"] else "fail"
        print(f"[{status}] {check['name']}: {check['detail']}")

    return 0 if report["ok"] else 1


def normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def fetch_json(base_url: str, path: str, label: str) -> dict[str, Any]:
    request_id = f"{label}-{int(time.time() * 1000)}"
    trace_id = f"trace-{request_id}"
    request = urllib.request.Request(
        f"{base_url}{path}",
        headers={
            "Accept": "application/json",
            "User-Agent": PROBE_USER_AGENT,
            "X-Request-ID": request_id,
            "X-Trace-ID": trace_id,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return {
                "ok": True,
                "url": f"{base_url}{path}",
                "status_code": response.status,
                "headers": headers,
                "body": parse_json(body),
                "raw_body": body,
                "request_id": request_id,
                "trace_id": trace_id,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return {
            "ok": False,
            "url": f"{base_url}{path}",
            "status_code": exc.code,
            "headers": headers,
            "body": parse_json(body),
            "raw_body": body,
            "request_id": request_id,
            "trace_id": trace_id,
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - report must capture all probe failures.
        return {
            "ok": False,
            "url": f"{base_url}{path}",
            "status_code": None,
            "headers": {},
            "body": None,
            "raw_body": "",
            "request_id": request_id,
            "trace_id": trace_id,
            "error": str(exc),
        }


def parse_json(body: str) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def add_probe(report: dict[str, Any], name: str, probe: dict[str, Any]) -> None:
    headers = probe.get("headers", {})
    body = probe.get("body")
    report["probes"][name] = {
        "url": probe.get("url"),
        "status_code": probe.get("status_code"),
        "headers": {
            key: headers.get(key)
            for key in ("content-type", "x-request-id", "x-trace-id")
            if headers.get(key) is not None
        },
        "body": body if isinstance(body, (dict, list, str, int, float, bool)) else None,
        "raw_body_snippet": (probe.get("raw_body") or "")[:2000],
        "request_id": probe.get("request_id"),
        "trace_id": probe.get("trace_id"),
        "error": probe.get("error"),
    }


def add_gateway_checks(
    report: dict[str, Any],
    prefix: str,
    health: dict[str, Any],
    ready: dict[str, Any],
    *,
    require_rust_version: bool,
) -> None:
    health_body = health.get("body") if isinstance(health.get("body"), dict) else {}
    ready_body = ready.get("body") if isinstance(ready.get("body"), dict) else {}
    ready_services = (
        ready_body.get("services") if isinstance(ready_body.get("services"), dict) else {}
    )

    add_check(
        report,
        f"{prefix}.health.http_200",
        health.get("status_code") == 200,
        f"{health.get('url')} returned {health.get('status_code')}",
    )
    add_check(
        report,
        f"{prefix}.health.status_ok",
        health_body.get("status") == "ok",
        f"status={health_body.get('status')!r}",
    )
    if require_rust_version:
        add_check(
            report,
            f"{prefix}.health.version",
            health_body.get("version") == EXPECTED_RUST_VERSION,
            f"version={health_body.get('version')!r}",
        )
        add_check(
            report,
            f"{prefix}.health.request_id_header",
            health.get("headers", {}).get("x-request-id") == health.get("request_id"),
            (
                f"expected={health.get('request_id')!r}, "
                f"actual={health.get('headers', {}).get('x-request-id')!r}"
            ),
        )
        add_check(
            report,
            f"{prefix}.health.trace_id_header",
            health.get("headers", {}).get("x-trace-id") == health.get("trace_id"),
            (
                f"expected={health.get('trace_id')!r}, "
                f"actual={health.get('headers', {}).get('x-trace-id')!r}"
            ),
        )

    add_check(
        report,
        f"{prefix}.ready.http_200",
        ready.get("status_code") == 200,
        f"{ready.get('url')} returned {ready.get('status_code')}",
    )
    add_check(
        report,
        f"{prefix}.ready.status_known",
        ready_body.get("status") in KNOWN_READY_STATUSES,
        f"status={ready_body.get('status')!r}",
    )
    add_check(
        report,
        f"{prefix}.ready.ai_service_reported",
        "ai_service" in ready_services,
        f"services={sorted(ready_services.keys())}",
    )


def add_compare_checks(
    report: dict[str, Any],
    legacy_health: dict[str, Any],
    rust_health: dict[str, Any],
    legacy_ready: dict[str, Any],
    rust_ready: dict[str, Any],
) -> None:
    legacy_health_body = (
        legacy_health.get("body") if isinstance(legacy_health.get("body"), dict) else {}
    )
    rust_health_body = (
        rust_health.get("body") if isinstance(rust_health.get("body"), dict) else {}
    )
    legacy_ready_body = (
        legacy_ready.get("body") if isinstance(legacy_ready.get("body"), dict) else {}
    )
    rust_ready_body = (
        rust_ready.get("body") if isinstance(rust_ready.get("body"), dict) else {}
    )

    add_check(
        report,
        "shadow.health.status_matches",
        legacy_health_body.get("status") == rust_health_body.get("status"),
        (
            f"legacy={legacy_health_body.get('status')!r}, "
            f"rust={rust_health_body.get('status')!r}"
        ),
    )
    add_check(
        report,
        "shadow.ready.status_matches",
        legacy_ready_body.get("status") == rust_ready_body.get("status"),
        (
            f"legacy={legacy_ready_body.get('status')!r}, "
            f"rust={rust_ready_body.get('status')!r}"
        ),
    )


def add_check(report: dict[str, Any], name: str, ok: bool, detail: str) -> None:
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})


if __name__ == "__main__":
    raise SystemExit(main())
