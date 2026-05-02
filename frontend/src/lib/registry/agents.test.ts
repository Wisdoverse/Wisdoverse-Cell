import { describe, it, expect } from "vitest";
import {
  AGENT_REGISTRY,
  getAgentMeta,
  getAgentsByDomain,
  getAllAgents,
} from "./agents";

describe("Agent Registry", () => {
  it("should have requirement-manager registered", () => {
    const rm = getAgentMeta("requirement-manager");
    expect(rm.name).toBe("Requirements Module");
    expect(rm.shortName).toBe("RM");
    expect(rm.domain).toBe("product");
    expect(rm.icon).toBe("ClipboardList");
  });

  it("should return agents by domain", () => {
    const productAgents = getAgentsByDomain("product");
    expect(productAgents.length).toBeGreaterThanOrEqual(1);
    expect(productAgents[0].domain).toBe("product");
  });

  it("should throw for unknown agent", () => {
    expect(() => getAgentMeta("nonexistent")).toThrow();
  });

  it("should have all agents assigned to valid domains", () => {
    const validDomains = [
      "product", "engineering", "quality",
      "operations", "business", "market-sales", "data-ai",
    ];
    Object.values(AGENT_REGISTRY).forEach((agent) => {
      expect(validDomains).toContain(agent.domain);
    });
  });

  it("should return all agents via getAllAgents", () => {
    const all = getAllAgents();
    expect(all.length).toBe(Object.keys(AGENT_REGISTRY).length);
  });
});
