import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api/client";
import {
  createControlPlaneGoal,
  createControlPlaneBudgetPolicy,
  createControlPlaneWorkItem,
  getControlPlaneOperatingMetrics,
  getControlPlaneTimeline,
  listControlPlaneArtifacts,
  listControlPlaneApprovals,
  listControlPlaneBudgetPolicies,
  listControlPlaneBudgetUsage,
  listControlPlaneEvolutionProposals,
  listControlPlaneGoals,
  listControlPlaneRuns,
  listControlPlaneWorkItems,
  updateControlPlaneBudgetPolicy,
  updateControlPlaneWorkItemStatus,
} from "./control-plane";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
  },
}));

const getMock = vi.mocked(apiClient.get);
const patchMock = vi.mocked(apiClient.patch);
const postMock = vi.mocked(apiClient.post);

describe("control-plane API client", () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValue({});
    patchMock.mockReset();
    patchMock.mockResolvedValue({});
    postMock.mockReset();
    postMock.mockResolvedValue({});
  });

  it("queries operating metrics by company using the typed metrics path", async () => {
    await getControlPlaneOperatingMetrics("company_1");
    expect(getMock).toHaveBeenCalledWith("/control-plane/operating-metrics", { company_id: "company_1" });
  });

  it("uses the shared control-plane goal/work/run paths", async () => {
    await listControlPlaneGoals({ status: "active", limit: 20 });
    await createControlPlaneGoal({
      title: "Reduce handoffs",
      status: "active",
      created_by: "human:operator",
    });
    await listControlPlaneWorkItems({ goal_id: "goal_1", limit: 50 });
    await createControlPlaneWorkItem({
      goal_id: "goal_1",
      title: "Draft acceptance plan",
      priority: "high",
      created_by: "human:operator",
    });
    await updateControlPlaneWorkItemStatus("work_1", {
      company_id: "company_1",
      status: "running",
      owner_agent_id: "dev-agent",
      actor_id: "human:operator",
    });
    await listControlPlaneRuns({ work_item_id: "work_1", limit: 10 });

    expect(getMock).toHaveBeenNthCalledWith(1, "/control-plane/goals", {
      status: "active",
      limit: 20,
    });
    expect(postMock).toHaveBeenNthCalledWith(1, "/control-plane/goals", {
      title: "Reduce handoffs",
      status: "active",
      created_by: "human:operator",
    });
    expect(getMock).toHaveBeenNthCalledWith(2, "/control-plane/work-items", {
      goal_id: "goal_1",
      limit: 50,
    });
    expect(postMock).toHaveBeenNthCalledWith(2, "/control-plane/work-items", {
      goal_id: "goal_1",
      title: "Draft acceptance plan",
      priority: "high",
      created_by: "human:operator",
    });
    expect(patchMock).toHaveBeenCalledWith(
      "/control-plane/work-items/work_1/status?company_id=company_1",
      {
        status: "running",
        owner_agent_id: "dev-agent",
        actor_id: "human:operator",
      },
    );
    expect(getMock).toHaveBeenNthCalledWith(3, "/control-plane/runs", {
      work_item_id: "work_1",
      limit: 10,
    });
  });

  it("uses evidence paths tied to run lineage", async () => {
    await getControlPlaneTimeline({ run_id: "run_1", limit: 100 });
    await listControlPlaneArtifacts({ run_id: "run_1", limit: 50 });
    await listControlPlaneBudgetUsage({ run_id: "run_1", limit: 50 });

    expect(getMock).toHaveBeenNthCalledWith(1, "/control-plane/timeline", {
      run_id: "run_1",
      limit: 100,
    });
    expect(getMock).toHaveBeenNthCalledWith(2, "/control-plane/artifacts", {
      run_id: "run_1",
      limit: 50,
    });
    expect(getMock).toHaveBeenNthCalledWith(3, "/control-plane/budgets/usage", {
      run_id: "run_1",
      limit: 50,
    });
  });

  it("uses the control-plane evolution proposal list path", async () => {
    await listControlPlaneEvolutionProposals({
      tier: "L2",
      approval_state: "pending",
      limit: 25,
    });

    expect(getMock).toHaveBeenCalledWith(
      "/control-plane/evolution-proposals",
      {
        tier: "L2",
        approval_state: "pending",
        limit: 25,
      },
    );
  });

  it("fetches approvals by work item so approvals without a run ID remain visible", async () => {
    await listControlPlaneApprovals({ company_id: "company_1", work_item_id: "work_1", limit: 50 });
    expect(getMock).toHaveBeenCalledWith("/control-plane/approvals", { company_id: "company_1", work_item_id: "work_1", limit: 50 });
  });

  it("uses durable approval action endpoints", async () => {
    const { approveControlPlaneApproval, rejectControlPlaneApproval } =
      await import("./control-plane");

    await approveControlPlaneApproval("approval_1", {
      resolved_by: "human:operator",
    });
    await rejectControlPlaneApproval("approval_2", {
      resolved_by: "human:operator",
    });

    expect(postMock).toHaveBeenNthCalledWith(
      1,
      "/control-plane/approvals/approval_1/approve",
      { resolved_by: "human:operator" },
    );
    expect(postMock).toHaveBeenNthCalledWith(
      2,
      "/control-plane/approvals/approval_2/reject",
      { resolved_by: "human:operator" },
    );
  });

  it("uses work-item execution, recovery, governance, and acceptance routes", async () => {
    const api = await import("./control-plane");
    const runPayload = { company_id: "company_1", agent_id: "qa-agent", actor_id: "human:operator", idempotency_key: "0e4d7b94-498c-41f5-8cc5-8c1c2c31a2d9" };
    await api.runControlPlaneWorkItem("work_1", runPayload);
    await api.retryControlPlaneWorkItem("work_1", runPayload);
    await api.reassignControlPlaneWorkItem("work_1", {
      company_id: "company_1", owner_agent_id: "qa-agent", actor_id: "human:operator", reason: "QA handoff",
    });
    await api.blockControlPlaneWorkItem("work_1", {
      company_id: "company_1", actor_id: "human:operator", reason: "Needs clarification",
    });
    await api.acceptControlPlaneWorkItemArtifact("work_1", {
      company_id: "company_1", artifact_id: "artifact_1", actor_id: "human:operator", verdict: "accepted", reason: "QA passed",
    });
    await api.closeControlPlaneWorkItem("work_1", {
      company_id: "company_1", actor_id: "human:operator", reason: "Accepted artifact",
    });

    expect(postMock).toHaveBeenNthCalledWith(1, "/control-plane/work-items/work_1/run", runPayload);
    expect(postMock).toHaveBeenNthCalledWith(2, "/control-plane/work-items/work_1/retry", runPayload);
    expect(postMock).toHaveBeenNthCalledWith(3, "/control-plane/work-items/work_1/reassign", {
      company_id: "company_1", owner_agent_id: "qa-agent", actor_id: "human:operator", reason: "QA handoff",
    });
    expect(postMock).toHaveBeenNthCalledWith(4, "/control-plane/work-items/work_1/block", {
      company_id: "company_1", actor_id: "human:operator", reason: "Needs clarification",
    });
    expect(postMock).toHaveBeenNthCalledWith(5, "/control-plane/work-items/work_1/accept", {
      company_id: "company_1", artifact_id: "artifact_1", actor_id: "human:operator", verdict: "accepted", reason: "QA passed",
    });
    expect(postMock).toHaveBeenNthCalledWith(6, "/control-plane/work-items/work_1/close", {
      company_id: "company_1", actor_id: "human:operator", reason: "Accepted artifact",
    });
  });

  it("uses first-class budget policy management paths", async () => {
    await listControlPlaneBudgetPolicies({
      scope: "agent",
      scope_id: "dev-agent",
      period: "daily",
      status: "active",
      limit: 25,
    });
    await createControlPlaneBudgetPolicy({
      scope: "agent",
      scope_id: "dev-agent",
      period: "daily",
      limit_usd: 12,
      created_by: "human:finance",
    });
    await updateControlPlaneBudgetPolicy("budget_1", {
      limit_usd: 20,
      status: "paused",
      actor_id: "human:finance",
    });

    expect(getMock).toHaveBeenCalledWith("/control-plane/budgets/policies", {
      scope: "agent",
      scope_id: "dev-agent",
      period: "daily",
      status: "active",
      limit: 25,
    });
    expect(postMock).toHaveBeenCalledWith("/control-plane/budgets/policies", {
      scope: "agent",
      scope_id: "dev-agent",
      period: "daily",
      limit_usd: 12,
      created_by: "human:finance",
    });
    expect(patchMock).toHaveBeenCalledWith(
      "/control-plane/budgets/policies/budget_1",
      {
        limit_usd: 20,
        status: "paused",
        actor_id: "human:finance",
      },
    );
  });
});
