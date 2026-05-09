import { describe, expect, it } from "vitest";

import { mapControlPlaneAgentStatus } from "./status";

describe("mapControlPlaneAgentStatus", () => {
  it("keeps paused lifecycle state visible", () => {
    expect(mapControlPlaneAgentStatus("paused")).toBe("paused");
    expect(mapControlPlaneAgentStatus(" PAUSED ")).toBe("paused");
  });

  it("maps active control-plane agents to running UI state", () => {
    expect(mapControlPlaneAgentStatus("active")).toBe("running");
    expect(mapControlPlaneAgentStatus("running")).toBe("running");
  });

  it("maps terminal and failed states without falling back to idle", () => {
    expect(mapControlPlaneAgentStatus("terminated")).toBe("stopped");
    expect(mapControlPlaneAgentStatus("stopped")).toBe("stopped");
    expect(mapControlPlaneAgentStatus("failed")).toBe("error");
    expect(mapControlPlaneAgentStatus("error")).toBe("error");
  });

  it("defaults unknown statuses to idle", () => {
    expect(mapControlPlaneAgentStatus("")).toBe("idle");
    expect(mapControlPlaneAgentStatus("provisioning")).toBe("idle");
  });
});
