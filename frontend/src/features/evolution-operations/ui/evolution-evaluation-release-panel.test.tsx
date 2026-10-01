import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  createEvolutionEvaluation: vi.fn(), listEvolutionEvaluations: vi.fn(), requestEvolutionRelease: vi.fn(), reconcileEvolutionRelease: vi.fn(), recoverEvolutionRelease: vi.fn(),
}));
vi.mock("../api/evolution-operations", () => api);
import { EvolutionEvaluationReleasePanel } from "./evolution-evaluation-release-panel";

const proposal = { proposal_id: "proposal-1", company_id: "company-1", metadata: {} };
const input = {
  baseline: { evaluation_id: "base-eval", dataset_revision: "set-v1", config_revision: "skill@1", budget_usd: 2,
    cases: [{ case_id: "c1", case_revision: "1", expects_policy_denial: false }],
    results: [{ result_id: "r1", case_id: "c1", config_revision: "skill@1", accepted: true, quality: 0.9, total_attempt_cost_usd: 0.2, latency_ms: 100, human_interventions: 0 }] },
  candidate: { evaluation_id: "candidate-eval", dataset_revision: "set-v1", config_revision: "skill@2", budget_usd: 2,
    cases: [{ case_id: "c1", case_revision: "1", expects_policy_denial: false }],
    results: [{ result_id: "r2", case_id: "c1", config_revision: "skill@2", accepted: true, quality: 0.95, total_attempt_cost_usd: 0.1, latency_ms: 80, human_interventions: 0 }] },
  policy: { maximum_cost_per_accepted_outcome_usd: 1 },
};
const report = {
  evaluation_report_id: "evr-1", company_id: "company-1", proposal_id: "proposal-1",
  baseline_skill_version_id: "skill-a@1", candidate_skill_version_id: "skill-a@2",
  comparison_report: { eligible: true, report_kind: "fixed_evaluation_case_comparison", baseline: { sample_count: 1 }, candidate: { sample_count: 1 } },
};

describe("EvolutionEvaluationReleasePanel", () => {
  beforeEach(() => {
    api.createEvolutionEvaluation.mockReset().mockResolvedValue(report);
    api.listEvolutionEvaluations.mockReset().mockResolvedValue({ evaluations: [], total: 0, report_kind: "fixed_evaluation_case_comparison" });
    api.requestEvolutionRelease.mockReset();
    api.reconcileEvolutionRelease.mockReset().mockResolvedValue({ state: "acknowledged" });
    api.recoverEvolutionRelease.mockReset().mockResolvedValue({ state: "recovered" });
  });

  it("validates fixed-case JSON before recording and shows the returned report and sample gate", async () => {
    render(<EvolutionEvaluationReleasePanel proposal={proposal} />);
    fireEvent.change(screen.getByPlaceholderText("batchPlaceholder"), { target: { value: "{}" } });
    fireEvent.click(screen.getByRole("button", { name: "evaluate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalidBatch");
    expect(api.createEvolutionEvaluation).not.toHaveBeenCalled();
    fireEvent.change(screen.getByPlaceholderText("batchPlaceholder"), { target: { value: JSON.stringify(input) } });
    fireEvent.click(screen.getByRole("button", { name: "evaluate" }));
    await waitFor(() => expect(api.createEvolutionEvaluation).toHaveBeenCalledWith("proposal-1", {
      company_id: "company-1", ...input, actor_id: "human:operator",
    }));
    expect((await screen.findAllByText(/fixed_evaluation_case_comparison/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/liveSampleInsufficient/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "canary" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "promote" })).toBeDisabled();
  });

  it("submits a release only after required release identifiers are supplied and surfaces approval denial", async () => {
    api.listEvolutionEvaluations.mockResolvedValue({ evaluations: [report], total: 1, report_kind: "fixed_evaluation_case_comparison" });
    api.requestEvolutionRelease.mockRejectedValue(new Error("403 skill_release_approval_required"));
    render(<EvolutionEvaluationReleasePanel proposal={proposal} />);
    for (const [label, value] of [
      ["skill_id", "skill-a"], ["agent_id", "agent-a"], ["baseline_version", "1"], ["candidate_version", "2"],
      ["baseline_config_hash", "a".repeat(64)], ["candidate_config_hash", "b".repeat(64)],
    ]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
    await waitFor(() => expect(screen.getByRole("button", { name: "shadow" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "shadow" }));
    await waitFor(() => expect(api.requestEvolutionRelease).toHaveBeenCalledWith("proposal-1", {
      company_id: "company-1", evaluation_report_id: "evr-1", skill_id: "skill-a", agent_id: "agent-a",
      baseline_version: 1, candidate_version: 2, baseline_config_hash: "a".repeat(64),
      candidate_config_hash: "b".repeat(64), action: "shadow",
    }));
    expect(await screen.findByRole("alert")).toHaveTextContent("403 skill_release_approval_required");
  });

  it("offers reconciliation after an uncertain release and never resubmits the release", async () => {
    api.listEvolutionEvaluations.mockResolvedValue({ evaluations: [report], total: 1, report_kind: "fixed_evaluation_case_comparison" });
    api.requestEvolutionRelease.mockRejectedValue(new Error("502 evolution_release_pending_reconciliation"));
    render(<EvolutionEvaluationReleasePanel proposal={proposal} />);
    for (const [label, value] of [
      ["skill_id", "skill-a"], ["agent_id", "agent-a"], ["baseline_version", "1"], ["candidate_version", "2"],
      ["baseline_config_hash", "a".repeat(64)], ["candidate_config_hash", "b".repeat(64)],
    ]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
    await waitFor(() => expect(screen.getByRole("button", { name: "shadow" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "shadow" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("evolution_release_pending_reconciliation");
    fireEvent.click(screen.getByRole("button", { name: "reconcileRelease" }));
    await waitFor(() => expect(api.reconcileEvolutionRelease).toHaveBeenCalledWith("proposal-1", "company-1"));
    expect(api.requestEvolutionRelease).toHaveBeenCalledOnce();
    expect(await screen.findByRole("status")).toHaveTextContent("reconcileCompleted");
    expect(screen.getByRole("button", { name: "reconcileRelease" })).toBeInTheDocument();
  });

  it("runs recovery only after an explicit click and reports the recovery response", async () => {
    api.listEvolutionEvaluations.mockResolvedValue({ evaluations: [report], total: 1, report_kind: "fixed_evaluation_case_comparison" });
    render(<EvolutionEvaluationReleasePanel proposal={proposal} />);
    fireEvent.click(screen.getByRole("button", { name: "recoverRelease" }));
    await waitFor(() => expect(api.recoverEvolutionRelease).toHaveBeenCalledWith("proposal-1", "company-1"));
    expect(api.requestEvolutionRelease).not.toHaveBeenCalled();
    expect(await screen.findByRole("status")).toHaveTextContent("recoveryCompleted");
  });

  it("keeps the pending recovery controls available and shows recovery errors", async () => {
    api.recoverEvolutionRelease.mockRejectedValue(new Error("403 evolution_release_approval_required"));
    render(<EvolutionEvaluationReleasePanel proposal={proposal} />);
    fireEvent.click(screen.getByRole("button", { name: "recoverRelease" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("403 evolution_release_approval_required");
    expect(screen.getByRole("button", { name: "recoverRelease" })).toBeInTheDocument();
  });
});
