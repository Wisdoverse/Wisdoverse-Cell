# Service Boundaries

Last updated: 2026-05-18

Status: Foundation document.

This document is the standalone decision matrix for "should this runtime be
its own deployable service yet?". It is binding for every conversation that
proposes splitting or merging a runtime.

It consolidates [Backend Target Architecture](./backend-target-architecture.md)
§4.4 and the split-fitness rows in
[Module Boundaries](./module-boundaries.md) §2.

---

## 1. Default Posture

The default backend posture is **modular monolith**. Stay there until a
runtime meets every split pre-condition. Splitting prematurely creates
dual-write hazards, unrecoverable replay state, and operator surface area
that does not pay back.

We split when **all four** of these are true for a runtime:

1. Outbox + projection + idempotency + replay are in place.
2. Per-runtime migrations land cleanly.
3. Operator dashboards (metrics + tracing) cover the boundary.
4. At least one non-production deployment proves the split under realistic
   load.

If any of these is missing, the answer to "extract X" is "not yet".

---

## 2. Ten Criteria

When evaluating a runtime for extraction, score each criterion explicitly
and write the result into the PR or design document. The criteria mirror
the senior-architect brief.

| # | Criterion | Question to answer |
|---|-----------|---------------------|
| 1 | Clear business boundary | Does the runtime own a single bounded context with documented aggregates? |
| 2 | Independent data ownership | Are all owned tables write-restricted to this runtime, with no shared write paths? |
| 3 | Independent deploy need | Is there a real reason to deploy this runtime separately from the bundled `cell` container? |
| 4 | Independent scale need | Is the load profile materially different from neighbors (burstier, more concurrent, more expensive per call)? |
| 5 | Failure isolation need | Does a failure of a neighbor runtime currently take this runtime down, or vice versa, in a way that matters to operators? |
| 6 | Different change rate | Does this runtime change at a different cadence (e.g., daily vs monthly) from neighbors? |
| 7 | Performance bottleneck | Is the runtime currently bottlenecked by sharing process resources (event loop, DB pool, CPU)? |
| 8 | Collaboration bottleneck | Is the runtime owned by a different person/team whose ownership is hindered by being in the monolith? |
| 9 | Over-split risk | What is the cost of premature extraction (operator surface, deployment complexity, distributed-debug burden)? |
| 10 | Pre-conditions met | Are the four "all four" pre-conditions above true today? |

A green answer on criterion 1, 2, and 10 is required. Criteria 3–9 build the
business case.

---

## 3. Current Verdicts

These verdicts are derived from the analysis on `main` at commit
`751c1e1b3 refactor(backend): modularize service boundaries (#121)`.

| Runtime | Boundary | Data | Deploy need | Scale need | Failure isolation | Change rate | Perf | Collab | Over-split risk | Pre-conditions met | Verdict |
|---------|----------|------|-------------|------------|-------------------|-------------|------|--------|-----------------|--------------------|---------|
| Dev Agent | Yes | Yes | Soon (long workflows) | Yes | Yes | Yes | Likely | Medium | Low | No | Extract after Migration Plan Stage 3 |
| QA Agent | Yes | Yes | Soon | Yes | Yes | Yes | Possible | Medium | Low | No | Extract after Migration Plan Stage 3 |
| Sync — OpenProject | Yes | Yes (sync schema) | Medium | Medium | Yes | Yes | Possible | Low | Medium | No | Sub-runtime split before full extraction |
| Sync — Feishu Bitable | Yes | Yes | Medium | Medium | Yes | Yes | Possible | Low | Medium | No | Sub-runtime split before full extraction |
| Coordinator | Medium | Partial | Low | Low | Yes | Medium | No | Medium | Medium | No | Keep modular; stabilize durable state first |
| Analysis | Medium | Partial | Low | Low | Yes | Low | No | Low | High | No | Keep modular; build projection first |
| Evolution | Medium | Yes | Low | Low | Yes | Low | No | Low | Medium | No | Keep modular; harden approval/rollback first |
| Requirement Manager | Yes | Yes | Medium | Medium | Yes | Yes | No | Medium | Medium | No | Keep modular; extract after Dev/QA pattern proves |
| PJM | Yes | Yes | Low | Low | Yes | Medium | No | Medium | Medium | No | Keep modular; pair with sync sub-split |
| Identity / User | No | Partial | Low | Low | Yes | Low | No | Low | High | No | Define API first; do not split runtime |
| Interaction / Channel Gateway | Gateway only | Gateway-local only | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Gateway boundary; never split as business service |
| Integration Plane (Feishu/WeCom/OpenProject/GitLab/AgentForge) | Adapter library | None | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Library; never split |

---

## 4. Extraction Playbook (When a Runtime Is Ready)

Each extraction follows the same sequence. Do not skip steps.

1. Confirm the four pre-conditions above are green. Cite evidence (dashboard
   links, migration test runs, projection table existence, replay rehearsal).
2. Cut the runtime's tables into a dedicated Postgres schema (or database).
3. Move the runtime's migrations into a per-runtime Alembic directory.
4. Switch its EventBus subscriptions from in-process to remote consumer
   groups; verify DLQ behavior and replay.
5. Publish per-agent OpenAPI snapshot; commit it under `docs/`.
6. Deploy as a separate container in staging. Run the canary monitor for at
   least two weeks.
7. Document the rollback (revert to the bundled `cell` topology and replay
   from outbox).
8. Promote only when SLIs are green: outbox lag bounded, no DLQ growth,
   request P95/P99 inside SLO, error rate inside SLO.

---

## 5. Reverse Rule

Splits are reversible. If a separately deployed runtime adds operator pain
without paying back, merge it back into `cell`. Use the same playbook in
reverse and treat the merge as an architecture event (cite evidence; update
this document).

---

## 6. Maintenance

When this document changes:

- Update [`module-boundaries.md`](./module-boundaries.md) §2 split-fitness
  rows in the same PR.
- Update `docs/guides/backend-boundaries.md` §2 service-extraction posture.
- Update `docs/architecture/backend-target-architecture.md` §4.4 matrix.
