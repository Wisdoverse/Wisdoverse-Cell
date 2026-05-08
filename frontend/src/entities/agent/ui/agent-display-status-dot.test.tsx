import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { AgentStatusDot } from "./agent-display-status-dot";

describe("AgentStatusDot", () => {
  it("renders with running status", () => {
    const { container } = render(<AgentStatusDot status="running" />);
    const dot = container.firstChild as HTMLElement;
    expect(dot.className).toContain("bg-green-500");
    expect(dot.className).toContain("animate-pulse");
  });

  it("renders idle without animation", () => {
    const { container } = render(<AgentStatusDot status="idle" />);
    const dot = container.firstChild as HTMLElement;
    expect(dot.className).toContain("bg-gray-400");
    expect(dot.className).not.toContain("animate-pulse");
  });

  it("renders paused without running animation", () => {
    const { container } = render(<AgentStatusDot status="paused" />);
    const dot = container.firstChild as HTMLElement;
    expect(dot.className).toContain("bg-amber-500");
    expect(dot.className).not.toContain("animate-pulse");
  });

  it("renders error status", () => {
    const { container } = render(<AgentStatusDot status="error" />);
    const dot = container.firstChild as HTMLElement;
    expect(dot.className).toContain("bg-red-500");
  });

  it("renders stopped as outline", () => {
    const { container } = render(<AgentStatusDot status="stopped" />);
    const dot = container.firstChild as HTMLElement;
    expect(dot.className).toContain("border");
  });
});
