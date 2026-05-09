import { describe, it, expect } from "vitest";
import type { AgentMeta } from "@/entities/agent";
import type {
  ApprovalRequest,
  ActivityEvent,
} from "../types";

describe("Agent types", () => {
  it("should define AgentMeta with required fields", () => {
    const agent: AgentMeta = {
      id: "requirement-manager",
      name: "Requirement Manager",
      shortName: "RM",
      domain: "product",
      icon: "ClipboardList",
      description: "Manages requirements",
      tabs: ["overview", "tasks", "events", "config", "logs"],
      upstream: [],
      downstream: ["code-generator"],
    };
    expect(agent.id).toBe("requirement-manager");
    expect(agent.domain).toBe("product");
  });

  it("should define ApprovalRequest with required fields", () => {
    const approval: ApprovalRequest = {
      id: "apr-001",
      source_agent_id: "requirement-manager",
      approval_type: "technical",
      title: "Confirm REQ-041",
      summary: "User login feature requirement",
      urgency: "normal",
      status: "pending",
      created_at: "2026-02-25T10:00:00Z",
    };
    expect(approval.approval_type).toBe("technical");
    expect(approval.status).toBe("pending");
  });

  it("should define ActivityEvent with required fields", () => {
    const event: ActivityEvent = {
      id: "evt-001",
      agent_id: "requirement-manager",
      event_type: "requirement.extracted",
      description: "Extracted REQ-042",
      payload: {},
      timestamp: "2026-02-25T14:32:00Z",
    };
    expect(event.event_type).toBe("requirement.extracted");
  });
});
