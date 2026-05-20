"""
OpenTelemetry tracing bootstrap.

Call ``init_tracing()`` at startup and ``shutdown_tracing()`` at shutdown.
Non-production runtimes without an OTLP endpoint still install a TracerProvider
with no exporter, so instrumentation and trace context stay active.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from shared.config import settings
from shared.utils.logger import get_logger

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

logger = get_logger("observability.tracing")

_tracer_provider: Optional["TracerProvider"] = None


def init_tracing(service_name: str | None = None) -> Optional["TracerProvider"]:
    """
    Create and register a global TracerProvider.

    Production-like runtimes require an OTLP endpoint. Non-production runtimes
    fall back to a provider with no span processor/exporter.
    """
    global _tracer_provider

    if _tracer_provider is not None:
        return _tracer_provider

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = settings.resolved_otel_endpoint
    service = service_name or settings.otel_service_name
    if settings.app_env.lower() in {"production", "prod"} and not endpoint:
        raise RuntimeError(
            "production tracing requires OTEL_ENDPOINT or OTEL_EXPORTER_OTLP_ENDPOINT"
        )

    resource = Resource.create(
        {"service.name": service}
    )
    provider = TracerProvider(resource=resource)
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        exporter_mode = "otlp"
    else:
        exporter_mode = "none"

    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    logger.info(
        "otel_tracing_enabled",
        endpoint=endpoint or "none",
        exporter_mode=exporter_mode,
        service=service,
    )
    return provider


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI app with OpenTelemetry (if tracing is active)."""
    if _tracer_provider is None:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    logger.info("otel_fastapi_instrumented")


def instrument_httpx() -> None:
    """Instrument httpx client calls (if tracing is active)."""
    if _tracer_provider is None:
        return
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()
    logger.info("otel_httpx_instrumented")


def shutdown_tracing() -> None:
    """Flush and shutdown the global TracerProvider."""
    global _tracer_provider
    if _tracer_provider is None:
        return
    _tracer_provider.shutdown()
    _tracer_provider = None
    logger.info("otel_tracing_shutdown")
