# API Guidelines

Last updated: 2026-05-18

Status: Foundation document.

This document is the contract every new or modified HTTP/REST/RPC route must
follow. It is binding for `agents/*/api/`, `services/gateways/*/api/`,
`shared/control_plane/api.py`, and the gRPC servers under
`agents/requirement_manager/grpc/` (and any later runtime gRPC entry).

The current implementation map lives in
[`docs/guides/api-reference.md`](../guides/api-reference.md). This document
defines the rules that the API reference must conform to.

---

## 1. URI and Versioning

1. Public routes live under `/api/v1/*`. New breaking changes ship a
   `/api/v2/*` parallel surface; never break `/api/v1`.
2. Per-agent wakeup endpoints expose `/agent/<agent_id>/*` (already
   established by `create_agent_app()`).
3. Internal endpoints live under `/internal/*`; they require
   `X-Internal-Key` authentication.
4. Webhook endpoints live under `/webhook/*` and verify the platform
   signature before any business logic runs.
5. URLs use kebab-case path segments. Route segments map to resource
   nouns; verbs live in the HTTP method.

---

## 2. Request and Response Shape

### 2.1 DTOs

1. Every request and every response body is a Pydantic v2 model.
2. DTOs live in `agents/<a>/api/schemas.py` (or `agents/<a>/models/`) per
   runtime. Cross-runtime DTOs are not shared; integration uses events or
   versioned HTTP contracts instead.
3. `model_config = ConfigDict(extra="forbid")` for inbound DTOs.
4. Use `model_dump_json()` (not `json()`) on Pydantic v2 models.
5. Field names are `snake_case`. Path parameters and query parameters use
   `snake_case`. Avoid abbreviations.

### 2.2 Success Responses

1. 2xx responses always carry a body except for `204 No Content`.
2. Pagination uses cursor pagination
   (`{ "items": [...], "next_cursor": "..." | null }`) when a list can grow
   without bound. Page-and-limit pagination is allowed for bounded lists
   only.
3. Timestamps are ISO 8601 with timezone (`2026-05-18T08:07:13Z`).

### 2.3 Error Responses

1. The error envelope is:
   ```json
   {
     "code": "<namespaced_error_code>",
     "message": "<human-readable message>",
     "trace_id": "<X-Trace-ID value>",
     "details": null | { "field": "value", ... }
   }
   ```
   The legacy FastAPI `detail` string is preserved in parallel until clients
   migrate.
2. Every error response carries an `X-Error-Code` header **and** an
   `X-Trace-ID` header.
3. Error codes are namespaced as `<runtime>.<category>.<specific>` and
   declared in the `ApiErrorCode` enum in `shared/api/errors.py`.
4. 4xx responses indicate caller errors; 5xx responses indicate server
   errors. Auth failures use 401 (missing) or 403 (forbidden).
5. Validation failures use 422 with `details` populated.
6. Rate limits use 429 with a `Retry-After` header.

---

## 3. Handlers

1. Route handlers are thin: validate input → build use-case command →
   invoke → map output → translate domain errors to HTTP errors.
2. Route handlers do not contain business rules.
3. Route handlers do not own the transaction boundary. Use cases do.
4. Route handlers receive collaborators through FastAPI `Depends`, not by
   reaching into global state.
5. Route handlers must not accept `AsyncSession` directly. Receive a
   use-case object or a session-provider port that hides the session
   (target: closes Phase 1 audit H5).

---

## 4. Authentication and Authorization

1. Public surfaces use the production auth contract (operator OAuth or
   per-deployment token). Document it in the API reference.
2. Internal endpoints require `X-Internal-Key` (see
   `shared/middleware/internal_auth.py`).
3. Webhook endpoints verify the platform signature **before** any
   side-effecting code runs.
4. Authorization decisions are made in the application layer (use case),
   not in the route handler.
5. Auth failures return the error envelope above; never expose the
   internal reason for failure.

---

## 5. Documentation

1. Every new route ships with an entry in
   `docs/guides/api-reference.md`.
2. Per-agent OpenAPI snapshots are generated and committed under
   `docs/api/openapi/<runtime>-v1.json`. Snapshot diffs reveal contract
   changes in PR review.
3. `X-Error-Code` values are listed in the same document and kept in sync
   with the `ApiErrorCode` enum.

---

## 6. Compatibility

1. Backward-compatible changes are allowed without bumping the version:
   adding optional fields to responses, adding new endpoints, accepting
   additional optional query parameters.
2. Breaking changes ship under a new version (`/api/v2/*`). The old version
   continues to serve until the documented sunset date.
3. A field that becomes nullable is a breaking change; treat it as such.
4. Renaming a field is breaking; ship a parallel field, deprecate the old
   one, remove only after the sunset date.

---

## 7. Idempotency

1. Mutating endpoints support an `Idempotency-Key` header when retry-safe
   behavior matters (e.g., approval submissions, agent wakeups).
2. The application layer deduplicates by `(<route>, <idempotency_key>)` and
   returns the same response for a repeated key within a documented window.

---

## 8. Performance

1. Each route declares an SLO (P95 and P99 latency) in the API reference.
2. Long-running operations return `202 Accepted` with a status URI; the
   client polls or subscribes to events.
3. Streaming endpoints (SSE/WebSocket) live under `/api/v1/stream/*` and
   are documented separately.

---

## 9. Testing

1. Every public route has at least one HTTP contract test (snapshot of
   request and response shape).
2. OpenAPI snapshot is regenerated and committed in the same PR as a route
   change.
3. Error-envelope tests assert `code`, `message`, `trace_id`,
   `X-Error-Code`, and `X-Trace-ID` are all populated.
4. Authentication and authorization tests cover happy path and at least
   one failure per credential class.

---

## 10. Maintenance

When this document changes:

- Update `docs/guides/api-reference.md`.
- Update `shared/api/errors.py` if the error envelope or code namespace
  changes.
- Update `tests/unit/test_api_errors.py` to enforce the new contract.
