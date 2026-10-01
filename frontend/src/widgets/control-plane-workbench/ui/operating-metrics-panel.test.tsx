import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const metricsHook = vi.hoisted(() => vi.fn());
vi.mock("@/entities/control-plane", () => ({ useControlPlaneOperatingMetrics: metricsHook }));
vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key} ${JSON.stringify(values)}` : key,
}));

import type { ControlPlaneOperatingMetrics } from "@/entities/control-plane";
import { OperatingMetricsPanel } from "./operating-metrics-panel";

const metrics: ControlPlaneOperatingMetrics = {
  company_id: "company-private",
  as_of_utc: "2026-10-01T12:00:00Z",
  export_policy: { retention_days: 90, applies_to: "exported snapshots" },
  runs: { total: 12, by_status: { succeeded: 8, failed: 2, running: 2 }, success_rate: 0.8, adapter_errors: 1 },
  queue_delay: { p95_seconds: 3.25, sample_size: 8, sample_limit: 1000, sampled_work_items: 10, excluded_without_run: 2, source: "created to first run" },
  approvals: { pending: 2, oldest_pending_age_seconds: 540 },
  costs: {
    accepted_outcome_count: 4, full_cost_usd_total: 5.75, full_cost_usd_per_accepted_outcome: 1.4375,
    full_cost_basis: "max reported or deduped", run_reported_cost_usd_total: 4, deduplicated_budget_usage_usd_total: 5.75,
    failed_run_reported_cost_usd: 0.5, failed_run_budget_charges_usd: 0.6, estimated_ceiling_usd_total: 8,
    estimated_ceiling_usd_per_accepted_outcome: 2, estimated_execution_count: 10,
    unestimated_execution_count: 2, budget_usage_run_coverage: 9, run_cost_coverage: 7, unmetered_run_count: 3,
  },
  unresolved_execution_leases: { count: 1, oldest_age_seconds: 600 },
  pending_outbox: { count: 3, oldest_age_seconds: 120 },
};

describe("OperatingMetricsPanel", () => {
  beforeEach(() => metricsHook.mockReset().mockReturnValue({ data: metrics, isLoading: false }));

  it("shows bounded queue sampling, outcomes, all-attempt cost, and coverage without leaking IDs", () => {
    render(<OperatingMetricsPanel companyId="company-private" />);
    expect(metricsHook).toHaveBeenCalledWith("company-private");
    expect(screen.getByText(/queueSample.*"size":8.*"sampled":10.*"cap":1000.*"excluded":2/)).toBeInTheDocument();
    expect(screen.getByText("acceptedOutcomes")).toBeInTheDocument();
    expect(screen.getByText(/allAttemptCost.*"cost":"5.75"/)).toBeInTheDocument();
    expect(screen.getByText(/unmeteredOfRuns.*"unmetered":"3".*"total":"12"/)).toBeInTheDocument();
    expect(screen.getByText("unresolvedLeases")).toBeInTheDocument();
    expect(screen.getByText("pendingOutbox")).toBeInTheDocument();
    expect(screen.queryByText("company-private")).not.toBeInTheDocument();
  });

  it("renders null metric values as unknown rather than zero", () => {
    metricsHook.mockReturnValue({
      data: {
        ...metrics,
        queue_delay: { ...metrics.queue_delay, p95_seconds: null },
        approvals: { pending: 0, oldest_pending_age_seconds: null },
        runs: { ...metrics.runs, total: 0, success_rate: null },
        unresolved_execution_leases: { count: 0, oldest_age_seconds: null },
        pending_outbox: { count: 0, oldest_age_seconds: null },
      },
      isLoading: false,
    });
    render(<OperatingMetricsPanel />);
    expect((document.body.textContent?.match(/unknown/g) ?? []).length).toBeGreaterThanOrEqual(5);
    expect(screen.getByText(/queueSample.*"size":8.*"cap":1000/)).toBeInTheDocument();
  });
});
