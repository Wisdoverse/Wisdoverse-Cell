import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentCard } from "../agent-card";
import type { AgentMeta, AgentRuntimeStatus } from "@/lib/api/types";

const mockMeta: AgentMeta = {
  id: "requirement-manager",
  name: "Requirement Manager",
  shortName: "RM",
  domain: "product",
  icon: "ClipboardList",
  description: "Manages requirements",
  tabs: ["overview", "tasks", "events", "config", "logs"],
  upstream: [],
  downstream: [],
};

const mockRuntime: AgentRuntimeStatus = {
  agent_id: "requirement-manager",
  status: "running",
  health: 85,
  task_count: 142,
  pending_count: 8,
  error_count: 2,
  uptime_seconds: 259200,
  last_active_at: "2026-02-25T14:32:00Z",
};

describe("AgentCard", () => {
  it("renders agent name and short name", () => {
    render(<AgentCard meta={mockMeta} runtime={mockRuntime} />);
    expect(screen.getByText("Requirement Manager")).toBeDefined();
    expect(screen.getByText("RM")).toBeDefined();
  });

  it("shows status dot", () => {
    const { container } = render(
      <AgentCard meta={mockMeta} runtime={mockRuntime} />
    );
    const dot = container.querySelector("[aria-label='running']");
    expect(dot).toBeTruthy();
  });

  it("shows task count", () => {
    render(<AgentCard meta={mockMeta} runtime={mockRuntime} />);
    expect(screen.getByText("142")).toBeDefined();
  });

  it("calls onClick when clicked", () => {
    const onClick = vi.fn();
    render(
      <AgentCard meta={mockMeta} runtime={mockRuntime} onClick={onClick} />
    );
    fireEvent.click(screen.getByText("Requirement Manager"));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
