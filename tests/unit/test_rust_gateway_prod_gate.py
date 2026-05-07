import socket
import time

import pytest

from scripts.rust_gateway_prod_gate import (
    DEFAULT_PROD_EVIDENCE_REPORT,
    EXPECTED_REPORT_SCHEMA_VERSION,
    validate_report,
)
from scripts.rust_gateway_shadow_check import REPORT_SCHEMA_VERSION


@pytest.fixture(autouse=True)
def _stable_prod_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int | None,
        *args: object,
        **kwargs: object,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        if host.endswith(".wisdoverse.dev"):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("93.184.216.34", port or 0),
                )
            ]
        raise socket.gaierror(f"test DNS does not know {host}")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_default_report_path_is_prod_shadow_specific() -> None:
    assert DEFAULT_PROD_EVIDENCE_REPORT == ".artifacts/rust-gateway-prod-shadow-check.json"


def test_shadow_checker_and_prod_gate_schema_versions_match() -> None:
    assert REPORT_SCHEMA_VERSION == EXPECTED_REPORT_SCHEMA_VERSION


def _probe(
    status: str = "ok",
    *,
    rust: bool = False,
    ready: bool = False,
    url: str = "https://gateway.wisdoverse.dev/health",
) -> dict:
    body = {"status": status}
    request_id = "req-rust-health" if rust and not ready else "req"
    trace_id = "trace-rust-health" if rust and not ready else "trace"
    headers = {}
    if rust and not ready:
        body["version"] = "0.1.0-rust"
        headers = {
            "x-request-id": request_id,
            "x-trace-id": trace_id,
        }
    if ready:
        body["services"] = {"ai_service": "ok"}
    return {
        "url": url,
        "status_code": 200,
        "headers": headers,
        "body": body,
        "request_id": request_id,
        "trace_id": trace_id,
    }


def _checks() -> list[dict]:
    return [
        {"name": name, "ok": True, "detail": "ok"}
        for name in (
            "rust.health.http_200",
            "rust.health.status_ok",
            "rust.health.version",
            "rust.health.request_id_header",
            "rust.health.trace_id_header",
            "rust.ready.http_200",
            "rust.ready.status_known",
            "rust.ready.ai_service_reported",
            "legacy.health.http_200",
            "legacy.health.status_ok",
            "legacy.ready.http_200",
            "legacy.ready.status_known",
            "legacy.ready.ai_service_reported",
            "shadow.health.status_matches",
            "shadow.ready.status_matches",
        )
    ]


def _report(now: int, *, rust_ready: str = "ok") -> dict:
    return {
        "schema_version": "rust-gateway-shadow/v1",
        "mode": "shadow",
        "ok": True,
        "failed_count": 0,
        "started_at_unix": now - 1,
        "finished_at_unix": now,
        "legacy_gateway_url": "https://gateway.wisdoverse.dev",
        "rust_gateway_url": "https://rust-gateway.wisdoverse.dev",
        "checks": _checks(),
        "probes": {
            "rust.health": _probe(
                rust=True,
                url="https://rust-gateway.wisdoverse.dev/health",
            ),
            "rust.ready": _probe(
                rust_ready,
                rust=True,
                ready=True,
                url="https://rust-gateway.wisdoverse.dev/ready",
            ),
            "legacy.health": _probe(url="https://gateway.wisdoverse.dev/health"),
            "legacy.ready": _probe(
                ready=True,
                url="https://gateway.wisdoverse.dev/ready",
            ),
        },
    }


def test_accepts_fresh_shadow_report_from_real_urls() -> None:
    now = int(time.time())

    errors = validate_report(
        _report(now),
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert errors == []


def test_rejects_localhost_evidence_for_production_cutover() -> None:
    now = int(time.time())
    report = _report(now)
    report["rust_gateway_url"] = "https://127.0.0.1:18080"

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert "rust_gateway_url must not point to local, private, or non-global hosts" in errors[0]


def test_rejects_private_ip_evidence_for_production_cutover() -> None:
    now = int(time.time())
    report = _report(now)
    report["rust_gateway_url"] = "https://10.0.0.12:18080"

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert "rust_gateway_url must not point to local, private, or non-global hosts" in errors[0]


def test_rejects_hostname_resolving_to_loopback_for_production_cutover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = int(time.time())
    report = _report(now)
    report["rust_gateway_url"] = "https://rust-gateway.127.0.0.1.nip.io"
    report["probes"]["rust.health"]["url"] = "https://rust-gateway.127.0.0.1.nip.io/health"
    report["probes"]["rust.ready"]["url"] = "https://rust-gateway.127.0.0.1.nip.io/ready"

    def fake_getaddrinfo(
        host: str,
        port: int | None,
        *args: object,
        **kwargs: object,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        if host == "rust-gateway.127.0.0.1.nip.io":
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("127.0.0.1", port or 0),
                )
            ]
        if host.endswith(".wisdoverse.dev"):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("93.184.216.34", port or 0),
                )
            ]
        raise socket.gaierror(f"test DNS does not know {host}")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert "rust_gateway_url must not point to local, private, or non-global hosts" in errors[0]


def test_rejects_unresolvable_hostname_for_production_cutover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = int(time.time())
    report = _report(now)
    report["rust_gateway_url"] = "https://rust-gateway.unresolvable.invalid-prod"
    report["probes"]["rust.health"]["url"] = "https://rust-gateway.unresolvable.invalid-prod/health"
    report["probes"]["rust.ready"]["url"] = "https://rust-gateway.unresolvable.invalid-prod/ready"

    def fake_getaddrinfo(
        host: str,
        port: int | None,
        *args: object,
        **kwargs: object,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        if host.endswith(".wisdoverse.dev"):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("93.184.216.34", port or 0),
                )
            ]
        raise socket.gaierror(f"test DNS does not know {host}")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert "rust_gateway_url must not point to local, private, or non-global hosts" in errors[0]


