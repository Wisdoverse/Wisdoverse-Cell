"""R0 evidence gates; fixtures are examples, never deployment evidence."""

import json
from datetime import datetime, timezone

import pytest

from scripts.check_operational_readiness import EvidenceError, evaluate_evidence, main

NOW = datetime(2026, 1, 20, tzinfo=timezone.utc)
REVISION = "a" * 40
HASH = "b" * 64


def evidence_fixture() -> dict:
    hashes = {
        "source": HASH,
        "configuration": "c" * 64,
        "migration": "d" * 64,
        "evidence": "e" * 64,
    }
    return {
        "schema_version": 1,
        "engineering": {
            "status": "passed",
            "synthetic": True,
            "runtime": "dev-agent",
            "revision": REVISION,
            "manifest_hashes": hashes,
        },
        "staging_observation": {
            "synthetic": False,
            "runtime": "dev-agent",
            "owner": "release-operator",
            "revision": REVISION,
            "start_utc": "2026-01-01T00:00:00Z",
            "end_utc": "2026-01-15T00:00:00Z",
            "declared_at_utc": "2025-12-30T00:00:00Z",
            "requests": 10_000,
            "sampled_requests": 10_000,
            "daily_samples": [
                {
                    "date_utc": f"2026-01-{day:02d}",
                    "requests": 715 if day <= 4 else 714,
                }
                for day in range(1, 15)
            ],
            "thresholds": {
                "uptime_percent_min": 99.0,
                "error_rate_percent_max": 1.0,
                "p95_latency_ms_max": 500,
                "cost_per_request_max": 0.05,
            },
            "metrics": {
                "uptime_percent": 99.5,
                "error_rate_percent": 0.5,
                "p95_latency_ms": 420,
                "cost_per_request": 0.03,
            },
            "restore_drill": {
                "passed": True,
                "synthetic": False,
                "date_utc": "2026-01-14T00:00:00Z",
                "revision": REVISION,
            },
            "rollback_readiness": {
                "passed": True,
                "date_utc": "2026-01-14T00:00:00Z",
                "revision": REVISION,
            },
            "manifest_hashes": hashes.copy(),
        },
    }


@pytest.mark.public
def test_exactly_fourteen_day_qualified_staging_is_eligible_for_review():
    report = evaluate_evidence(evidence_fixture(), now=NOW)
    assert report["status"] == "eligible_for_production_cutover_review"
    assert report["observation_days"] == 14
    assert report["engineering"] == "passed_synthetic"
    assert report["staging_observation"] == "passed"
    assert report["production_cutover"] == "pending"
    assert report["deployed"] is False


@pytest.mark.public
def test_thirteen_day_observation_is_blocked():
    evidence = evidence_fixture()
    evidence["staging_observation"]["end_utc"] = "2026-01-14T23:59:59Z"
    with pytest.raises(EvidenceError, match="at least 14"):
        evaluate_evidence(evidence, now=NOW)


@pytest.mark.public
def test_synthetic_staging_observation_is_blocked():
    evidence = evidence_fixture()
    evidence["staging_observation"]["synthetic"] = True
    with pytest.raises(EvidenceError, match="non-synthetic"):
        evaluate_evidence(evidence, now=NOW)


@pytest.mark.public
def test_missing_day_in_observation_window_is_blocked():
    evidence = evidence_fixture()
    evidence["staging_observation"]["daily_samples"].pop(4)
    with pytest.raises(EvidenceError, match="cover every observation day"):
        evaluate_evidence(evidence, now=NOW)


@pytest.mark.public
@pytest.mark.parametrize("missing", ["metric", "hash"])
def test_missing_metric_or_manifest_hash_is_blocked(missing):
    evidence = evidence_fixture()
    if missing == "metric":
        del evidence["staging_observation"]["metrics"]["p95_latency_ms"]
    else:
        del evidence["staging_observation"]["manifest_hashes"]["migration"]
    with pytest.raises(EvidenceError):
        evaluate_evidence(evidence, now=NOW)


@pytest.mark.public
@pytest.mark.parametrize(
    "change, message",
    [
        (lambda e: e["staging_observation"].update(revision="f" * 40), "revisions differ"),
        (lambda e: e["staging_observation"].update(start_utc="2026-01-21T00:00:00Z"), "future"),
        (lambda e: e["staging_observation"]["metrics"].update(p95_latency_ms=-1), "valid range"),
        (lambda e: e["staging_observation"].update(requests=12), "request counts"),
        (
            lambda e: e["staging_observation"]["metrics"].update(error_rate_percent=1.1),
            "thresholds",
        ),
    ],
)
def test_invalid_or_mixed_evidence_is_blocked(change, message):
    evidence = evidence_fixture()
    change(evidence)
    with pytest.raises(EvidenceError, match=message):
        evaluate_evidence(evidence, now=NOW)


@pytest.mark.public
def test_cutover_claim_and_non_finite_json_are_rejected(tmp_path):
    evidence = evidence_fixture()
    evidence["deployed"] = True
    with pytest.raises(EvidenceError, match="unsupported fields"):
        evaluate_evidence(evidence, now=NOW)

    path = tmp_path / "nan.json"
    path.write_text('{"schema_version": NaN}', encoding="utf-8")
    from scripts.check_operational_readiness import load_evidence

    with pytest.raises(EvidenceError, match="non-finite"):
        load_evidence(path)


@pytest.mark.public
def test_missing_evidence_cli_writes_blocked_report_and_nonzero_exit(tmp_path):
    report_path = tmp_path / "report.json"
    code = main(["--evidence", str(tmp_path / "absent.json"), "--report", str(report_path)])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 1
    assert report["status"] == "blocked"
    assert report["production_cutover"] == "pending"
    assert report["deployed"] is False
