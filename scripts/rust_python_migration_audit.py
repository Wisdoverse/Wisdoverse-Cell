#!/usr/bin/env python3
"""Audit the Rust + Python backend migration artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_PROD_EVIDENCE_REPORT = ".artifacts/rust-gateway-prod-shadow-check.json"


@dataclass(frozen=True)
class AuditCheck:
    name: str
    ok: bool
    required: bool
    detail: str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--require-prod-evidence",
        action="store_true",
        help="Fail unless the production evidence report passes rust-gateway-prod-gate",
    )
    parser.add_argument(
        "--prod-report",
        default=os.getenv(
            "RUST_GATEWAY_PROD_EVIDENCE_REPORT",
            DEFAULT_PROD_EVIDENCE_REPORT,
        ),
        help="Path to the production shadow/canary evidence report",
    )
    args = parser.parse_args()

    checks = evaluate_migration(
        Path.cwd(),
        require_prod_evidence=args.require_prod_evidence,
        prod_report_path=Path(args.prod_report),
    )
    failed = [check for check in checks if check.required and not check.ok]
    payload = {
        "ok": not failed,
        "failed_required_count": len(failed),
        "checks": [asdict(check) for check in checks],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for check in checks:
            status = "ok" if check.ok else ("manual" if not check.required else "fail")
            print(f"[{status}] {check.name}: {check.detail}")

    return 0 if not failed else 1


def evaluate_migration(
    root: Path,
    *,
    require_prod_evidence: bool,
    prod_report_path: Path,
) -> list[AuditCheck]:
    checks = [
        contains(
            root,
            "docs/adr/0007-rust-python-backend-migration.md",
            ["Rust edge plane", "Python agent plane", "rust-gateway-prod-gate"],
            "ADR records the Rust edge plane and Python agent plane decision",
        ),
        exists(root, "rust/Cargo.toml", "Rust workspace exists"),
        exists(root, "rust/gateway/src/routes.rs", "Rust gateway routes exist"),
        absent(root, "gateway", "legacy Go gateway source tree is removed"),
        absent(
            root,
            "docker/compose/docker-compose.go-gateway-legacy.yml",
            "legacy Go gateway development rollback overlay is removed",
        ),
        absent(
            root,
            "docker/compose/docker-compose.go-gateway-legacy-prod.yml",
            "legacy Go gateway production rollback overlay is removed",
        ),
        absent(root, "scripts/resolve-go-version.sh", "Go toolchain resolver is removed"),
        contains(
            root,
            "docker/compose/docker-compose.app.yml",
            [
                "dockerfile: rust/gateway/Dockerfile",
                "wisdoverse/cell-rust-gateway",
                "GATEWAY_IMPLEMENTATION: rust",
            ],
            "application Compose runs the canonical gateway with Rust",
        ),
        contains(
            root,
            "docker-compose.yml",
            [
                "dockerfile: rust/gateway/Dockerfile",
                "wisdoverse/cell-rust-gateway",
                "GATEWAY_IMPLEMENTATION: rust",
            ],
            "root Compose runs the canonical gateway with Rust",
        ),
        contains(
            root,
            "docker/compose/docker-compose.rust-gateway-shadow.yml",
            ["rust-gateway-shadow", "RUST_GATEWAY_SHADOW_PORT", "replicas: 1"],
            "shadow overlay adds a separate Rust gateway listener for canaries",
        ),
        contains(
            root,
            "docker/compose/docker-compose.prod.yml",
            [
                "wisdoverse/cell-rust-gateway",
                "build: !reset null",
                "GATEWAY_IMPLEMENTATION: rust",
            ],
            "production Compose uses the prebuilt Rust gateway image by default",
        ),
        contains(
            root,
            "docker-compose.prod.yml",
            [
                "wisdoverse/cell-rust-gateway",
                "build: !reset null",
                "GATEWAY_IMPLEMENTATION: rust",
            ],
            "root production Compose uses the prebuilt Rust gateway image by default",
        ),
        contains(
            root,
            "docker/compose/docker-compose.rust-gateway-prod-shadow.yml",
            [
                "rust-gateway-shadow",
                "RUST_GATEWAY_SHADOW_HOST",
                "build: !reset null",
                "entrypoints=websecure",
                "tls=true",
                "tls.certresolver=letsencrypt",
            ],
            "production shadow overlay exposes Rust gateway through a separate host over HTTPS",
        ),
        contains(
            root,
            "docker/compose/docker-compose.prod.yml",
            [
                "${HTTPS_PORT:-443}:443",
                "TRAEFIK_ACME_EMAIL",
                "traefik_letsencrypt:/letsencrypt",
                "GATEWAY_HOST",
                "traefik.http.routers.gateway.rule=Host(`${GATEWAY_HOST:",
                "traefik.http.routers.gateway.entrypoints=websecure",
                "traefik.http.routers.gateway.tls.certresolver=letsencrypt",
                "--entrypoints.websecure.address=:443",
                "--providers.file.directory=/etc/traefik/dynamic",
                "--certificatesresolvers.letsencrypt.acme.email=",
                "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json",
                "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web",
            ],
            "production Compose publishes HTTPS and ACME CLI config for gateway evidence",
        ),
        contains(
            root,
            "docker/compose/docker-compose.proxy.yml",
            ["image: traefik:v3.6"],
            "Traefik proxy image supports the current Docker provider API",
        ),
        contains(
            root,
            ".env.example",
            [
                "SYNC_MODULE_DB_PASSWORD",
                "ANALYSIS_MODULE_DB_PASSWORD",
                "EVOLUTION_MODULE_DB_PASSWORD",
                "RUST_GATEWAY_SHADOW_HOST",
                "RUST_GATEWAY_LOCAL_EVIDENCE_REPORT",
                "RUST_GATEWAY_PROD_EVIDENCE_REPORT",
                "GATEWAY_HOST",
                "HTTPS_PORT",
                "TRAEFIK_ACME_EMAIL",
            ],
            ".env.example documents canonical module environment variables",
        ),
        not_contains(
            root,
            "docker/Dockerfile.agents",
            [
                "FROM sync-module AS sync-agent",
                "FROM analysis-module AS analysis-agent",
                "FROM evolution-module AS evolution-agent",
            ],
            "Docker build targets use module names for support capabilities",
        ),
        not_contains(
            root,
            "shared/capabilities/sync/service/agent.py",
            ["SyncAgent = SyncModule"],
            "sync support capability exposes SyncModule, not SyncAgent",
        ),
        not_contains(
            root,
            "shared/capabilities/analysis/service/agent.py",
            ["AnalysisAgent = AnalysisModule"],
            "analysis support capability exposes AnalysisModule, not AnalysisAgent",
        ),
        not_contains(
            root,
            "shared/capabilities/evolution/service/agent.py",
            ["EvolutionAgent = EvolutionModule"],
            "evolution support capability exposes EvolutionModule, not EvolutionAgent",
        ),
        contains(
            root,
            "Makefile",
            [
                "rust-gateway-test:",
                "rust-gateway-shadow-check:",
                "rust-gateway-local-shadow-gate:",
                "RUST_GATEWAY_LOCAL_EVIDENCE_REPORT",
                "RUST_GATEWAY_PROD_ALLOW_LOCAL_URLS=true",
                "rust-gateway-prod-shadow-check:",
                "rust-gateway-prod-gate:",
                "rust-gateway-prod-shadow-config:",
                "rust-gateway-prod-cutover-config:",
                "up-prod-rust-gateway-shadow:",
                "up-prod-rust-gateway: rust-gateway-prod-cutover-config rust-gateway-prod-gate",
            ],
            "Make targets cover Rust defaults, shadow evidence, and production gate",
        ),
        contains(
            root,
            ".github/workflows/ci.yml",
            [
                "rust-gateway:",
                "cargo test --manifest-path rust/Cargo.toml --locked",
                "docker build -f rust/gateway/Dockerfile -t wisdoverse/cell-rust-gateway:ci .",
            ],
            "GitHub Actions runs Rust gateway checks",
        ),
        contains(
            root,
            "scripts/rust_gateway_prod_gate.py",
            [
                "RUST_GATEWAY_PROD_EVIDENCE_REPORT",
                "EXPECTED_REPORT_SCHEMA_VERSION",
                "REQUIRED_RUST_CHECKS",
                "REQUIRED_SHADOW_CHECKS",
                "must use https",
                "base URL without path, query, or fragment",
                "expected_base_url",
                "allow_degraded",
                "socket.getaddrinfo",
                "host_resolves_to_non_global_ip",
            ],
            "production gate rejects weak or forged gateway evidence",
        ),
        contains(
            root,
            "scripts/rust_gateway_shadow_check.py",
            [
                "REPORT_SCHEMA_VERSION",
                '"schema_version": REPORT_SCHEMA_VERSION',
                "PROBE_USER_AGENT",
                '"User-Agent": PROBE_USER_AGENT',
            ],
            "shadow checker writes versioned evidence reports with an explicit probe User-Agent",
        ),
        contains(
            root,
            "scripts/rust_gateway_prod_shadow_preflight.py",
            [
                "GATEWAY_HOST",
                "LEGACY_GATEWAY_URL",
                "RUST_GATEWAY_URL",
                "GATEWAY_HOST must match",
                "must use https",
                "base URL without path, query, or fragment",
                "local, private, or non-global",
                "placeholder or documentation-only",
                "is_local_url",
            ],
            "production shadow evidence preflight rejects missing, non-HTTPS, path-scoped, non-global, or placeholder URLs",
        ),
        contains(
            root,
            ".github/PULL_REQUEST_TEMPLATE.md",
            [
                "rust-python-migration-audit-prod",
                "rust-gateway-local-shadow-gate",
                "rust-gateway-prod-shadow-check",
                "GATEWAY_HOST",
                "distinct globally routable",
            ],
            "PR template requires local and production Rust gateway evidence",
        ),
        rust_public_routes(root),
        prod_evidence(
            root,
            prod_report_path=prod_report_path,
            required=require_prod_evidence,
        ),
    ]
    return checks


def exists(root: Path, relative_path: str, detail: str) -> AuditCheck:
    path = root / relative_path
    return AuditCheck(relative_path, path.exists(), True, detail)


def absent(root: Path, relative_path: str, detail: str) -> AuditCheck:
    path = root / relative_path
    return AuditCheck(relative_path, not path.exists(), True, detail)


def contains(
    root: Path,
    relative_path: str,
    needles: Iterable[str],
    detail: str,
) -> AuditCheck:
    path = root / relative_path
    if not path.exists():
        return AuditCheck(relative_path, False, True, f"missing {relative_path}")
    content = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in content]
    if missing:
        return AuditCheck(
            relative_path,
            False,
            True,
            f"missing expected markers: {', '.join(missing)}",
        )
    return AuditCheck(relative_path, True, True, detail)


def not_contains(
    root: Path,
    relative_path: str,
    needles: Iterable[str],
    detail: str,
) -> AuditCheck:
    path = root / relative_path
    if not path.exists():
        return AuditCheck(relative_path, False, True, f"missing {relative_path}")
    content = path.read_text(encoding="utf-8")
    found = [needle for needle in needles if needle in content]
    if found:
        return AuditCheck(
            relative_path,
            False,
            True,
            f"found forbidden markers: {', '.join(found)}",
        )
    return AuditCheck(relative_path, True, True, detail)


def rust_public_routes(root: Path) -> AuditCheck:
    rust_routes = (root / "rust/gateway/src/routes.rs").read_text(encoding="utf-8")
    compose = (root / "docker/compose/docker-compose.app.yml").read_text(encoding="utf-8")
    required_markers = [
        (rust_routes, '.route("/health", get(health))'),
        (rust_routes, '.route("/ready", get(ready))'),
        (rust_routes, '.route("/api/feishu/webhook", post(feishu_webhook))'),
        (
            rust_routes,
            '.route("/api/wecom/webhook", get(wecom_verify).post(wecom_webhook))',
        ),
        (compose, "traefik.http.routers.gateway.rule=PathPrefix(`/webhook`)"),
        (rust_routes, '.route("/webhook/feishu", post(feishu_webhook))'),
        (
            rust_routes,
            '.route("/webhook/wecom", get(wecom_verify).post(wecom_webhook))',
        ),
    ]
    missing = [
        marker
        for content, marker in required_markers
        if marker not in content
    ]
    return AuditCheck(
        "rust_gateway.public_routes",
        not missing,
        True,
        "Rust gateway owns the public gateway routes"
        if not missing
        else f"missing public route markers: {missing}",
    )


def prod_evidence(root: Path, *, prod_report_path: Path, required: bool) -> AuditCheck:
    from scripts.rust_gateway_prod_gate import load_and_validate_report

    report_path = prod_report_path if prod_report_path.is_absolute() else root / prod_report_path
    errors = load_and_validate_report(
        report_path,
        expected_mode="shadow",
        max_age_seconds=3600,
        allow_local_urls=False,
        allow_degraded=False,
        now=int(time.time()),
    )
    return AuditCheck(
        "rust_gateway.production_evidence",
        not errors,
        required,
        "fresh production shadow evidence passes rust-gateway-prod-gate"
        if not errors
        else "; ".join(errors),
    )


if __name__ == "__main__":
    raise SystemExit(main())
