import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ActivityItem } from "./activity-item";
import type { ActivityEvent } from "@/lib/api/types";

const mockEvent: ActivityEvent = {
  id: "evt-001",
  agent_id: "requirement-manager",
  event_type: "requirement.extracted",
  description: "Extracted requirement REQ-042 from meeting notes",
  payload: {},
  timestamp: "2026-02-25T14:32:00Z",
};

describe("ActivityItem", () => {
  it("renders event description", () => {
    render(<ActivityItem event={mockEvent} />);
    expect(screen.getByText(/Extracted requirement REQ-042/)).toBeDefined();
  });

  it("renders agent short name via avatar", () => {
    render(<ActivityItem event={mockEvent} />);
    expect(screen.getByText("RM")).toBeDefined();
  });

  it("renders agent name", () => {
    render(<ActivityItem event={mockEvent} />);
    expect(screen.getByText("Requirement Manager")).toBeDefined();
  });
});
