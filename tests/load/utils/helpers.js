/**
 * Shared helpers for k6 load tests.
 */
import { check } from "k6";

export const BASE_URL = __ENV.BASE_URL || "http://traefik:80";

/**
 * Generate random meeting content for ingest endpoint.
 */
export function randomMeetingContent() {
  const topics = [
    "user authentication flow",
    "payment integration",
    "dashboard redesign",
    "API rate limiting",
    "mobile app notifications",
    "data export feature",
    "search optimization",
    "onboarding wizard",
  ];
  const topic = topics[Math.floor(Math.random() * topics.length)];
  const id = Math.floor(Math.random() * 100000);

  return {
    content: `Meeting #${id}: We discussed ${topic}. The team agreed we need to implement this by next sprint. Key requirements: 1) Must support 1000 concurrent users 2) Response time under 200ms 3) Full audit logging. Action items assigned to engineering team.`,
    source: "load_test",
    title: `Load Test Meeting ${id} - ${topic}`,
  };
}

/**
 * Standard response check — verifies status 200 and response time.
 */
export function checkResponse(res, name, maxDuration = 2000) {
  check(res, {
    [`${name}: status 200`]: (r) => r.status === 200,
    [`${name}: duration < ${maxDuration}ms`]: (r) =>
      r.timings.duration < maxDuration,
  });
}

/**
 * JSON POST headers.
 */
export const jsonHeaders = {
  headers: { "Content-Type": "application/json" },
};
