"""Fail-closed R0 staging evidence validator; never performs or declares a cutover."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MIN_STAGING_WINDOW = timedelta(days=14)
MIN_REQUESTS = 1_000
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
HASH_NAMES = {"source", "configuration", "migration", "evidence"}


class EvidenceError(ValueError):
    """Raised when the supplied R0 evidence is absent or insufficient."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise EvidenceError("non-finite JSON number")


def _object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    missing, extra = keys - value.keys(), value.keys() - keys
    if missing:
        raise EvidenceError(f"{label} is missing required fields")
    if extra:
        raise EvidenceError(f"{label} contains unsupported fields")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{label} must be a non-empty string")
    return value.strip()


def _date(value: Any, label: str, now: datetime) -> datetime:
    raw = _text(value, label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise EvidenceError(f"{label} must be an ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{label} must include a timezone")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now:
        raise EvidenceError(f"{label} cannot be in the future")
    return parsed


def _number(value: Any, label: str, *, minimum: float, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
        raise EvidenceError(f"{label} is outside its valid range")
    return number


def _hashes(value: Any) -> dict[str, str]:
    hashes = _object(value, HASH_NAMES, "manifest_hashes")
    for name, digest in hashes.items():
        if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
            raise EvidenceError(f"manifest_hashes.{name} must be a lowercase SHA-256 digest")
    return hashes


def evaluate_evidence(evidence: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Evaluate R0 staging readiness; eligibility is not deployment acceptance."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = current.astimezone(timezone.utc)
    root = _object(
        evidence,
        {"schema_version", "engineering", "staging_observation"},
        "evidence",
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise EvidenceError("unsupported evidence schema_version")

    engineering = _object(
        root["engineering"],
        {"status", "synthetic", "runtime", "revision", "manifest_hashes"},
        "engineering",
    )
    if engineering["status"] != "passed" or engineering["synthetic"] is not True:
        raise EvidenceError("engineering evidence must be passed and explicitly synthetic")
    revision = _text(engineering["revision"], "engineering.revision")
    runtime = _text(engineering["runtime"], "engineering.runtime")
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise EvidenceError("engineering.revision must be a Git object identifier")
    hashes = _hashes(engineering["manifest_hashes"])

    staging = _object(
        root["staging_observation"],
        {
            "synthetic",
            "runtime",
            "owner",
            "revision",
            "start_utc",
            "end_utc",
            "declared_at_utc",
            "requests",
            "sampled_requests",
            "daily_samples",
            "thresholds",
            "metrics",
            "restore_drill",
            "rollback_readiness",
            "manifest_hashes",
        },
        "staging_observation",
    )
    if staging["synthetic"] is not False:
        raise EvidenceError("staging observation must be non-synthetic")
    owner = _text(staging["owner"], "staging_observation.owner")
    if _text(staging["runtime"], "staging_observation.runtime") != runtime:
        raise EvidenceError("engineering and staging runtimes differ")
    if _text(staging["revision"], "staging_observation.revision") != revision:
        raise EvidenceError("engineering and staging revisions differ")
    if _hashes(staging["manifest_hashes"]) != hashes:
        raise EvidenceError("engineering and staging manifest hashes differ")

    started = _date(staging["start_utc"], "start_utc", current)
    ended = _date(staging["end_utc"], "end_utc", current)
    declared = _date(staging["declared_at_utc"], "declared_at_utc", current)
    if ended <= started or ended - started < MIN_STAGING_WINDOW:
        raise EvidenceError("staging observation must span at least 14 continuous days")
    if declared > started:
        raise EvidenceError("SLO thresholds must be declared before observation starts")

    requests = staging["requests"]
    sampled = staging["sampled_requests"]
    if (
        isinstance(requests, bool)
        or not isinstance(requests, int)
        or requests < MIN_REQUESTS
        or isinstance(sampled, bool)
        or not isinstance(sampled, int)
        or sampled < MIN_REQUESTS
        or requests != sampled
    ):
        raise EvidenceError(f"request counts must match and meet the {MIN_REQUESTS} minimum")

    daily_samples = staging["daily_samples"]
    if not isinstance(daily_samples, list):
        raise EvidenceError("daily_samples must be an array")
    expected_days: list[str] = []
    day = started.date()
    last_day = (ended - timedelta(microseconds=1)).date()
    while day <= last_day:
        expected_days.append(day.isoformat())
        day += timedelta(days=1)
    observed_days: list[str] = []
    daily_total = 0
    for item in daily_samples:
        sample = _object(item, {"date_utc", "requests"}, "daily sample")
        date = _text(sample["date_utc"], "daily sample date")
        try:
            parsed_day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise EvidenceError("daily sample dates must use YYYY-MM-DD") from None
        if parsed_day.isoformat() != date:
            raise EvidenceError("daily sample dates must use YYYY-MM-DD")
        count = sample["requests"]
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise EvidenceError("each observed day must include a positive request count")
        observed_days.append(date)
        daily_total += count
    if observed_days != expected_days or daily_total != sampled:
        raise EvidenceError(
            "daily samples must cover every observation day and match sampled_requests"
        )

    thresholds = _object(
        staging["thresholds"],
        {
            "uptime_percent_min",
            "error_rate_percent_max",
            "p95_latency_ms_max",
            "cost_per_request_max",
        },
        "thresholds",
    )
    metrics = _object(
        staging["metrics"],
        {"uptime_percent", "error_rate_percent", "p95_latency_ms", "cost_per_request"},
        "metrics",
    )
    t_uptime = _number(thresholds["uptime_percent_min"], "uptime threshold", minimum=0, maximum=100)
    t_error = _number(
        thresholds["error_rate_percent_max"], "error threshold", minimum=0, maximum=100
    )
    t_latency = _number(thresholds["p95_latency_ms_max"], "p95 threshold", minimum=0)
    t_cost = _number(thresholds["cost_per_request_max"], "cost threshold", minimum=0)
    if t_uptime == 0 or t_error == 100:
        raise EvidenceError("uptime and error thresholds must be meaningful SLO targets")
    m_uptime = _number(metrics["uptime_percent"], "uptime metric", minimum=0, maximum=100)
    m_error = _number(metrics["error_rate_percent"], "error metric", minimum=0, maximum=100)
    m_latency = _number(metrics["p95_latency_ms"], "p95 metric", minimum=0)
    m_cost = _number(metrics["cost_per_request"], "cost metric", minimum=0)
    if m_uptime < t_uptime or m_error > t_error or m_latency > t_latency or m_cost > t_cost:
        raise EvidenceError("sampled metrics do not meet declared SLO thresholds")

    restore = _object(
        staging["restore_drill"], {"passed", "synthetic", "date_utc", "revision"}, "restore_drill"
    )
    rollback = _object(
        staging["rollback_readiness"], {"passed", "date_utc", "revision"}, "rollback_readiness"
    )
    if restore["passed"] is not True or restore["synthetic"] is not False:
        raise EvidenceError("restore drill must be passed against non-synthetic data")
    if rollback["passed"] is not True:
        raise EvidenceError("rollback readiness must be passed")
    for label, record in (("restore_drill", restore), ("rollback_readiness", rollback)):
        _date(record["date_utc"], f"{label}.date_utc", current)
        if _text(record["revision"], f"{label}.revision") != revision:
            raise EvidenceError(f"{label} revision differs from the observed revision")

    return {
        "schema_version": 1,
        "status": "eligible_for_production_cutover_review",
        "engineering": "passed_synthetic",
        "staging_observation": "passed",
        "production_cutover": "pending",
        "deployed": False,
        "runtime": runtime,
        "owner": owner,
        "revision": revision,
        "observation_days": (ended - started).total_seconds() / 86400,
        "requests": requests,
        "manifest_hashes": hashes,
        "checks": {
            "slo_thresholds": "passed",
            "restore_drill": "passed",
            "rollback_readiness": "passed",
            "revision_consistency": "passed",
        },
    }


def load_evidence(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except FileNotFoundError:
        raise EvidenceError("evidence file is missing") from None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise EvidenceError("evidence file is unreadable or invalid JSON") from None


def blocked_report(reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "blocked",
        "engineering": "unverified_or_synthetic_only",
        "staging_observation": "not_accepted",
        "production_cutover": "pending",
        "deployed": False,
        "reason": reason,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False, encoding="utf-8"
        ) as handle:
            temporary = handle.name
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate_evidence(load_evidence(args.evidence))
    except EvidenceError as error:
        report = blocked_report(str(error))
    except Exception:
        report = blocked_report("evidence validation failed")
    write_report(args.report, report)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if report["status"] == "eligible_for_production_cutover_review" else 1


if __name__ == "__main__":
    sys.exit(main())
