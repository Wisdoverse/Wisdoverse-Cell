/**
 * Browser-side OpenTelemetry Initialization
 *
 * Initializes distributed tracing in the browser using @opentelemetry/sdk-trace-web.
 * Propagates trace context via the W3C `traceparent` header so that browser-initiated
 * requests are linked to backend traces in Jaeger/Tempo.
 *
 * Usage:
 *   Import and call `initBrowserTelemetry()` once in a client-side layout or
 *   root component (e.g., inside a useEffect).
 */

import {
  WebTracerProvider,
  BatchSpanProcessor,
} from "@opentelemetry/sdk-trace-web";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { ATTR_SERVICE_NAME } from "@opentelemetry/semantic-conventions";
import {
  W3CTraceContextPropagator,
  CompositePropagator,
} from "@opentelemetry/core";
import { context, propagation, trace } from "@opentelemetry/api";

let initialized = false;

/**
 * Initialize browser-side OpenTelemetry tracing.
 *
 * Safe to call multiple times; subsequent calls are no-ops.
 * Gracefully degrades if the OTLP endpoint is unavailable.
 */
export function initBrowserTelemetry(): void {
  if (initialized) return;
  if (typeof window === "undefined") return;

  try {
    const endpoint = process.env.NEXT_PUBLIC_OTEL_ENDPOINT;

    if (!endpoint) {
      console.info(
        "[telemetry:browser] No NEXT_PUBLIC_OTEL_ENDPOINT configured, skipping browser tracing",
      );
      return;
    }

    const resource = resourceFromAttributes({
      [ATTR_SERVICE_NAME]: "project-cell-frontend-browser",
      "deployment.environment": process.env.NODE_ENV || "development",
    });

    const exporter = new OTLPTraceExporter({
      url: `${endpoint.replace(/\/$/, "")}/v1/traces`,
    });

    const provider = new WebTracerProvider({
      resource,
      spanProcessors: [new BatchSpanProcessor(exporter)],
    });

    // Register W3C Trace Context propagation for distributed tracing
    const propagator = new CompositePropagator({
      propagators: [new W3CTraceContextPropagator()],
    });

    provider.register({
      propagator,
    });

    // Set global propagation so fetch/XHR automatically include traceparent
    propagation.setGlobalPropagator(propagator);

    initialized = true;
    console.info(
      `[telemetry:browser] OpenTelemetry initialized (endpoint: ${endpoint})`,
    );
  } catch (err) {
    console.warn(
      "[telemetry:browser] Failed to initialize OpenTelemetry, continuing without tracing:",
      err,
    );
  }
}

/**
 * Get the browser tracer for creating custom spans.
 *
 * @example
 * ```ts
 * const tracer = getBrowserTracer();
 * const span = tracer.startSpan('user-action');
 * // ... do work ...
 * span.end();
 * ```
 */
export function getBrowserTracer() {
  return trace.getTracer("project-cell-frontend-browser", "1.0.0");
}

/**
 * Inject trace context headers into a fetch request's headers.
 * Useful for manually propagating trace context in custom fetch calls.
 *
 * @example
 * ```ts
 * const headers = injectTraceHeaders({ 'Content-Type': 'application/json' });
 * fetch('/api/data', { headers });
 * ```
 */
export function injectTraceHeaders(
  headers: Record<string, string> = {},
): Record<string, string> {
  const carrier: Record<string, string> = { ...headers };
  propagation.inject(context.active(), carrier);
  return carrier;
}
