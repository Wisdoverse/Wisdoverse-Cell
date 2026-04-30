import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentAvatar } from "../agent-avatar";

describe("AgentAvatar", () => {
  it("renders short name", () => {
    render(
      <AgentAvatar domain="product" icon="ClipboardList" shortName="RM" />
    );
    expect(screen.getByText("RM")).toBeDefined();
  });

  it("applies domain color as background style", () => {
    const { container } = render(
      <AgentAvatar domain="engineering" icon="Code" shortName="CG" />
    );
    const avatar = container.firstChild as HTMLElement;
    expect(avatar.style.backgroundColor).toBeTruthy();
  });

  it("supports size prop", () => {
    const { container } = render(
      <AgentAvatar domain="quality" icon="ShieldCheck" shortName="QA" size="lg" />
    );
    const avatar = container.firstChild as HTMLElement;
    expect(avatar.className).toContain("h-16");
  });
});
