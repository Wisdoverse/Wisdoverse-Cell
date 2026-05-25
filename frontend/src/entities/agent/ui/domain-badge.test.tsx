import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DomainBadge } from "./domain-badge";

describe("DomainBadge", () => {
  it("renders domain label", () => {
    render(<DomainBadge domain="product" />);
    expect(screen.getByText("domainLabels.product")).toBeDefined();
  });

  it("renders data-ai domain correctly", () => {
    render(<DomainBadge domain="data-ai" />);
    expect(screen.getByText("domainLabels.dataAi")).toBeDefined();
  });

  it("renders market-sales domain correctly", () => {
    render(<DomainBadge domain="market-sales" />);
    expect(screen.getByText("domainLabels.marketSales")).toBeDefined();
  });
});
