import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ControlPlaneWorkbenchState } from "@/entities/control-plane";
import { ControlPlaneWorkbenchPage } from "./control-plane-workbench-page";

const useControlPlaneWorkbenchMock = vi.fn<() => ControlPlaneWorkbenchState>();

vi.mock("@/entities/control-plane", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/entities/control-plane")>();
  return {
    ...actual,
    useControlPlaneWorkbench: () => useControlPlaneWorkbenchMock(),
  };
});

function buildWorkbenchState(): ControlPlaneWorkbenchState {
  const goal = {
    goal_id: "goal_alpha",
    company_id: "company_1",
    title: "Goal Alpha",
    description: "",
    status: "active" as const,
    parent_goal_id: null,
    owner_agent_id: "pjm-agent",
    owner_user_id: null,
    success_metric: "accepted outcome",
    target_value: 1,
    current_value: 0,
    due_at: null,
    tags: [],
    metadata: {},
    created_at: "2026-05-01T10:00:00Z",
    updated_at: "2026-05-01T10:00:00Z",
  };
  const workItem = {
    work_item_id: "work_alpha",
    company_id: "company_1",
    title: "Work Alpha",
    description: "",
    status: "running" as const,
    priority: "high" as const,
    goal_id: "goal_alpha",
    owner_agent_id: "dev-agent",
    owner_user_id: null,
    source: "manual",
    external_ref: null,
    dependencies: [],
    approval_required: false,
    metadata: {},
    created_at: "2026-05-01T10:05:00Z",
    updated_at: "2026-05-01T10:10:00Z",
  };
  const run = {
    run_id: "run_alpha",
    company_id: "company_1",
    agent_id: "dev-agent",
    status: "succeeded" as const,
    trace_id: "trace_alpha",
    goal_id: "goal_alpha",
    work_item_id: "work_alpha",
    trigger_event_id: null,
    input_event: null,
    output_events: [],
    started_at: "2026-05-01T10:11:00Z",
    completed_at: "2026-05-01T10:12:00Z",
    error_category: null,
    error_message: null,
    last_successful_step: null,
    cost_usd: 0.12,
    input_tokens: 100,
    output_tokens: 50,
    metadata: {},
  };
  const budgetPolicy = {
    budget_id: "budget_alpha",
    company_id: "company_1",
    scope: "agent" as const,
    scope_id: "dev-agent",
    period: "daily" as const,
    limit_usd: 12,
    warning_threshold: 0.8,
    status: "active" as const,
    model_allowlist: ["gpt-5.2"],
    metadata: {},
    created_at: "2026-05-01T10:02:00Z",
    updated_at: "2026-05-01T10:02:00Z",
  };

  return {
    goals: [goal],
    workItems: [workItem],
    runs: [run],
    decisions: [],
    artifacts: [],
    budgetPolicies: [budgetPolicy],
    approvals: [
      {
        approval_id: "approval_alpha",
        company_id: "company_1",
        category: "technical" as const,
        status: "pending" as const,
        requested_by: "human:operator",
        source_agent_id: "dev-agent",
        proposed_action: "Deploy risky change",
        reason: "Production path update",
        risk: "Could interrupt users",
        rollback_note: "Revert deployment",
        affected_resources: ["frontend"],
        artifact_links: [],
        run_id: "run_alpha",
        work_item_id: "work_alpha",
        goal_id: "goal_alpha",
        trace_id: "trace_alpha",
        resolved_by: null,
        resolved_at: null,
        expires_at: null,
        metadata: {},
        created_at: "2026-05-01T10:12:00Z",
        updated_at: "2026-05-01T10:12:00Z",
      },
    ],
    budgetUsage: [],
    evolutionProposals: [
      {
        proposal_id: "proposal_alpha",
        company_id: "company_1",
        tier: "L2" as const,
        scope: "control-plane workbench",
        evidence: {},
        expected_benefit: "Operators can review proposed architecture changes",
        risk: "Requires technical approval before rollout",
        approval_state: "pending" as const,
        rollout_state: "proposed" as const,
        approval_id: "approval_alpha",
        metadata: {},
        created_at: "2026-05-01T10:13:00Z",
        updated_at: "2026-05-01T10:13:00Z",
      },
    ],
    timeline: [
      {
        type: "agent_run",
        at: "2026-05-01T10:12:00Z",
        data: {
          run_id: "run_alpha",
          status: "succeeded",
        },
      },
    ],
    selectedGoal: goal,
    selectedWorkItem: workItem,
    activeRun: run,
    activeGoalId: "goal_alpha",
    activeWorkItemId: "work_alpha",
    activeRunId: "run_alpha",
    selectedRunId: undefined,
    selectGoal: vi.fn(),
    selectWorkItem: vi.fn(),
    selectRun: vi.fn(),
    approveApproval: vi.fn().mockResolvedValue(undefined),
    rejectApproval: vi.fn().mockResolvedValue(undefined),
    createGoal: vi.fn().mockResolvedValue(undefined),
    createWorkItem: vi.fn().mockResolvedValue(undefined),
    createBudgetPolicy: vi.fn().mockResolvedValue(undefined),
    updateBudgetPolicy: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn(),
    summary: {
      goalCount: 1,
      openWorkCount: 1,
      pendingApprovalCount: 0,
      costUsd: 0,
    },
    isLoading: false,
    isEvidenceLoading: false,
    isEvolutionLoading: false,
    error: undefined,
    approvalActionId: undefined,
    goalActionId: undefined,
    workItemActionId: undefined,
    budgetPolicyActionId: undefined,
    isBudgetPolicyLoading: false,
  };
}

