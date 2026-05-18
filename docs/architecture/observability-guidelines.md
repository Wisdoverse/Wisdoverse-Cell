# Observability Guidelines

Last updated: 2026-05-18

Status: Foundation document.

This document defines the minimum observability bar for the backend. It is
binding for every PR that adds or modifies a code path that crosses a
boundary (HTTP, RPC, event publish, external call, database write, long-
running task).

The current implementation lives in `shared/observability/`,
`shared/middleware/`, and `shared/utils/logger.py`. This document defines
what those packages must provide.

---

## 1. Stack of Record

- **Logs**: structlog JSON; one event per record; context fields bound via
  `RequestIdMiddleware`.
- **Traces**: OpenTelemetry with OTLP exporter. Always-on with a no-op
  exporter fallback when no endpoint is configured.
- **Metrics**: Prometheus exposition via `/metrics` on every agent and
  gateway (gated by `X-Internal-Key`). OpenTelemetry metrics later, after
  Prometheus baseline is stable.
- **Alerting**: Alertmanager rules in
  [`docs/guides/operations.md`](../guides/operations.md).

No new framework is introduced as part of Stage 0. The stack-of-record
decision is documented here so future PRs do not re-litigate it.

---

## 2. Required Signals

Mirrors the senior-architect brief's 10-item observability list.

| # | Requirement | Concrete target | Code seam |
|---|-------------|-----------------|-----------|
| 1 | requestId / correlationId | `X-Trace-ID` from `RequestIdMiddleware` propagated to outbound HTTP + EventBus event metadata | `shared/middleware/__init__.py` |
| 2 | Structured logging | structlog JSON + bound context (`trace_id`, `agent_id`, `work_item_id`, `run_id`, `approval_id`) | `shared/utils/logger.py` |
| 3 | Key business ID logging | Every use case logs `run_id`, `work_item_id`, `goal_id`, `approval_id` on entry and exit | logging helper consumed by all `*_use_cases.py` |
| 4 | Error logs | Classified errors (use `ApiErrorCode`); include `trace_id` and retry decision; never log secrets | `shared/api/errors.py`, `shared/middleware/error_handler.py` |
| 5 | External call latency | Histogram per integration call (Feishu, OpenProject, GitLab, AgentForge, LLM) | new `shared/observability/metrics.py` |
| 6 | DB slow query | Log queries above N ms (default 200 ms); emit `db_query_duration_seconds` histogram | SQLAlchemy event hook in `shared/db/` |
| 7 | MQ consumer state | Outbox-lag gauge, `dlq.failed` length, consumer-group pending count | dispatcher already collects totals; expose as metrics |
| 8 | Task processing state | Per-use-case state-transition counter + duration histogram; per-runtime task throughput | metric + log convention |
| 9 | Key endpoint P95 / P99 | Per-route latency histogram; SLO target in `operations.md` | FastAPI middleware metric |
| 10 | Failure rate + alerting | Outbox failure rate, DLQ rate, LLM budget breach, approval timeout — all alerted | Alertmanager rules documented in `operations.md` |

---

## 3. Logging

1. structlog JSON only. No print, no f-string into `logging.info`, no
   `print_exc`.
2. Bound context fields on every log line:
   `trace_id`, `agent_id`, `work_item_id`, `run_id`, `approval_id` where
   available.
3. Log levels:
   - `debug` — local-only; CI runs at `info`.
   - `info` — boundary crossings (HTTP request, event publish, external
     call entry/exit).
   - `warning` — recoverable failures (timeouts that retried, fallbacks).
   - `error` — unrecoverable for this attempt (after retries).
   - `critical` — operator must intervene (budget exhausted, DLQ
     overflow).
4. Never log secrets, tokens, signatures, raw PII, or full LLM prompts.
   Use `shared/observability/privacy.py` to scrub if needed.
5. Stack traces only at `error` and above, and only for unexpected
   exceptions.

---

## 4. Tracing

1. Every HTTP request is a span; child spans cover outbound calls (HTTP,
   gRPC, DB, EventBus publish, LLM).
