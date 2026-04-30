/**
 * Smoke Test — Quick sanity check.
 *
 * 10 VUs for 1 minute. Validates all critical endpoints respond correctly.
 * Run: k6 run tests/load/k6_smoke.js
 */
import http from "k6/http";
import { sleep } from "k6";
import { BASE_URL, checkResponse } from "./utils/helpers.js";

export const options = {
  vus: 10,
  duration: "1m",
  thresholds: {
    http_req_duration: ["p(95)<200"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  // Health liveness (50% weight)
  const r1 = http.get(`${BASE_URL}/health`);
  checkResponse(r1, "health", 100);
  sleep(0.5);

  // Health readiness (30% weight)
  if (Math.random() < 0.6) {
    const r2 = http.get(`${BASE_URL}/health/ready`);
    checkResponse(r2, "health/ready", 500);
    sleep(0.5);
  }

  // API info (20% weight)
  if (Math.random() < 0.4) {
    const r3 = http.get(`${BASE_URL}/api/v1`);
    checkResponse(r3, "api/v1", 200);
    sleep(0.5);
  }

  sleep(1);
}
