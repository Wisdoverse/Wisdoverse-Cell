import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {
    root: process.cwd(),
  },

  // Source maps are uploaded to Sentry via CI, not served to browsers
  productionBrowserSourceMaps: false,

  // Security headers applied to all routes
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=()",
          },
          { key: "X-DNS-Prefetch-Control", value: "on" },
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
          },
        ],
      },
    ];
  },
};

// Sentry configuration options
// These are applied via the Sentry webpack plugin at build time.
// Set NEXT_PUBLIC_SENTRY_DSN and SENTRY_AUTH_TOKEN to activate.
const sentryConfig = {
  // Suppresses source map upload logs during build
  silent: true,

  // Upload source maps to Sentry for readable stack traces
  // Requires SENTRY_AUTH_TOKEN and SENTRY_ORG / SENTRY_PROJECT env vars
  widenClientFileUpload: true,

  // Hides source maps from the client (recommended for production)
  hideSourceMaps: true,

  // Automatically tree-shake Sentry debug logging to reduce bundle size
  webpack: {
    treeshake: {
      removeDebugLogging: true,
    },
  },

  // Prevent Sentry from tunneling through the Next.js server
  // (use a dedicated Sentry tunnel endpoint in production if needed)
  tunnelRoute: undefined,
};

// Compose plugins: next-intl first, then Sentry wraps the result
export default withSentryConfig(withNextIntl(nextConfig), sentryConfig);
