# Identity / User Boundary Contract

Last updated: 2026-05-18

Status: Foundation document. Stage 3 deliverable per
[`migration-plan.md`](./migration-plan.md) §Stage 3 item 3 (Identity /
User write-owner path).

This document is the binding contract for the `users` table and the
identity boundary in the backend. It closes the Phase 1 audit gap H9 /
P1-5 ("`users` lacks a dedicated public user/profile API boundary"):
the table now has one documented write owner.

## 1. Bounded Context

| Field | Value |
|-------|-------|
| Boundary name | Identity / User |
| Runtime owner | `shared/messaging/inbound/user_service.py` |
| Persistence owner | `shared/db/user_store.py` (`SqlAlchemyUserIdentityStore`) |
| Port contract | `shared/core/identity_ports.py` (`UserIdentityStore` Protocol) |
| Repository implementation | `shared/db/repository.py` (`UserRepository`) |
| Tables owned | `users` |
| Migration | `migrations/versions/20260506_identity_users_table.py` |
| Domain model | `shared/models/user.py` (`User`), `shared/models/platform.py` (`Platform`) |

The identity boundary is intentionally narrow. It exists to map
platform-specific identifiers (Feishu, WeCom, Web, etc.) to a unified
`User` record. It does **not** own profile preferences, organizational
membership, or role assignments — those are control-plane concerns
(`shared/control_plane/agent_registry_*`).

## 2. Write Owner

There is exactly one write path to the `users` table:

```text
inbound message
   → shared/messaging/inbound/user_service.py
        → shared/core/identity_ports.UserIdentityStore  (Protocol)
        → shared/db/user_store.SqlAlchemyUserIdentityStore  (adapter)
        → shared/db/repository.UserRepository  (SQL)
        → users table
```

Rules:

1. No module outside `shared/messaging/inbound/user_service.py` may
   construct a `User` and persist it.
2. Repositories and stores for other runtimes (agents, capabilities,
   gateways, control plane) MUST NOT import `UserRepository`,
   `SqlAlchemyUserIdentityStore`, or `shared.models.user.User` for
   write purposes.
3. The `User` aggregate fields are persistence-managed; consumers who
   need user data fetch through the inbound user-service path or
   through a documented read path (§3).
4. Changes to the schema require a new migration plus an update to
   `docs/guides/backend-boundaries.md` §3.

The architecture-boundary test
`tests/unit/test_architecture_boundaries.py::test_inbound_user_service_uses_identity_store_port`
encodes the structural pieces of this contract.

## 3. Read Paths

Read access to users is allowed for runtimes that need to resolve a
platform-specific user id to the unified `User` model. The current
read paths are:

| Path | Caller | Purpose |
|------|--------|---------|
| `UserIdentityStore.get_by_platform_id` | Inbound message handlers | Resolve incoming Feishu/WeCom identity to a User row |
| `UserIdentityStore.get_by_email` | Bootstrap and admin paths | Resolve human-entered email to a User row |
| `UserIdentityStore.get_by_id` | Cross-boundary HTTP/event handlers | Hydrate a User from a unified `user_id` field |

Reads MUST also go through `UserIdentityStore`. Other runtimes that
need to know about a user (PJM, QA, Dev, Requirement, Control Plane)
should accept the `user_id` as part of their command/event payload and
resolve via the port — they MUST NOT join the `users` table from their
own repositories.

A future projection / read-model service (Stage 4) MAY consume
identity changes through an integration event so that analytics and
operator dashboards do not need to hit `UserIdentityStore` for every
row. Until that exists, ad-hoc denormalization is not allowed.

## 4. Public API Surface

No public HTTP route exposes user records today. When such a route is
added in a future PR:

1. It MUST live under `/api/v1/identity/users/*`.
2. Internal endpoints require `X-Internal-Key` per
   [`api-guidelines.md`](./api-guidelines.md).
3. Write endpoints MUST route through `UserIdentityStore` (never a
   raw `UserRepository`).
4. Response DTOs MUST NOT expose `User` ORM rows directly. Define a
   `UserView` Pydantic schema and copy fields explicitly.
5. The route MUST emit a `identity.user-created` / `identity.user-updated`
   integration event for downstream consumers (Stage 4 dependency).

Until the route exists, identity is an internal boundary. Inbound
messaging is its only entry point.

## 5. Forbidden Patterns

- Any runtime outside the identity boundary importing
  `shared.db.repository.UserRepository`.
- Any runtime outside the identity boundary importing
  `shared.db.user_store.SqlAlchemyUserIdentityStore` directly.
- Joining the `users` table from another runtime's SQL query.
- Storing a `User` ORM row in another runtime's cache, projection, or
  outbox payload. Pass the `user_id` and resolve on demand.
- Adding `users.*` columns for runtime-specific data. Such data
  belongs in the consuming runtime's own table, keyed by `user_id`.

## 6. Future Service Extraction

Identity is the natural candidate to extract into its own runtime when
all of the following hold:

1. A public API surface (§4) is in production.
2. At least one external consumer relies on `identity.user-*`
   integration events.
3. The `users` table is migrated to its own per-runtime Alembic
   directory (Migration Plan §Stage 4 pre-condition).
4. An operator dashboard tracks identity write rate and resolution
   latency.

Until all four hold, identity stays where it is. See
[`service-boundaries.md`](./service-boundaries.md) for the general
extraction criteria.

## 7. Maintenance

When this document changes:

- Update `docs/guides/backend-boundaries.md` §2 (identity row) and §3
  (table-ownership row).
- Update `tests/unit/test_architecture_boundaries.py` if a new
  structural rule applies.
- Update `docs/architecture/module-boundaries.md` §2.11.
- Update `docs/architecture/data-ownership.md` if read/write contract
  changes.
