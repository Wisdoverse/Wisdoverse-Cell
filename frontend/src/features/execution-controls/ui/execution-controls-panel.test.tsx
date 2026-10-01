import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ControlPlaneAgentRun } from "@/entities/control-plane";

const api = vi.hoisted(() => ({ requestExecutionControl: vi.fn(), recoverAbandonedExecution: vi.fn() }));
vi.mock("../api/execution-controls", () => api);
import { ExecutionControlsPanel } from "./execution-controls-panel";

const run = (status: string, adapter_type: string): ControlPlaneAgentRun => ({
  run_id: "run-7", company_id: "company-2", status,
  metadata: { adapter_type },
} as unknown as ControlPlaneAgentRun);

describe("ExecutionControlsPanel", () => {
  beforeEach(() => { api.requestExecutionControl.mockReset().mockResolvedValue({ requested_action: "pause", state: "requested" }); });

  it("only offers controls for running process adapters and submits requested-state actions", async () => {
    const refresh = vi.fn();
    const { rerender } = render(<ExecutionControlsPanel run={run("succeeded", "process")} onRefresh={refresh} />);
    expect(screen.queryByRole("region", { name: "title" })).not.toBeInTheDocument();
    rerender(<ExecutionControlsPanel run={run("running", "process")} onRefresh={refresh} />);
    fireEvent.change(screen.getByLabelText("controlReason"), { target: { value: "operator review" } });
    fireEvent.click(screen.getByRole("button", { name: "pause" }));
    await waitFor(() => expect(api.requestExecutionControl).toHaveBeenCalledWith("run-7", {
      company_id: "company-2", action: "pause", reason: "operator review",
    }));
    expect(await screen.findByText(/requestMayNotBeApplied/)).toBeInTheDocument();
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("does not offer unsupported HTTP or local-executor controls", () => {
    const { rerender } = render(<ExecutionControlsPanel run={run("running", "http")} onRefresh={vi.fn()} />);
    expect(screen.queryByRole("region", { name: "title" })).not.toBeInTheDocument();
    rerender(<ExecutionControlsPanel run={run("running", "codex_local")} onRefresh={vi.fn()} />);
    expect(screen.queryByRole("region", { name: "title" })).not.toBeInTheDocument();
  });

  it("surfaces access-denial errors for a supported process control", async () => {
    api.requestExecutionControl.mockRejectedValue(new Error("403 operator_scope_denied"));
    render(<ExecutionControlsPanel run={run("running", "process")} onRefresh={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("controlReason"), { target: { value: "review" } });
    fireEvent.click(screen.getByRole("button", { name: "terminate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("403 operator_scope_denied");
  });
});
