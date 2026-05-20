"""Tests for shared OpenTelemetry bootstrap contracts."""

from types import SimpleNamespace

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from shared.observability import tracing


@pytest.fixture(autouse=True)
def reset_tracing_provider():
    """Keep tracing bootstrap tests isolated from the module-level provider."""
    previous = tracing._tracer_provider
    tracing._tracer_provider = None
    yield
    provider = tracing._tracer_provider
    tracing._tracer_provider = previous
    if provider is not None:
        provider.shutdown()


def test_init_tracing_installs_no_export_provider_without_endpoint(monkeypatch):
    captured: list[TracerProvider] = []
    monkeypatch.setattr(trace, "set_tracer_provider", captured.append)
    monkeypatch.setattr(
        tracing,
        "settings",
        SimpleNamespace(
            app_env="development",
            resolved_otel_endpoint="",
            otel_service_name="fallback-service",
        ),
    )

    provider = tracing.init_tracing(service_name="requirement-manager")

    assert isinstance(provider, TracerProvider)
    assert tracing._tracer_provider is provider
    assert captured == [provider]


def test_init_tracing_is_idempotent(monkeypatch):
    captured: list[TracerProvider] = []
    monkeypatch.setattr(trace, "set_tracer_provider", captured.append)
    monkeypatch.setattr(
        tracing,
        "settings",
        SimpleNamespace(
            app_env="development",
            resolved_otel_endpoint="",
            otel_service_name="fallback-service",
        ),
    )

    first = tracing.init_tracing(service_name="requirement-manager")
    second = tracing.init_tracing(service_name="pjm-agent")

    assert second is first
    assert captured == [first]


def test_init_tracing_fails_closed_in_production_without_endpoint(monkeypatch):
    monkeypatch.setattr(trace, "set_tracer_provider", lambda provider: None)
    monkeypatch.setattr(
        tracing,
        "settings",
        SimpleNamespace(
            app_env="production",
            resolved_otel_endpoint="",
            otel_service_name="ai-core",
        ),
    )

    with pytest.raises(RuntimeError, match="OTEL_ENDPOINT"):
        tracing.init_tracing(service_name="ai-core")

    assert tracing._tracer_provider is None
