"""Call the Control Plane's durable heartbeat scheduler over HTTP."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import signal
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

LOGGER = logging.getLogger("control_plane_worker")
ENDPOINT = "/api/v1/control-plane/scheduler/heartbeats/run-once"
DEFAULT_HEALTH_FILE = Path("/tmp/control-plane-worker.health")


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    base_url: str
    company_id: str
    interval_seconds: float
    timeout_seconds: float
    internal_key: str
    operator_token: str
    health_file: Path = DEFAULT_HEALTH_FILE

    @classmethod
    def from_env(cls) -> WorkerConfig:
        base_url = os.environ.get("CONTROL_PLANE_BASE_URL", "http://ai-core:8000").rstrip("/")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("CONTROL_PLANE_BASE_URL must be an HTTP(S) origin or base path")
        company_id = os.environ.get("CONTROL_PLANE_COMPANY_ID", "").strip()
        internal_key = os.environ.get("CONTROL_PLANE_WORKER_INTERNAL_KEY", "").strip()
        operator_token = os.environ.get("CONTROL_PLANE_WORKER_OPERATOR_TOKEN", "").strip()
        if not company_id or not internal_key or not operator_token:
            raise ValueError("company id and both worker credentials must be configured")
        try:
            interval = float(os.environ.get("CONTROL_PLANE_WORKER_INTERVAL_SECONDS", "60"))
            timeout = float(os.environ.get("CONTROL_PLANE_WORKER_TIMEOUT_SECONDS", "30"))
        except ValueError:
            raise ValueError("worker interval and timeout must be numeric") from None
        if not 1 <= interval <= 86_400 or not 1 <= timeout <= 30:
            raise ValueError("worker interval or timeout is outside its allowed range")
        health_file = Path(
            os.environ.get("CONTROL_PLANE_WORKER_HEALTH_FILE", str(DEFAULT_HEALTH_FILE))
        )
        return cls(
            base_url, company_id, interval, timeout, internal_key, operator_token, health_file
        )


def backoff_delay(attempt: int, *, jitter: float | None = None) -> float:
    """Bound exponential retry delay; jitter is injectable for deterministic tests."""
    if attempt < 1:
        raise ValueError("attempt must be positive")
    factor = random.uniform(0.8, 1.2) if jitter is None else jitter
    if not 0.8 <= factor <= 1.2:
        raise ValueError("jitter factor must be between 0.8 and 1.2")
    return min(300.0, (2.0 ** min(attempt - 1, 8)) * factor)


def write_health_timestamp(path: Path, *, now: datetime | None = None) -> None:
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).timestamp()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False, encoding="ascii"
        ) as handle:
            temporary = handle.name
            handle.write(f"{timestamp:.6f}\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def health_is_fresh(path: Path, *, max_age_seconds: float, now: float | None = None) -> bool:
    try:
        age = (now if now is not None else datetime.now(UTC).timestamp()) - path.stat().st_mtime
        return 0 <= age <= max_age_seconds and path.stat().st_mode & 0o777 == 0o600
    except OSError:
        return False


class HeartbeatWorker:
    def __init__(self, config: WorkerConfig, client: httpx.AsyncClient) -> None:
        self.config = config
        self.client = client

    async def run_once(self) -> int:
        response = await self.client.post(
            f"{self.config.base_url}{ENDPOINT}",
            json={"company_id": self.config.company_id, "limit": 500},
            headers={
                "X-Internal-Key": self.config.internal_key,
                "X-Control-Plane-Operator-Token": self.config.operator_token,
            },
        )
        response.raise_for_status()
        try:
            result = response.json()
            total = result["total"]
            if isinstance(total, bool) or not isinstance(total, int) or total < 0:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise RuntimeError("scheduler returned an invalid response") from None
        write_health_timestamp(self.config.health_file)
        return total

    async def run(self, stop_event: asyncio.Event) -> None:
        failures = 0
        while not stop_event.is_set():
            try:
                total = await self.run_once()
                failures = 0
                LOGGER.info("heartbeat scheduler completed (due=%d)", total)
                delay = self.config.interval_seconds
            except (httpx.HTTPError, OSError, RuntimeError) as error:
                failures += 1
                LOGGER.warning(
                    "heartbeat scheduler request failed (attempt=%d, error_type=%s)",
                    failures,
                    type(error).__name__,
                )
                delay = backoff_delay(failures)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except TimeoutError:
                continue


async def serve(config: WorkerConfig) -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop_event.set)
    timeout = httpx.Timeout(config.timeout_seconds, connect=min(5.0, config.timeout_seconds))
    async with httpx.AsyncClient(timeout=timeout) as client:
        await HeartbeatWorker(config, client).run(stop_event)


def _healthcheck() -> int:
    try:
        interval = float(os.environ.get("CONTROL_PLANE_WORKER_INTERVAL_SECONDS", "60"))
        timeout = float(os.environ.get("CONTROL_PLANE_WORKER_TIMEOUT_SECONDS", "30"))
    except ValueError:
        return 1
    return (
        0
        if health_is_fresh(
            Path(os.environ.get("CONTROL_PLANE_WORKER_HEALTH_FILE", str(DEFAULT_HEALTH_FILE))),
            max_age_seconds=interval * 3 + timeout,
        )
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-health", action="store_true")
    args = parser.parse_args()
    if args.check_health:
        return _healthcheck()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    try:
        asyncio.run(serve(WorkerConfig.from_env()))
    except ValueError as error:
        LOGGER.error("worker configuration rejected (%s)", str(error))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
