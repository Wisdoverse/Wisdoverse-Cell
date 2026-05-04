import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RequirementsTable } from "./requirements-table";
import type { Requirement } from "@/lib/api/types";

// next-intl and next/navigation are globally mocked in setup.ts.

const makeRequirement = (overrides: Partial<Requirement> = {}): Requirement => ({
  id: "req-1",
  title: "Login button not working",
  description: "Users cannot click the login button",
  source_quote: null,
  status: "pending",
  priority: "high",
  category: "UI",
  source_meeting_ids: [],
  confirmed_by: null,
  confirmed_at: null,
  rejection_reason: null,
  open_questions: [],
  history: [],
  created_at: "2025-06-01T00:00:00Z",
  updated_at: "2025-06-01T00:00:00Z",
  ...overrides,
});

const defaultProps = {
  data: [
    makeRequirement({ id: "req-1", title: "Login button not working" }),
    makeRequirement({
      id: "req-2",
      title: "Search performance slow",
      status: "confirmed" as const,
      priority: "medium" as const,
    }),
  ],
  isLoading: false,
  page: 1,
  pageSize: 20,
  total: 2,
  onPageChange: vi.fn(),
  selectedIds: [] as string[],
  onSelectionChange: vi.fn(),
  onConfirm: vi.fn(),
  onReject: vi.fn(),
};

describe("RequirementsTable", () => {
  it("renders requirement rows with titles", () => {
    render(<RequirementsTable {...defaultProps} />);

    expect(screen.getByText("Login button not working")).toBeInTheDocument();
    expect(screen.getByText("Search performance slow")).toBeInTheDocument();
  });

  it("renders status badges for each requirement", () => {
    render(<RequirementsTable {...defaultProps} />);

    // StatusBadge renders the translation key as text (via the mock)
    expect(screen.getByText("statusPending")).toBeInTheDocument();
    expect(screen.getByText("statusConfirmed")).toBeInTheDocument();
  });

  it("renders checkbox for each row plus a header checkbox", () => {
    render(<RequirementsTable {...defaultProps} />);

    const checkboxes = screen.getAllByRole("checkbox");
    // 1 header checkbox + 2 row checkboxes = 3
    expect(checkboxes.length).toBe(3);
  });

  it("calls onSelectionChange when a row checkbox is toggled", async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();

    render(
      <RequirementsTable
        {...defaultProps}
        onSelectionChange={onSelectionChange}
      />,
    );

    const checkboxes = screen.getAllByRole("checkbox");
    // Click the first row checkbox (index 1, since 0 is the header)
    await user.click(checkboxes[1]);

    expect(onSelectionChange).toHaveBeenCalledWith(["req-1"]);
  });

  it("checks selected row checkboxes", () => {
    render(
      <RequirementsTable {...defaultProps} selectedIds={["req-1"]} />,
    );

    const checkboxes = screen.getAllByRole("checkbox");
    // Row 1 should be checked
    expect(checkboxes[1]).toBeChecked();
    // Row 2 should not be checked
    expect(checkboxes[2]).not.toBeChecked();
  });

  it("calls onConfirm when the confirm button is clicked", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(<RequirementsTable {...defaultProps} onConfirm={onConfirm} />);

    // Each row has a confirm (check) and reject (x) button.
    // The confirm buttons are the odd-indexed action buttons.
    const buttons = screen.getAllByRole("button");

    // Find the green confirm button for the first row (it contains a Check icon)
    // Buttons with green-600 class
    const confirmButtons = buttons.filter((btn) =>
      btn.className.includes("text-green-600"),
    );
    expect(confirmButtons.length).toBe(2); // one per row

    await user.click(confirmButtons[0]);
    expect(onConfirm).toHaveBeenCalledWith("req-1");
  });

  it("calls onReject when the reject button is clicked", async () => {
    const user = userEvent.setup();
    const onReject = vi.fn();

    render(<RequirementsTable {...defaultProps} onReject={onReject} />);

    const buttons = screen.getAllByRole("button");
    const rejectButtons = buttons.filter((btn) =>
      btn.className.includes("text-red-600"),
    );
    expect(rejectButtons.length).toBe(2); // one per row

    await user.click(rejectButtons[1]);
    expect(onReject).toHaveBeenCalledWith("req-2");
  });

  it("shows loading skeletons when isLoading is true", () => {
    const { container } = render(
      <RequirementsTable {...defaultProps} isLoading={true} data={[]} />,
    );

    const skeletons = container.querySelectorAll('[data-slot="skeleton"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});
