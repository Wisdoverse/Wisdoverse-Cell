# Load Testing (k6)

Performance validation for the cloud-native Wisdoverse Cell stack using [k6](https://k6.io/).

## Quick Start

```bash
# Ensure the stack is running
make up-prod

# Run smoke test (10 VUs, 1 minute)
make load-smoke

# Run full load test (100 VUs, 8 minutes)
make load-test
```

## Test Scenarios

| Scenario | Command | VUs | Duration | Purpose |
|----------|---------|-----|----------|---------|
| Smoke | `make load-smoke` | 10 | 1 min | Quick sanity — all endpoints respond |
| Load | `make load-test` | 100 | 8 min | Normal production traffic simulation |
| Stress | `make load-stress` | 0→500 | 13 min | Find breaking point and degradation patterns |
| Spike | `make load-spike` | 10→500→10 | ~3 min | Rate limiting and recovery behavior |

## Script Files

```
tests/load/
├── k6_smoke.js          # Health + API info endpoints
├── k6_load.js           # Full endpoint mix (list, search, ingest, export)
├── k6_stress.js         # Progressive ramp to 500 VUs
├── k6_spike.js          # Sudden surge and recovery
└── utils/
    └── helpers.js        # Shared: BASE_URL, checkResponse, randomMeetingContent
```

## Endpoint Mix (load/stress)

| Endpoint | Weight | Max Duration |
|----------|--------|-------------|
| `GET /health` | 30% | 100ms |
| `GET /api/v1/requirements` | 30% | 500ms |
| `GET /api/v1/requirements/search` | 20% | 1000ms |
| `POST /api/v1/ingest/upload` | 10% | 2000ms |
| `GET /api/v1/export/prd` | 10% | 2000ms |

## Performance Targets

From the cloud-native design doc:

| Layer | Target QPS | P99 Latency |
|-------|-----------|-------------|
| Gateway (Rust) | > 10K | < 100ms |
| Requirements capability (Python) | > 5K | < 500ms (excl. LLM) |
| System under 50K QPS | Graceful degradation | Rate limiting active |

## Running Manually

```bash
# With Docker (recommended)
docker compose -f docker/compose/docker-compose.loadtest.yml \
  run --rm -e K6_SCRIPT=k6_load.js k6

# With local k6 binary
k6 run --env BASE_URL=http://localhost:80 tests/load/k6_load.js

# With JSON output for analysis
k6 run --out json=results.json tests/load/k6_load.js
```

## Monitoring During Tests

Open Grafana at `http://localhost:3000` during load tests to observe:
- **Service Overview** dashboard: Request rate, latency percentiles, error rate
- **Infrastructure** dashboard: CPU, memory, connection pools
- **NATS** dashboard: Message throughput and consumer lag