describe("ControlPlaneWorkbenchPage", () => {
  beforeEach(() => {
    useControlPlaneWorkbenchMock.mockReturnValue(buildWorkbenchState());
  });

  it("renders goal, work, and timeline lineage from the control-plane hook", () => {
    render(<ControlPlaneWorkbenchPage />);

    expect(screen.getAllByText("Goal Alpha").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Work Alpha").length).toBeGreaterThan(0);
    expect(screen.getAllByText("run_alpha").length).toBeGreaterThan(0);
    expect(screen.getAllByText("succeeded").length).toBeGreaterThan(0);
    expect(screen.getByText("control-plane workbench")).toBeInTheDocument();
    expect(screen.getAllByText("pending").length).toBeGreaterThan(0);
  });

  it("exposes durable approval actions from the evidence panel", async () => {
    const user = userEvent.setup();
    const state = buildWorkbenchState();
    useControlPlaneWorkbenchMock.mockReturnValue(state);

    render(<ControlPlaneWorkbenchPage />);

    await user.click(screen.getByRole("tab", { name: "approvals" }));

    expect(screen.getByText("Deploy risky change")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "approve" }));

    expect(state.approveApproval).toHaveBeenCalledWith("approval_alpha");
  });

  it("lets operators create goals and work items from the workbench", async () => {
    const user = userEvent.setup();
    const state = buildWorkbenchState();
    useControlPlaneWorkbenchMock.mockReturnValue(state);

    render(<ControlPlaneWorkbenchPage />);

    await user.click(screen.getByRole("button", { name: "newGoal" }));
    await user.type(screen.getByLabelText("goalTitle"), "Goal Beta");
    await user.click(screen.getByRole("button", { name: "create" }));

    expect(state.createGoal).toHaveBeenCalledWith({
      title: "Goal Beta",
      description: "",
      owner_agent_id: "pjm-agent",
    });

    await user.click(screen.getByRole("button", { name: "newWorkItem" }));
    await user.type(screen.getByLabelText("workItemTitle"), "Work Beta");
    await user.click(screen.getByRole("button", { name: "create" }));

    expect(state.createWorkItem).toHaveBeenCalledWith({
      title: "Work Beta",
      description: "",
      owner_agent_id: "dev-agent",
    });
  });

  it("lets operators manage budget policies from the workbench", async () => {
    const user = userEvent.setup();
    const state = buildWorkbenchState();
    useControlPlaneWorkbenchMock.mockReturnValue(state);

    render(<ControlPlaneWorkbenchPage />);

    expect(screen.getByText("budgetPolicies")).toBeInTheDocument();
    expect(screen.getAllByText("dev-agent").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "newBudgetPolicy" }));
    await user.clear(screen.getByLabelText("budgetLimit"));
    await user.type(screen.getByLabelText("budgetLimit"), "25");
    await user.type(screen.getByLabelText("modelAllowlist"), "gpt-5.2, gpt-5.4");
    await user.click(screen.getByRole("button", { name: "create" }));

    expect(state.createBudgetPolicy).toHaveBeenCalledWith({
      scope: "agent",
      scope_id: "dev-agent",
      period: "daily",
      status: "active",
      limit_usd: 25,
      warning_threshold: 0.8,
      model_allowlist: ["gpt-5.2", "gpt-5.4"],
    });

    await user.click(screen.getByRole("button", { name: "pause" }));

    expect(state.updateBudgetPolicy).toHaveBeenCalledWith("budget_alpha", {
      status: "paused",
    });

    await user.click(screen.getByRole("button", { name: "edit" }));
    await user.clear(screen.getByLabelText("budgetLimit"));
    await user.type(screen.getByLabelText("budgetLimit"), "18");
    await user.click(screen.getByRole("button", { name: "save" }));

    expect(state.updateBudgetPolicy).toHaveBeenCalledWith("budget_alpha", {
      status: "active",
      limit_usd: 18,
      warning_threshold: 0.8,
      model_allowlist: ["gpt-5.2"],
    });
  });
});
