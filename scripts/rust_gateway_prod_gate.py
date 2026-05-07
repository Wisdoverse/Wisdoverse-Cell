#!/usr/bin/env python3
"""Validate Rust gateway production evidence.

This gate is intentionally stricter than the local canary/shadow probe:
production cutover must be backed by a fresh report from real listeners, not by
localhost smoke-test evidence.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EXPECTED_RUST_VERSION = "0.1.0-rust"
KNOWN_READY_STATUSES = {"ok", "degraded"}
EXPECTED_REPORT_SCHEMA_VERSION = "rust-gateway-shadow/v1"
DEFAULT_PROD_EVIDENCE_REPORT = ".artifacts/rust-gateway-prod-shadow-check.json"
REQUIRED_RUST_CHECKS = {
    "rust.health.http_200",
    "rust.health.status_ok",
    "rust.health.version",
    "rust.health.request_id_header",
    "rust.health.trace_id_header",
    "rust.ready.http_200",
    "rust.ready.status_known",
    "rust.ready.ai_service_reported",
}
REQUIRED_SHADOW_CHECKS = {
    "legacy.health.http_200",
    "legacy.health.status_ok",
    "legacy.ready.http_200",
    "legacy.ready.status_known",
    "legacy.ready.ai_service_reported",
    "shadow.health.status_matches",
    "shadow.ready.status_matches",
}


def main() -> int:
    report_path = Path(
        os.getenv(
            "RUST_GATEWAY_PROD_EVIDENCE_REPORT",
            DEFAULT_PROD_EVIDENCE_REPORT,
        )
    )
    expected_mode = os.getenv("RUST_GATEWAY_PROD_EVIDENCE_MODE", "shadow").strip()
    max_age_seconds = parse_int_env("RUST_GATEWAY_PROD_EVIDENCE_MAX_AGE_SECONDS", 3600)
    allow_local_urls = parse_bool_env("RUST_GATEWAY_PROD_ALLOW_LOCAL_URLS", False)
    allow_degraded = parse_bool_env("RUST_GATEWAY_PROD_ALLOW_DEGRADED", False)

    errors = load_and_validate_report(
        report_path,
        expected_mode=expected_mode,
        max_age_seconds=max_age_seconds,
        allow_local_urls=allow_local_urls,
        allow_degraded=allow_degraded,
        now=int(time.time()),
    )

    if errors:
        print(f"rust_gateway_prod_gate_report={report_path}")
        for error in errors:
            print(f"[fail] {error}", file=sys.stderr)
        return 1

    print(f"rust_gateway_prod_gate_report={report_path}")
    print("[ok] Rust gateway production evidence is fresh and cutover-ready")
    return 0


def load_and_validate_report(
    report_path: Path,
    *,
    expected_mode: str,
    max_age_seconds: int,
    allow_local_urls: bool,
    allow_degraded: bool,
    now: int,
) -> list[str]:
    if not report_path.exists():
        return [f"evidence report does not exist: {report_path}"]

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"evidence report is not valid JSON: {exc}"]

    return validate_report(
        report,
        expected_mode=expected_mode,
        max_age_seconds=max_age_seconds,
        allow_local_urls=allow_local_urls,
        allow_degraded=allow_degraded,
        now=now,
    )


def validate_report(
    report: dict[str, Any],
    *,
    expected_mode: str,
    max_age_seconds: int,
    allow_local_urls: bool,
    allow_degraded: bool,
    now: int,
) -> list[str]:
    errors: list[str] = []
    mode = report.get("mode")

    if report.get("schema_version") != EXPECTED_REPORT_SCHEMA_VERSION:
        errors.append(
            "evidence report schema_version must be "
            f"{EXPECTED_REPORT_SCHEMA_VERSION!r}, got {report.get('schema_version')!r}"
        )
    if report.get("ok") is not True:
        errors.append("evidence report ok must be true")
    if report.get("failed_count") != 0:
        errors.append(f"evidence report failed_count must be 0, got {report.get('failed_count')!r}")
    if expected_mode and expected_mode != "any" and mode != expected_mode:
        errors.append(f"evidence report mode must be {expected_mode!r}, got {mode!r}")

    finished_at = report.get("finished_at_unix")
    started_at = report.get("started_at_unix")
    if not isinstance(started_at, int):
        errors.append("evidence report must include integer started_at_unix")
    if not isinstance(finished_at, int):
        errors.append("evidence report must include integer finished_at_unix")
    else:
        if isinstance(started_at, int) and started_at > finished_at:
            errors.append("evidence report started_at_unix must be <= finished_at_unix")
        if finished_at > now + 60:
            errors.append("evidence report finished_at_unix must not be in the future")
        if max_age_seconds > 0 and now - finished_at > max_age_seconds:
            errors.append(
                f"evidence report is stale: age_seconds={now - finished_at}, "
                f"max_age_seconds={max_age_seconds}"
            )

    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("evidence report must include non-empty checks")
    else:
        check_names = {
            check.get("name")
            for check in checks
            if isinstance(check, dict) and isinstance(check.get("name"), str)
        }
        required_checks = set(REQUIRED_RUST_CHECKS)
        if mode == "shadow":
            required_checks.update(REQUIRED_SHADOW_CHECKS)
        missing_checks = sorted(required_checks - check_names)
        if missing_checks:
            errors.append(
                "evidence report is missing required checks: "
                + ", ".join(missing_checks)
            )
        for check in checks:
            if not isinstance(check, dict) or check.get("ok") is not True:
                errors.append(f"evidence report contains failed check: {check!r}")

    probes = report.get("probes")
    if not isinstance(probes, dict):
        errors.append("evidence report must include probes")
        probes = {}

    rust_gateway_url = report.get("rust_gateway_url")
    legacy_gateway_url = report.get("legacy_gateway_url")

    errors.extend(validate_gateway_url(report, "rust_gateway_url", allow_local_urls))
    errors.extend(
        validate_probe(
            probes,
            "rust.health",
            ready=False,
            rust=True,
            allow_degraded=False,
            expected_base_url=rust_gateway_url if isinstance(rust_gateway_url, str) else None,
            expected_path="/health",
        )
    )
    errors.extend(
        validate_probe(
            probes,
            "rust.ready",
            ready=True,
            rust=True,
            allow_degraded=allow_degraded,
            expected_base_url=rust_gateway_url if isinstance(rust_gateway_url, str) else None,
            expected_path="/ready",
        )
    )

    if mode == "shadow":
        errors.extend(validate_gateway_url(report, "legacy_gateway_url", allow_local_urls))
        if report.get("legacy_gateway_url") == report.get("rust_gateway_url"):
            errors.append("shadow evidence requires legacy and Rust gateway URLs to differ")
        errors.extend(
            validate_probe(
                probes,
                "legacy.health",
                ready=False,
                rust=False,
                allow_degraded=False,
                expected_base_url=legacy_gateway_url if isinstance(legacy_gateway_url, str) else None,
                expected_path="/health",
            )
        )
        errors.extend(
            validate_probe(
                probes,
                "legacy.ready",
                ready=True,
                rust=False,
                allow_degraded=allow_degraded,
                expected_base_url=legacy_gateway_url if isinstance(legacy_gateway_url, str) else None,
                expected_path="/ready",
            )
        )

    return errors


def validate_gateway_url(
    report: dict[str, Any], key: str, allow_local_urls: bool
) -> list[str]:
    value = report.get(key)
    if not isinstance(value, str) or not value:
        return [f"{key} must be a non-empty URL"]
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return [f"{key} must be an absolute HTTP(S) URL"]
    if not allow_local_urls and parsed.scheme != "https":
        return [f"{key} must use https for production gateway evidence"]
    if not is_base_url(value):
        return [f"{key} must be a base URL without path, query, or fragment"]
    if is_placeholder_url(value):
        return [f"{key} must not point to placeholder or documentation-only hosts"]
    if not allow_local_urls and is_local_url(value):
        return [f"{key} must not point to local, private, or non-global hosts for production cutover"]
    return []


def validate_probe(
    probes: dict[str, Any],
    name: str,
    *,
    ready: bool,
    rust: bool,
    allow_degraded: bool,
    expected_base_url: str | None = None,
    expected_path: str | None = None,
) -> list[str]:
    probe = probes.get(name)
    if not isinstance(probe, dict):
        return [f"missing probe: {name}"]

    errors: list[str] = []
    if expected_base_url and expected_path:
        expected_url = f"{expected_base_url.strip().rstrip('/')}{expected_path}"
        if probe.get("url") != expected_url:
            errors.append(f"{name} url must be {expected_url!r}, got {probe.get('url')!r}")

    if rust and not ready:
        headers = probe.get("headers")
        if not isinstance(headers, dict):
            errors.append(f"{name} headers must be a JSON object")
        else:
            request_id = probe.get("request_id")
            trace_id = probe.get("trace_id")
            if headers.get("x-request-id") != request_id:
                errors.append(
                    f"{name} x-request-id header must match request_id, "
                    f"got {headers.get('x-request-id')!r} vs {request_id!r}"
                )
            if headers.get("x-trace-id") != trace_id:
                errors.append(
                    f"{name} x-trace-id header must match trace_id, "
                    f"got {headers.get('x-trace-id')!r} vs {trace_id!r}"
                )

    if probe.get("status_code") != 200:
        errors.append(f"{name} status_code must be 200, got {probe.get('status_code')!r}")

    body = probe.get("body")
    if not isinstance(body, dict):
        errors.append(f"{name} body must be a JSON object")
        return errors

    if ready:
        status = body.get("status")
        if allow_degraded:
            if status not in KNOWN_READY_STATUSES:
                errors.append(f"{name} ready status must be ok or degraded, got {status!r}")
        elif status != "ok":
            errors.append(f"{name} ready status must be ok, got {status!r}")

        services = body.get("services")
        if not isinstance(services, dict) or "ai_service" not in services:
            errors.append(f"{name} must report ai_service readiness")
    else:
        if body.get("status") != "ok":
            errors.append(f"{name} health status must be ok, got {body.get('status')!r}")
        if rust and body.get("version") != EXPECTED_RUST_VERSION:
            errors.append(
                f"{name} version must be {EXPECTED_RUST_VERSION!r}, "
                f"got {body.get('version')!r}"
            )

    return errors


def is_base_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.path in {"", "/"} and not parsed.params and not parsed.query and not parsed.fragment


def is_local_url(value: str) -> bool:
    hostname = urlparse(value).hostname
    if not hostname:
        return False
    host = hostname.lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host_resolves_to_non_global_ip(host)
    return not ip.is_global


def host_resolves_to_non_global_ip(hostname: str) -> bool:
    try:
        addrinfos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return True

    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for addrinfo in addrinfos:
        sockaddr = addrinfo[4]
        if not sockaddr:
            continue
        try:
            addresses.add(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            return True

    if not addresses:
        return True
    return any(not address.is_global for address in addresses)


def is_placeholder_url(value: str) -> bool:
    hostname = urlparse(value).hostname
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    return (
        host == "example.com"
        or host.endswith(".example.com")
        or host.endswith(".example")
        or host.endswith(".invalid")
        or host.endswith(".test")
    )


def parse_int_env(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_bool_env(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
