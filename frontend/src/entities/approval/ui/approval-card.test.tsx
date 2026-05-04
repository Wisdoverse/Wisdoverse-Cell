import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ApprovalCard } from "./approval-card";
import type { ApprovalRequest } from "@/lib/api/types";

const mockApproval: ApprovalRequest = {
  id: "apr-001",
  source_agent_id: "requirement-manager",
  approval_type: "technical",
  title: "Confirm REQ-041",
  summary: "User login feature extracted from meeting notes",
  urgency: "normal",
  status: "pending",
  created_at: "2026-02-25T14:15:00Z",
};

describe("ApprovalCard", () => {
  it("renders title and summary", () => {
    render(<ApprovalCard approval={mockApproval} />);
    expect(screen.getByText("Confirm REQ-041")).toBeDefined();
    expect(screen.getByText(/User login feature/)).toBeDefined();
  });

  it("renders approve and reject buttons", () => {
    render(<ApprovalCard approval={mockApproval} />);
    expect(screen.getByRole("button", { name: /approve/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /reject/i })).toBeDefined();
  });

  it("calls onApprove when approve button clicked", () => {
    const onApprove = vi.fn();
    render(<ApprovalCard approval={mockApproval} onApprove={onApprove} />);
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onApprove).toHaveBeenCalledOnce();
  });

  it("calls onReject when reject button clicked", () => {
    const onReject = vi.fn();
    render(<ApprovalCard approval={mockApproval} onReject={onReject} />);
    fireEvent.click(screen.getByRole("button", { name: /reject/i }));
    expect(onReject).toHaveBeenCalledOnce();
  });
});
