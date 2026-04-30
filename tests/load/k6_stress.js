/**
 * Stress Test — Find the breaking point.
 *
 * Ramps 0 → 200 → 500 → 200 → 0 VUs over ~15 min.
 * Identifies system limits and degradation patterns.
 * Run: k6 run tests/load/k6_stress.js
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
    { duration: "2m", target: 200 }, // Ramp to 200
    { duration: "3m", target: 200 }, // Hold at 200
    { duration: "2m", target: 500 }, // Push to 500
    { duration: "3m", target: 500 }, // Hold at 500
    { duration: "2m", target: 200 }, // Step down
    { duration: "1m", target: 0 }, // Ramp down
  ],
  thresholds: {
    http_req_duration: ["p(99)<2000"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const roll = Math.random();

  if (roll < 0.3) {
    const r = http.get(`${BASE_URL}/health`);
    checkResponse(r, "health", 200);
  } else if (roll < 0.6) {
    const r = http.get(`${BASE_URL}/api/v1/requirements`);
    checkResponse(r, "list-requirements", 1000);
  } else if (roll < 0.8) {
    const q = ["auth", "payment", "dashboard"][
      Math.floor(Math.random() * 3)
    ];
    const r = http.get(`${BASE_URL}/api/v1/requirements/search?q=${q}`);
    checkResponse(r, "search-requirements", 1500);
  } else if (roll < 0.9) {
    const meeting = randomMeetingContent();
    const r = http.post(
      `${BASE_URL}/api/v1/ingest/upload`,
      JSON.stringify(meeting),
      jsonHeaders,
    );
    checkResponse(r, "ingest-upload", 3000);
  } else {
    const r = http.get(`${BASE_URL}/api/v1/export/prd`);
    checkResponse(r, "export-prd", 3000);
  }

  sleep(Math.random() * 1.5 + 0.3); // Shorter think time under stress
}
