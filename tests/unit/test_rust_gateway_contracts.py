"""Static contracts for the Rust gateway migration boundary."""

from pathlib import Path


def test_rust_gateway_owns_public_gateway_routes() -> None:
    """The Rust gateway is the only public gateway implementation."""
    rust_routes = Path("rust/gateway/src/routes.rs").read_text(encoding="utf-8")
    compose = Path("docker/compose/docker-compose.app.yml").read_text(encoding="utf-8")

    assert not Path("gateway").exists()
    assert '.route("/health", get(health))' in rust_routes
    assert '.route("/ready", get(ready))' in rust_routes
    assert '.route("/api/feishu/webhook", post(feishu_webhook))' in rust_routes
    assert (
        '.route("/api/wecom/webhook", get(wecom_verify).post(wecom_webhook))'
        in rust_routes
    )
    assert "traefik.http.routers.gateway.rule=PathPrefix(`/webhook`)" in compose
    assert '.route("/webhook/feishu", post(feishu_webhook))' in rust_routes
    assert (
        '.route("/webhook/wecom", get(wecom_verify).post(wecom_webhook))'
        in rust_routes
    )


def test_github_actions_runs_rust_gateway_cutover_checks() -> None:
    """Public CI must guard the Rust gateway as a first-class backend runtime."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "Go gateway tests" not in workflow
    assert "actions/setup-go" not in workflow
    assert "go test ./..." not in workflow
    assert "rust-gateway:" in workflow
    assert "cargo fmt --manifest-path rust/Cargo.toml --check" in workflow
    assert "cargo test --manifest-path rust/Cargo.toml --locked" in workflow
    assert (
        "cargo clippy --manifest-path rust/Cargo.toml --all-targets --locked -- -D warnings"
        in workflow
    )
    assert "cargo build --manifest-path rust/Cargo.toml --locked -p projectcell-rust-gateway" in workflow
    assert "docker build -f rust/gateway/Dockerfile -t projectcell/rust-gateway:ci ." in workflow
