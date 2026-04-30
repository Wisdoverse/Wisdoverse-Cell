"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[GlobalError]", error.digest, error);
    import("@sentry/nextjs")
      .then((Sentry) => Sentry.captureException(error))
      .catch((err) => console.warn("[GlobalError] Failed to load Sentry:", err));
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
          backgroundColor: "#fafafa",
          color: "#111",
        }}
      >
        <div
          style={{
            textAlign: "center",
            maxWidth: 420,
            padding: 32,
            border: "1px solid #e5e5e5",
            borderRadius: 12,
            backgroundColor: "#fff",
            boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
          }}
        >
          <div
            style={{
              width: 48,
              height: 48,
              margin: "0 auto 16px",
              borderRadius: "50%",
              backgroundColor: "#fef2f2",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 24,
            }}
          >
            !
          </div>
          <h1
            style={{
              fontSize: 20,
              fontWeight: 600,
              marginBottom: 8,
            }}
          >
            Something went wrong
          </h1>
          <p
            style={{
              fontSize: 14,
              color: "#666",
              marginBottom: 24,
              lineHeight: 1.5,
            }}
          >
            An unexpected error occurred. Please reload the page to try again.
          </p>
          <button
            onClick={() => reset()}
            style={{
              padding: "8px 20px",
              fontSize: 14,
              fontWeight: 500,
              color: "#fff",
              backgroundColor: "#111",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Reload Page
          </button>
          <p
            style={{
              marginTop: 16,
              fontSize: 12,
              color: "#999",
            }}
          >
            Wisdoverse Cell
          </p>
        </div>
      </body>
    </html>
  );
}
