"""
OpenTelemetry tracing bootstrap.

Call ``init_tracing()`` at startup and ``shutdown_tracing()`` at shutdown.
If ``settings.otel_endpoint`` is empty, all functions are no-ops.
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
    Create and register a global TracerProvider with OTLP exporter.

    Returns None (no-op) when ``otel_endpoint`` is not configured.
    """
    global _tracer_provider

    endpoint = settings.otel_endpoint
    if not endpoint:
        logger.info("otel_tracing_disabled", reason="otel_endpoint not set")
        return None

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {"service.name": service_name or settings.otel_service_name}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    logger.info(
        "otel_tracing_enabled",
        endpoint=endpoint,
        service=service_name or settings.otel_service_name,
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
