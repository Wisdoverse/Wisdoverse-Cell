"""Run the Python side of Wisdoverse Cell as one Docker runtime unit."""

from __future__ import annotations

import os
import asyncio
import re
import shlex
import signal
import subprocess
import sys
import time


SERVICE_DISCOVERY_ENV = {
    "PJM_AGENT_URL": "http://127.0.0.1:8012",
    "QA_AGENT_URL": "http://127.0.0.1:8014",
    "SYNC_MODULE_HOST": "127.0.0.1",
    "SYNC_AGENT_HOST": "127.0.0.1",
}


CONTROL_PLANE_GRANTEE_ENVS = [
    ("CHAT_AGENT_DB_USER", "chat_agent"),
    ("PM_AGENT_DB_USER", "pjm_agent"),
    ("SYNC_MODULE_DB_USER", "sync_agent"),
    ("ANALYSIS_MODULE_DB_USER", "analysis_agent"),
    ("QA_AGENT_DB_USER", "qa_agent"),
    ("DEV_AGENT_DB_USER", "dev_agent"),
    ("EVOLUTION_MODULE_DB_USER", "evolution_agent"),
]


SERVICES = [
    {
        "name": "ai-core",
        "port": "8000",
        "app": "agents.requirement_manager.app.main:app",
        "db_user_env": "POSTGRES_USER",
        "db_password_env": "POSTGRES_PASSWORD",
        "db_user_default": "wisdoverse-cell",
        "db_password_default": "",
        "redis_db": "0",
        "event_consumer": "requirement-manager",
    },
    {
        "name": "sync-module",
        "port": "8010",
        "app": "shared.capabilities.sync.app.main:app",
        "db_user_env": "SYNC_MODULE_DB_USER",
        "db_password_env": "SYNC_MODULE_DB_PASSWORD",
        "db_user_default": "sync_agent",
        "db_password_default": "sync_agent_dev",
        "redis_db": "3",
        "event_consumer": "sync-module",
    },
    {
        "name": "analysis-module",
        "port": "8011",
        "app": "shared.capabilities.analysis.app.main:app",
        "db_user_env": "ANALYSIS_MODULE_DB_USER",
        "db_password_env": "ANALYSIS_MODULE_DB_PASSWORD",
        "db_user_default": "analysis_agent",
        "db_password_default": "analysis_agent_dev",
        "redis_db": "4",
        "event_consumer": "analysis-module",
    },
    {
        "name": "pjm-agent",
        "port": "8012",
        "app": "agents.pjm_agent.app.main:app",
        "db_user_env": "PM_AGENT_DB_USER",
        "db_password_env": "PM_AGENT_DB_PASSWORD",
        "db_user_default": "pjm_agent",
        "db_password_default": "pjm_agent_dev",
        "redis_db": "2",
        "event_consumer": "pjm-agent",
    },
    {
        "name": "chat-agent",
        "port": "8013",
        "app": "services.gateways.user_interaction.app.main:app",
        "db_user_env": "CHAT_AGENT_DB_USER",
        "db_password_env": "CHAT_AGENT_DB_PASSWORD",
        "db_user_default": "chat_agent",
        "db_password_default": "chat_agent_dev",
        "redis_db": "1",
        "event_consumer": "chat-agent",
    },
    {
        "name": "qa-agent",
        "port": "8014",
        "app": "agents.qa_agent.app.main:app",
        "db_user_env": "QA_AGENT_DB_USER",
        "db_password_env": "QA_AGENT_DB_PASSWORD",
        "db_user_default": "qa_agent",
        "db_password_default": "qa_agent_dev",
        "redis_db": "5",
        "event_consumer": "qa-agent",
    },
    {
        "name": "dev-agent",
        "port": "8015",
        "app": "agents.dev_agent.app.main:app",
        "db_user_env": "DEV_AGENT_DB_USER",
        "db_password_env": "DEV_AGENT_DB_PASSWORD",
        "db_user_default": "dev_agent",
        "db_password_default": "dev_agent_dev",
        "redis_db": "6",
        "event_consumer": "dev-agent",
    },
    {
        "name": "evolution-module",
        "port": "8016",
        "app": "shared.capabilities.evolution.app.main:app",
        "db_user_env": "EVOLUTION_MODULE_DB_USER",
        "db_password_env": "EVOLUTION_MODULE_DB_PASSWORD",
        "db_user_default": "evolution_agent",
        "db_password_default": "evolution_agent_dev",
        "redis_db": "7",
        "event_consumer": "evolution-module",
    },
]


