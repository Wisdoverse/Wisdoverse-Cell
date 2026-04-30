/**
 * Load Test — Normal production-like traffic.
 *
 * Ramps to 100 VUs over 2 min, sustains 5 min, ramps down 1 min.
 * Validates the system handles expected production load.
 * Run: k6 run tests/load/k6_load.js
 */
import http from "k6/http";
import { sleep } from "k6";
import {
  BASE_URL,
  checkResponse,
  jsonHeaders,
  randomMeetingContent,
} from "./utils/helpers.js";

export const options = {
  stages: [
    { duration: "2m", target: 100 }, // Ramp up
    { duration: "5m", target: 100 }, // Sustain
    { duration: "1m", target: 0 }, // Ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<500", "p(99)<1000"],
    http_req_failed: ["rate<0.001"],
  },
};

export default function () {
  const roll = Math.random();

  if (roll < 0.3) {
    // 30%: Health check
    const r = http.get(`${BASE_URL}/health`);
    checkResponse(r, "health", 100);
  } else if (roll < 0.6) {
    // 30%: List requirements
    const r = http.get(`${BASE_URL}/api/v1/requirements`);
    checkResponse(r, "list-requirements", 500);
  } else if (roll < 0.8) {
    // 20%: Search requirements
    const q = ["auth", "payment", "dashboard", "api", "mobile"][
      Math.floor(Math.random() * 5)
    ];
    const r = http.get(`${BASE_URL}/api/v1/requirements/search?q=${q}`);
    checkResponse(r, "search-requirements", 1000);
  } else if (roll < 0.9) {
    // 10%: Ingest meeting
    const meeting = randomMeetingContent();
    const r = http.post(
      `${BASE_URL}/api/v1/ingest/upload`,
      JSON.stringify(meeting),
      jsonHeaders,
    );
    checkResponse(r, "ingest-upload", 2000);
  } else {
    // 10%: Export PRD
    const r = http.get(`${BASE_URL}/api/v1/export/prd`);
    checkResponse(r, "export-prd", 2000);
  }

  sleep(Math.random() * 2 + 0.5); // 0.5-2.5s think time
}