def test_rejects_http_evidence_for_production_cutover() -> None:
    now = int(time.time())
    report = _report(now)
    report["rust_gateway_url"] = "http://rust-gateway.wisdoverse.dev"

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert "rust_gateway_url must use https for production gateway evidence" in errors[0]


@pytest.mark.parametrize(
    ("key", "value", "health_url", "ready_url"),
    [
        (
            "rust_gateway_url",
            "https://rust-gateway.wisdoverse.dev/api",
            "https://rust-gateway.wisdoverse.dev/api/health",
            "https://rust-gateway.wisdoverse.dev/api/ready",
        ),
        (
            "rust_gateway_url",
            "https://rust-gateway.wisdoverse.dev?mode=shadow",
            "https://rust-gateway.wisdoverse.dev?mode=shadow/health",
            "https://rust-gateway.wisdoverse.dev?mode=shadow/ready",
        ),
        (
            "legacy_gateway_url",
            "https://gateway.wisdoverse.dev#shadow",
            "https://gateway.wisdoverse.dev#shadow/health",
            "https://gateway.wisdoverse.dev#shadow/ready",
        ),
    ],
)
def test_rejects_gateway_urls_with_path_query_or_fragment(
    key: str,
    value: str,
    health_url: str,
    ready_url: str,
) -> None:
    now = int(time.time())
    report = _report(now)
    report[key] = value
    if key == "rust_gateway_url":
        report["probes"]["rust.health"]["url"] = health_url
        report["probes"]["rust.ready"]["url"] = ready_url
    else:
        report["probes"]["legacy.health"]["url"] = health_url
        report["probes"]["legacy.ready"]["url"] = ready_url

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert f"{key} must be a base URL without path, query, or fragment" in errors


def test_allows_local_http_evidence_for_explicit_non_production_drill() -> None:
    now = int(time.time())
    report = _report(now)
    report["legacy_gateway_url"] = "http://127.0.0.1:18081"
    report["rust_gateway_url"] = "http://127.0.0.1:18083"
    report["probes"]["rust.health"]["url"] = "http://127.0.0.1:18083/health"
    report["probes"]["rust.ready"]["url"] = "http://127.0.0.1:18083/ready"
    report["probes"]["legacy.health"]["url"] = "http://127.0.0.1:18081/health"
    report["probes"]["legacy.ready"]["url"] = "http://127.0.0.1:18081/ready"

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=True,
        allow_degraded=False,
        now=now,
    )

    assert errors == []


def test_rejects_placeholder_evidence_for_production_cutover() -> None:
    now = int(time.time())
    report = _report(now)
    report["rust_gateway_url"] = "https://rust-gateway.example.com"

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert "rust_gateway_url must not point to placeholder or documentation-only hosts" in errors[0]


def test_rejects_probe_url_mismatch_for_production_cutover() -> None:
    now = int(time.time())
    report = _report(now)
    report["probes"]["rust.ready"]["url"] = "http://127.0.0.1:18080/ready"

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert any(
        "rust.ready url must be 'https://rust-gateway.wisdoverse.dev/ready'" in error
        for error in errors
    )


def test_rejects_rust_health_request_trace_header_mismatch() -> None:
    now = int(time.time())
    report = _report(now)
    report["probes"]["rust.health"]["headers"]["x-request-id"] = "wrong"
    report["probes"]["rust.health"]["headers"]["x-trace-id"] = "wrong"

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert any("rust.health x-request-id header must match request_id" in error for error in errors)
    assert any("rust.health x-trace-id header must match trace_id" in error for error in errors)


def test_rejects_reports_missing_required_shadow_checks() -> None:
    now = int(time.time())
    report = _report(now)
    report["checks"] = [{"name": "shadow.ready.status_matches", "ok": True, "detail": "ok"}]

    errors = validate_report(
        report,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert any("evidence report is missing required checks" in error for error in errors)
    assert any("rust.health.http_200" in error for error in errors)


def test_rejects_wrong_schema_or_future_evidence() -> None:
    now = int(time.time())
    wrong_schema = _report(now)
    wrong_schema["schema_version"] = "legacy"
    future = _report(now)
    future["finished_at_unix"] = now + 120
    future["started_at_unix"] = now + 119
    reversed_times = _report(now)
    reversed_times["started_at_unix"] = now + 1

    wrong_schema_errors = validate_report(
        wrong_schema,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )
    future_errors = validate_report(
        future,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )
    reversed_time_errors = validate_report(
        reversed_times,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert any("schema_version must be 'rust-gateway-shadow/v1'" in error for error in wrong_schema_errors)
    assert any("finished_at_unix must not be in the future" in error for error in future_errors)
    assert any("started_at_unix must be <= finished_at_unix" in error for error in reversed_time_errors)


def test_rejects_stale_or_degraded_production_evidence() -> None:
    now = int(time.time())

    stale_errors = validate_report(
        _report(now - 7200),
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )
    degraded_errors = validate_report(
        _report(now, rust_ready="degraded"),
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=now,
    )

    assert any("evidence report is stale" in error for error in stale_errors)
    assert any("rust.ready ready status must be ok" in error for error in degraded_errors)
