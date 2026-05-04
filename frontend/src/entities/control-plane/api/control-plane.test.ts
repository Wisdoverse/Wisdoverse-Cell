import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api/client";
import {
  getControlPlaneTimeline,
  listControlPlaneArtifacts,
  listControlPlaneBudgetUsage,
  listControlPlaneEvolutionProposals,
  listControlPlaneGoals,
  listControlPlaneRuns,
  listControlPlaneWorkItems,
} from "./control-plane";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const getMock = vi.mocked(apiClient.get);
const postMock = vi.mocked(apiClient.post);

describe("control-plane API client", () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValue({});
    postMock.mockReset();
    postMock.mockResolvedValue({});
  });

  it("uses the shared control-plane goal/work/run paths", async () => {
    await listControlPlaneGoals({ status: "active", limit: 20 });
    await listControlPlaneWorkItems({ goal_id: "goal_1", limit: 50 });
    await listControlPlaneRuns({ work_item_id: "work_1", limit: 10 });

    expect(getMock).toHaveBeenNthCalledWith(1, "/control-plane/goals", {
      status: "active",
      limit: 20,
    });
    expect(getMock).toHaveBeenNthCalledWith(2, "/control-plane/work-items", {
      goal_id: "goal_1",
      limit: 50,
    });
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
});
