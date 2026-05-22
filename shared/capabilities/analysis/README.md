# Analysis Capability

Shared support capability that generates risk and operating reports
from operational evidence (work-package progress, delivery flow, quality
verdicts).

Canonical runtime ID: `analysis-module`.
See [`docs/architecture/module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.9.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `shared/capabilities/analysis/` |
| Owned tables | `analysis_agent_*` (`analysis_report_log`, `analysis_agent_event_outbox`) |
| Aggregate root | **None — DDD-004 introduces explicit projection-source records** |
| Domain services | `core/milestone_checker.py` `MilestoneChecker.check()`; `core/quality_evaluator.py` `QualityEvaluator.evaluate_all()` |
| Domain events | `event_use_cases.py:86-155` stages `REPORT_DAILY_GENERATED`, `ANALYSIS_RISK_DETECTED`, `ANALYSIS_QUALITY_EVALUATED`. |
| Open boundary violation | **Reads source-domain ports directly** (`OpenProjectWorkPackagePort`, Bitable port) — DDD-004 introduces a projection layer to remove this dependency. |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Report** | A scheduled or on-demand operating artifact. Two kinds today: `daily_report` and `weekly_report`. |
| **Risk signal** | A flagged condition emitted as an `ANALYSIS_RISK_DETECTED` event. Risk-level strings are not yet typed (DDD-008 / DDD-003 cleanup). |
| **Quality verdict** | An aggregated assessment of delivery quality derived from QA acceptance results. |
| **Milestone** | A trackable progress checkpoint against a goal. The `MilestoneChecker` evaluates these against work-package state. |
| **Projection** | The not-yet-implemented read model that Analysis will consume instead of source tables. See DDD-004. |

## Context-Map Relationships

Per [`module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.9:

- **Upstream (broken)**: Customer/Supplier to source-domain runtimes; currently reads OpenProject / Bitable ports directly rather than via projection. DDD-004 fix.
- **Downstream**: Customer/Supplier to all reporting consumers (emits `analysis.*` events).
- **Conformist** to Control Plane.

## Architecture

```
core/
  application_facade.py     composes use cases for the service shell
  daily_report.py           daily-report generator (uses source ports today)
  weekly_report.py          weekly-report generator
  milestone_checker.py      milestone domain service
  quality_evaluator.py      quality domain service
  event_use_cases.py        event handling + report-trigger flow
  request_use_cases.py      operator-facing commands
  outbox_delivery_use_cases.py
  outbox_ports.py
db/                         SQLAlchemy stores (ReportLog)
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../../docs/architecture/ddd-compliance-audit.md) §4.11.
