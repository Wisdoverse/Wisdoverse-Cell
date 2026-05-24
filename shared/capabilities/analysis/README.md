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
| Aggregate root | `core/domain/report.py` `GeneratedAnalysisReport`; report-log persistence uses `core/domain/report_log.py` `AnalysisReportLogRecord`; projection value objects live in `core/domain/projection.py`; Feishu task snapshots live in `core/domain/feishu_task.py`; risk and quality assessment value objects live in `core/domain/assessment.py` |
| Application commands | `core/report_delivery_use_cases.py` owns the generate -> push -> integration-event boundary for daily and weekly reports. |
| Domain services | `core/milestone_checker.py` `MilestoneChecker.check()`; `core/quality_evaluator.py` `QualityEvaluator.evaluate_all()` |
| Domain events | `GeneratedAnalysisReport` raises `AnalysisReportGenerated` in-memory; `event_use_cases.py` stages `REPORT_DAILY_GENERATED`, `ANALYSIS_RISK_DETECTED`, `ANALYSIS_QUALITY_EVALUATED`. |
| Open boundary status | Report and milestone reads go through `WorkPackageProjectionPort`; the projection updater is the only report/risk read path that touches Feishu Bitable task rows and translates them into Analysis-owned projection snapshots. |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Report** | A scheduled or on-demand operating artifact. Two kinds today: `daily_report` and `weekly_report`. |
| **Generated report** | The aggregate for one generated Analysis report, including kind, summary, content, stats, and delivery status. |
| **Report log** | The persisted Analysis report-log entity snapshot. `AnalysisReportLogRecord` owns identity, kind, generated/pushed status, and push-transition validation before the SQLAlchemy adapter writes `analysis_agent_report_logs`. |
| **Report stats** | Immutable per-source task counts derived from `AnalysisFeishuTaskSnapshot` and Analysis work-package projections. |
| **Feishu task snapshot** | Analysis-owned published-language view of one projected Feishu task row: title, status, blocked reason, and optional record ID. |
| **Risk signal** | A flagged milestone condition emitted as an `ANALYSIS_RISK_DETECTED` event. `MilestoneRiskSignal`, `AnalysisRiskType`, and `AnalysisRiskSeverity` own the internal vocabulary before the event payload is serialized. |
| **Quality verdict** | A deliverable quality assessment derived from task metadata and LLM review. `QualityEvaluation`, `AnalysisQualityVerdict`, `DeliverableQualityTask`, and `DeliverableQualityResult` own the verdict, prompt metadata, and Feishu write-back field payload. |
| **Milestone** | A trackable progress checkpoint against a goal. The `MilestoneChecker` evaluates these against work-package state. |
| **Projection** | The Analysis-owned read model consumed instead of OpenProject and Feishu Bitable source reads. |

## Context-Map Relationships

Per [`module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.9:

- **Upstream**: Customer/Supplier to Sync / PJM through the Analysis-owned
  `WorkPackageProjectionPort` published-language read model. Anti-Corruption
  Layer to Feishu Bitable task records sits at the projection updater and
  `AnalysisFeishuTaskACL`; daily, weekly, and milestone risk reads consume
  the projection only.
- **Downstream**: Customer/Supplier to all reporting consumers (emits `analysis.*` events).
- **Conformist** to Control Plane.

## Architecture

```
core/
  application_facade.py     composes use cases for the service shell
  daily_report.py           daily-report generator
  weekly_report.py          weekly-report generator
  domain/assessment.py      milestone risk + quality assessment value objects
  domain/feishu_task.py     Feishu Bitable task ACL + Analysis snapshot
  domain/report.py          generated-report aggregate + report stats
  domain/report_log.py      report-log persistence entity + status mapping
  domain/projection.py      Analysis-owned work-package/subtask projections
  report_delivery_use_cases.py report generate -> push -> event command boundary
  milestone_checker.py      milestone domain service
  quality_evaluator.py      quality domain service
  event_use_cases.py        event handling + report-trigger flow
  request_use_cases.py      operator-facing commands
  outbox_delivery_use_cases.py
  outbox_ports.py
db/                         SQLAlchemy stores (ReportLog adapter mapping)
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../../docs/architecture/ddd-compliance-audit.md) §4.11.
