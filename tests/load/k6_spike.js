/**
 * Spike Test — Sudden traffic surge and recovery.
 *
 * 10 → 500 VUs in 10s, hold 30s, drop to 10. Tests rate limiting
 * behavior and system recovery under sudden load spikes.
 * Run: k6 run tests/load/k6_spike.js
 */
import http from "k6/http";
import { sleep } from "k6";
import { BASE_URL, checkResponse } from "./utils/helpers.js";

export const options = {
  stages: [
    { duration: "30s", target: 10 }, // Warm up
    { duration: "10s", target: 500 }, // SPIKE to 500
    { duration: "30s", target: 500 }, // Hold spike
    { duration: "10s", target: 10 }, // DROP to 10
    { duration: "1m", target: 10 }, // Recovery
    { duration: "20s", target: 0 }, // Cool down
  ],
  thresholds: {
    // Relaxed thresholds — expect some failures during spike
    http_req_duration: ["p(95)<3000"],
    http_req_failed: ["rate<0.05"], // Allow up to 5% errors (rate limiting)
  },
};

export default function () {
  const roll = Math.random();

  if (roll < 0.4) {
    const r = http.get(`${BASE_URL}/health`);
    checkResponse(r, "health", 500);
  } else if (roll < 0.7) {
    const r = http.get(`${BASE_URL}/api/v1/requirements`);
    checkResponse(r, "list-requirements", 2000);
  } else {
    const r = http.get(`${BASE_URL}/api/v1`);
    checkResponse(r, "api-info", 1000);
  }

  sleep(Math.random() * 0.5 + 0.1); // Aggressive pacing during spike
}
