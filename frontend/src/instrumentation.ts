/**
 * Next.js Instrumentation Hook
 *
 * This file is automatically loaded by Next.js when the application starts.
 * It initializes OpenTelemetry for server-side distributed tracing and
 * Sentry for error monitoring.
 *
 * @see https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 */

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await registerNodeTracing();
  }
}

async function registerNodeTracing() {
  try {
    const { NodeSDK } = await import("@opentelemetry/sdk-node");
    const { OTLPTraceExporter } = await import(
      "@opentelemetry/exporter-trace-otlp-http"
    );
    const { resourceFromAttributes } = await import(
      "@opentelemetry/resources"
    );
    const { ATTR_SERVICE_NAME } = await import(
      "@opentelemetry/semantic-conventions"
    );

    const endpoint =
      process.env.OTEL_EXPORTER_OTLP_ENDPOINT ||
      process.env.OTEL_ENDPOINT ||
      "";

    // Skip initialization if no endpoint is configured
    if (!endpoint) {
      console.info(
        "[telemetry] No OTEL_EXPORTER_OTLP_ENDPOINT configured, skipping OpenTelemetry initialization",
      );
      return;
    }

    const traceExporter = new OTLPTraceExporter({
      url: `${endpoint.replace(/\/$/, "")}/v1/traces`,
    });

    const resource = resourceFromAttributes({
      [ATTR_SERVICE_NAME]: "wisdoverse-cell-frontend",
      "deployment.environment": process.env.APP_ENV || "development",
    });

    const sdk = new NodeSDK({
      resource,
      traceExporter,
    });

    sdk.start();

    // Gracefully shut down SDK on process exit
    const shutdown = async () => {
      try {
        await sdk.shutdown();
        console.info("[telemetry] OpenTelemetry SDK shut down successfully");
      } catch (err) {
        console.error("[telemetry] Error shutting down OpenTelemetry SDK", err);
      }
    };

    const processWithSignals = globalThis.process as
      | { on?: (event: string, listener: () => Promise<void>) => void }
      | undefined;
    const onSignal = processWithSignals?.on?.bind(processWithSignals);
    onSignal?.("SIGTERM", shutdown);
    onSignal?.("SIGINT", shutdown);

    console.info(
      `[telemetry] OpenTelemetry initialized for wisdoverse-cell-frontend (endpoint: ${endpoint})`,
    );
  } catch (err) {
    // Gracefully degrade if OTel initialization fails
    console.error(
      "[telemetry] Failed to initialize OpenTelemetry, continuing without tracing:",
      err,
    );
  }

  // Initialize Sentry for server-side error tracking
  try {
    const Sentry = await import("@sentry/nextjs");
    const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

    if (!dsn) {
      console.info(
        "[sentry] No NEXT_PUBLIC_SENTRY_DSN configured, skipping Sentry initialization",
      );
      return;
    }

    Sentry.init({
      dsn,
      environment: process.env.APP_ENV || "development",
      tracesSampleRate: process.env.APP_ENV === "production" ? 0.1 : 1.0,
      debug: process.env.APP_ENV === "development",
    });

    console.info("[sentry] Sentry initialized for server-side error tracking");
  } catch (err) {
    console.error(
      "[sentry] Failed to initialize Sentry, continuing without error tracking:",
      err,
    );
  }
}
