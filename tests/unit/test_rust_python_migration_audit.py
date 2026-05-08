from pathlib import Path

from scripts.rust_python_migration_audit import (
    DEFAULT_PROD_EVIDENCE_REPORT,
    evaluate_migration,
)


def test_default_prod_report_path_is_prod_shadow_specific() -> None:
    assert DEFAULT_PROD_EVIDENCE_REPORT == ".artifacts/rust-gateway-prod-shadow-check.json"


def test_local_migration_audit_passes_required_repo_artifacts() -> None:
    checks = evaluate_migration(
        Path.cwd(),
        require_prod_evidence=False,
        prod_report_path=Path(".artifacts/rust-gateway-shadow-compose-check.json"),
    )

    failed_required = [check for check in checks if check.required and not check.ok]

    assert failed_required == []
    assert any(check.name == "rust_gateway.production_evidence" for check in checks)
    assert any(
        check.name == ".env.example"
        and "canonical module environment variables" in check.detail
        for check in checks
    )
    assert any(
        check.name == "docker/Dockerfile.agents"
        and "module names for support capabilities" in check.detail
        for check in checks
    )
    assert any(
        check.name == "Makefile"
        and "Rust defaults" in check.detail
        for check in checks
    )
    assert any(
        check.name == "docker/compose/docker-compose.app.yml"
        and "canonical gateway with Rust" in check.detail
        for check in checks
    )
    assert any(
        check.name == "gateway"
        and "source tree is removed" in check.detail
        for check in checks
    )
    assert any(
        check.name == "shared/capabilities/sync/service/agent.py"
        and "SyncModule" in check.detail
        for check in checks
    )
    assert any(
        check.name == "docker/compose/docker-compose.rust-gateway-prod-shadow.yml"
        and "separate host" in check.detail
        for check in checks
    )
    assert any(
        check.name == ".github/PULL_REQUEST_TEMPLATE.md"
        and "local and production Rust gateway evidence" in check.detail
        for check in checks
    )


def test_prod_migration_audit_requires_real_evidence() -> None:
    checks = evaluate_migration(
        Path.cwd(),
        require_prod_evidence=True,
        prod_report_path=Path(".artifacts/rust-gateway-shadow-compose-check.json"),
    )

    failed_required = [check for check in checks if check.required and not check.ok]

    assert [check.name for check in failed_required] == ["rust_gateway.production_evidence"]