2. `trace_id` propagates through:
   (a) HTTP headers (`X-Trace-ID` for human readability + W3C
   traceparent for OTel);
   (b) EventBus event metadata (`metadata.trace_id`);
   (c) outbound LLM gateway calls.
3. Spans carry attributes: `runtime.id`, `route.name`, `event.type`,
   `aggregate.id`, `error.code` (when failed).
4. OpenTelemetry is always-on; a no-op exporter is the fallback when
   `settings.otel_endpoint` is unset.
5. Sampling defaults to 100% for non-prod and a documented ratio (e.g.,
   10%) for prod; documented in `operations.md`.

---

## 5. Metrics

1. Every agent and gateway exposes `/metrics` (Prometheus). Internal-key
   protected.
2. Required metric families:
   - `http_request_duration_seconds` (histogram) per route + method +
     status.
   - `http_request_errors_total` (counter) per route + error code.
   - `event_outbox_pending_count` (gauge) per runtime + outbox.
   - `event_outbox_oldest_unsent_age_seconds` (gauge) per outbox.
   - `event_outbox_dispatcher_duration_seconds` (histogram) per
     dispatcher cycle.
   - `eventbus_dlq_failed_total` (counter) per consumer group.
   - `external_call_duration_seconds` (histogram) per integration +
     operation.
   - `llm_request_tokens_total` (counter) per model + direction.
   - `llm_cost_usd_total` (counter) per model.
   - `db_query_duration_seconds` (histogram) per agent.
3. Cardinality discipline: do not include user IDs or work item IDs in
   metric labels.
4. Naming follows Prometheus conventions: `<noun>_<unit>` with `_total`
   for counters and `_seconds` / `_bytes` for histograms.

---

## 6. Alerts

These are the minimum alerts. Tune thresholds per environment in
`operations.md`.

| Alert | Condition | Severity |
|-------|-----------|----------|
| Outbox-lag warning | `event_outbox_oldest_unsent_age_seconds` > 60 s for 5 min | Warning |
| Outbox-lag critical | > 5 min for 5 min | Critical |
| DLQ growing | `eventbus_dlq_failed_total` rate > 0 over 5 min | Critical |
| Route error spike | per-route 5xx rate > 1% over 10 min | Warning |
| LLM budget breach | budget usage > 90% of period | Warning |
| LLM budget hard breach | budget usage > 100% of period | Critical |
| Approval timeout | open approval older than its SLA | Warning |
| Trace export failure | OTel export failures > 10/min for 5 min | Warning |
| `/ready` failing | any agent `/ready` failing for 1 min | Critical |

---

## 7. SLOs

Each public route declares an SLO in
[`docs/guides/api-reference.md`](../guides/api-reference.md). The default
template:

- P95 latency target.
- P99 latency target.
- Error rate target (5xx + classified failures).
- Availability target (% of minutes per quarter the route serves
  successfully).

SLO breaches are tracked in a per-quarter retrospective.

---

## 8. Health Endpoints

1. Every agent and gateway exposes `/status` (current AgentRuntime status
   plugin response) and `/ready` (readiness, gates traffic).
2. `/status` is unauthenticated and returns minimal information.
3. `/ready` returns 200 when all critical plugins (database, outbox
   dispatcher, EventBus client, LLM Gateway) report healthy; 503 otherwise.

---

## 9. Documentation

1. Every new metric and alert is documented in `operations.md` in the
   same PR.
2. Every new structured log field is documented in
   `docs/guides/agent-development.md`.
3. SLO changes are documented in the API reference under the route.

---

## 10. Forbidden Patterns

- Unstructured logs (f-strings into `logging`).
- Secrets in logs, traces, or metric labels.
- High-cardinality metric labels (user/work-item/run IDs).
- Optional tracing in production. Tracing must be on; the exporter
  decision is the operator's, not the application's.
- Alerts without a documented runbook entry.

---

## 11. Maintenance

When this document changes:

- Update `docs/guides/operations.md` (alerts and runbooks).
- Update `shared/observability/` modules to match the contract.
- Update `tests/unit/test_logging_privacy.py` and related tests if a new
  privacy rule is introduced.
