import { describe, expect, it } from "vitest";

import { mapControlPlaneLifecycleStatus } from "./status";

describe("mapControlPlaneLifecycleStatus", () => {
  it("keeps paused lifecycle state visible", () => {
    expect(mapControlPlaneLifecycleStatus("paused")).toBe("paused");
    expect(mapControlPlaneLifecycleStatus(" PAUSED ")).toBe("paused");
  });

  it("maps catalog-enabled lifecycle states to idle, not running", () => {
    // `active` is a lifecycle flag, not evidence of an in-flight run.
    // Runtime `running` must come from AgentRun rows.
    expect(mapControlPlaneLifecycleStatus("active")).toBe("idle");
    expect(mapControlPlaneLifecycleStatus("running")).toBe("idle");
  });

  it("maps terminal and failed lifecycle states", () => {
    expect(mapControlPlaneLifecycleStatus("terminated")).toBe("stopped");
    expect(mapControlPlaneLifecycleStatus("stopped")).toBe("stopped");
    expect(mapControlPlaneLifecycleStatus("failed")).toBe("error");
    expect(mapControlPlaneLifecycleStatus("error")).toBe("error");
  });

  it("defaults unknown lifecycle states to idle", () => {
    expect(mapControlPlaneLifecycleStatus("")).toBe("idle");
    expect(mapControlPlaneLifecycleStatus("provisioning")).toBe("idle");
  });
});