children: list[subprocess.Popen[bytes]] = []
stopping = False
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def env_enabled(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def bootstrap_control_plane_tables() -> None:
    if not env_enabled("CELL_BOOTSTRAP_CONTROL_PLANE", default=True):
        return

    print("bootstrapping control-plane tables", flush=True)
    asyncio.run(_bootstrap_control_plane_tables())


def runtime_db_roles() -> list[str]:
    roles = []
    for env_name, default in CONTROL_PLANE_GRANTEE_ENVS:
        role = os.getenv(env_name, default)
        if not IDENTIFIER_RE.match(role):
            raise ValueError(f"{env_name} must be a PostgreSQL identifier")
        roles.append(role)
    return sorted(set(roles))


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _bootstrap_control_plane_tables() -> None:
    from sqlalchemy import text

    from shared.control_plane.database import control_plane_db_manager

    try:
        await control_plane_db_manager.create_tables()
        role_sql = ", ".join(quote_identifier(role) for role in runtime_db_roles())
        if not role_sql:
            return

        async with control_plane_db_manager.engine.begin() as conn:
            table_result = await conn.execute(
                text(
                    """
                    SELECT quote_ident(schemaname) || '.' || quote_ident(tablename)
                    FROM pg_tables
                    WHERE schemaname = 'public'
                      AND tablename LIKE 'control_plane_%'
                    """
                )
            )
            for table_name in table_result.scalars().all():
                await conn.execute(
                    text(
                        "GRANT SELECT, INSERT, UPDATE, DELETE "
                        f"ON TABLE {table_name} TO {role_sql}"
                    )
                )

            sequence_result = await conn.execute(
                text(
                    """
                    SELECT quote_ident(schemaname) || '.' || quote_ident(sequencename)
                    FROM pg_sequences
                    WHERE schemaname = 'public'
                      AND sequencename LIKE 'control_plane_%'
                    """
                )
            )
            for sequence_name in sequence_result.scalars().all():
                await conn.execute(
                    text(
                        "GRANT USAGE, SELECT, UPDATE "
                        f"ON SEQUENCE {sequence_name} TO {role_sql}"
                    )
                )
    finally:
        await control_plane_db_manager.close()


def service_env(service: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(SERVICE_DISCOVERY_ENV)
    env["WISDOVERSE_BIND_PORT"] = service["port"]
    env["WISDOVERSE_APP_PATH"] = service["app"]
    env["API_PORT"] = service["port"]
    env["POSTGRES_USER"] = os.getenv(service["db_user_env"], service["db_user_default"])
    env["POSTGRES_PASSWORD"] = os.getenv(
        service["db_password_env"], service["db_password_default"]
    )
    env["REDIS_DB"] = service["redis_db"]
    env["REDIS_URL"] = redis_url(service["redis_db"])
    env["OTEL_SERVICE_NAME"] = service["name"]
    env["EVENT_BUS_CONSUMER_NAME"] = service["event_consumer"]
    return env


def redis_url(redis_db: str) -> str:
    host = os.getenv("REDIS_HOST", "redis")
    port = os.getenv("REDIS_PORT", "6379")
    password = os.getenv("REDIS_PASSWORD", "")
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/{redis_db}"


def start_service(service: dict[str, str]) -> subprocess.Popen[bytes]:
    workers = os.getenv("GUNICORN_WORKERS", "1")
    extra_args = shlex.split(os.getenv("GUNICORN_EXTRA_ARGS", ""))
    command = [
        "gunicorn",
        service["app"],
        "--name",
        service["name"],
        "--worker-class",
        "uvicorn.workers.UvicornWorker",
        "--workers",
        workers,
        "--bind",
        f"0.0.0.0:{service['port']}",
        "--timeout",
        "120",
        "--graceful-timeout",
        "30",
        "--keep-alive",
        "5",
        "--no-control-socket",
        "--access-logfile",
        "-",
        "--access-logformat",
        '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)s',
        *extra_args,
    ]
    print(f"starting {service['name']} on :{service['port']}", flush=True)
    return subprocess.Popen(command, env=service_env(service))


def stop_children(signum: int = signal.SIGTERM) -> None:
    global stopping
    stopping = True
    for child in children:
        if child.poll() is None:
            child.send_signal(signum)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if all(child.poll() is not None for child in children):
            return
        time.sleep(0.2)
    for child in children:
        if child.poll() is None:
            child.kill()


def handle_signal(signum: int, _frame: object) -> None:
    stop_children(signum)


def main() -> int:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    bootstrap_control_plane_tables()

    for service in SERVICES:
        children.append(start_service(service))

    while not stopping:
        for child in children:
            status = child.poll()
            if status is not None:
                print(f"cell child exited pid={child.pid} status={status}", flush=True)
                stop_children()
                return status or 1
        time.sleep(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
