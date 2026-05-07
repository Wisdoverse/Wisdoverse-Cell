"""Static contracts for the Rust gateway migration boundary."""

from pathlib import Path


def test_rust_gateway_preserves_go_gateway_public_routes() -> None:
    """The Rust gateway must keep public route parity with the legacy Go rollback path."""
    go_main = Path("gateway/cmd/gateway/main.go").read_text(encoding="utf-8")
    rust_routes = Path("rust/gateway/src/routes.rs").read_text(encoding="utf-8")
    compose = Path("docker/compose/docker-compose.app.yml").read_text(encoding="utf-8")

    assert 'router.GET("/health", healthHandler.Health)' in go_main
    assert 'router.GET("/ready", healthHandler.Ready)' in go_main
    assert 'api.POST("/feishu/webhook", feishuHandler.Webhook)' in go_main
    assert 'api.GET("/wecom/webhook", wecomHandler.Webhook)' in go_main
    assert 'api.POST("/wecom/webhook", wecomHandler.Webhook)' in go_main

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

    assert "rust-gateway:" in workflow
    assert "cargo fmt --manifest-path rust/Cargo.toml --check" in workflow
    assert "cargo test --manifest-path rust/Cargo.toml --locked" in workflow
    assert (
        "cargo clippy --manifest-path rust/Cargo.toml --all-targets --locked -- -D warnings"
        in workflow
    )
    assert "cargo build --manifest-path rust/Cargo.toml --locked -p projectcell-rust-gateway" in workflow
    assert "docker build -f rust/gateway/Dockerfile -t projectcell/rust-gateway:ci ." in workflow
