/**
 * Web Vitals Reporting
 *
 * Measures and reports Core Web Vitals metrics:
 *  - LCP (Largest Contentful Paint) - loading performance
 *  - CLS (Cumulative Layout Shift) - visual stability
 *  - INP (Interaction to Next Paint) - interactivity (replaced FID)
 *  - FCP (First Contentful Paint) - perceived load speed
 *  - TTFB (Time to First Byte) - server response time
 *
 * Metrics are sent to a configurable collector endpoint or logged to the console.
 *
 * Usage:
 *   Import and call `reportWebVitals()` in a client-side layout or root component.
 *
 * @see https://web.dev/articles/vitals
 */

import type { Metric } from "web-vitals";

type MetricReporter = (metric: Metric) => void;

/**
 * Send a Web Vitals metric to the analytics collector endpoint.
 * Falls back to console logging in development or when no endpoint is configured.
 */
const sendToCollector: MetricReporter = (metric) => {
  const endpoint = process.env.NEXT_PUBLIC_VITALS_ENDPOINT;

  const body = JSON.stringify({
    name: metric.name,
    value: metric.value,
    rating: metric.rating,
    delta: metric.delta,
    id: metric.id,
    navigationType: metric.navigationType,
    timestamp: Date.now(),
    url: typeof window !== "undefined" ? window.location.href : "",
  });

  if (endpoint) {
    // Use sendBeacon for reliable delivery even during page unload
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon(endpoint, blob);
    } else {
      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
      }).catch(() => {
        // Silently ignore network errors for metrics reporting
      });
    }
  }

  // Always log in development for debugging
  if (process.env.NODE_ENV === "development") {
    const ratingColor =
      metric.rating === "good"
        ? "\x1b[32m" // green
        : metric.rating === "needs-improvement"
          ? "\x1b[33m" // yellow
          : "\x1b[31m"; // red
    console.log(
      `[web-vitals] ${metric.name}: ${ratingColor}${metric.value.toFixed(2)}\x1b[0m (${metric.rating})`,
    );
  }
};

/**
 * Initialize Web Vitals reporting.
 *
 * Registers observers for all Core Web Vitals metrics.
 * Safe to call multiple times; the web-vitals library handles deduplication.
 *
 * @param onMetric - Optional custom reporter. If not provided, metrics are sent
 *                   to NEXT_PUBLIC_VITALS_ENDPOINT and/or logged to console.
 */
export function reportWebVitals(onMetric?: MetricReporter): void {
  if (typeof window === "undefined") return;

  const reporter = onMetric ?? sendToCollector;

  // Dynamic import to keep the web-vitals library out of the critical path
  import("web-vitals")
    .then(({ onCLS, onFCP, onINP, onLCP, onTTFB }) => {
      onCLS(reporter);
      onFCP(reporter);
      onINP(reporter);
      onLCP(reporter);
      onTTFB(reporter);
    })
    .catch((err) => {
      console.warn("[web-vitals] Failed to load web-vitals library:", err);
    });
}
