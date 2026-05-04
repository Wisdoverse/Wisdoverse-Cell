import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "@/entities/requirement/ui/status-badge";
import type { RequirementStatus } from "@/lib/api/types";

// next-intl is globally mocked in setup.ts – useTranslations returns key lookup.

describe("StatusBadge", () => {
  const statuses: RequirementStatus[] = [
    "pending",
    "confirmed",
    "rejected",
    "changed",
  ];

  it.each(statuses)("renders the '%s' status variant", (status) => {
    render(<StatusBadge status={status} />);

    // The mock useTranslations returns the translation key as the label.
    // The component calls t("statusPending"), t("statusConfirmed"), etc.
    const expectedLabels: Record<RequirementStatus, string> = {
      pending: "statusPending",
      confirmed: "statusConfirmed",
      rejected: "statusRejected",
      changed: "statusChanged",
    };

    expect(screen.getByText(expectedLabels[status])).toBeInTheDocument();
  });

  it("applies the correct CSS classes for 'pending'", () => {
    render(<StatusBadge status="pending" />);
    const badge = screen.getByText("statusPending");
    expect(badge.className).toContain("bg-yellow-100");
    expect(badge.className).toContain("text-yellow-800");
  });

  it("applies the correct CSS classes for 'confirmed'", () => {
    render(<StatusBadge status="confirmed" />);
    const badge = screen.getByText("statusConfirmed");
    expect(badge.className).toContain("bg-green-100");
    expect(badge.className).toContain("text-green-800");
  });

  it("applies the correct CSS classes for 'rejected'", () => {
    render(<StatusBadge status="rejected" />);
    const badge = screen.getByText("statusRejected");
    expect(badge.className).toContain("bg-red-100");
    expect(badge.className).toContain("text-red-800");
  });

  it("applies the correct CSS classes for 'changed'", () => {
    render(<StatusBadge status="changed" />);
    const badge = screen.getByText("statusChanged");
    expect(badge.className).toContain("bg-blue-100");
    expect(badge.className).toContain("text-blue-800");
  });
});
