import { describe, it, expect } from "vitest";
import { DOMAINS, getDomainConfig, DOMAIN_LIST } from "./domains";

describe("Domain Registry", () => {
  it("should define all 7 domains", () => {
    expect(Object.keys(DOMAINS)).toHaveLength(7);
  });

  it("should return config for a valid domain", () => {
    const config = getDomainConfig("product");
    expect(config.label).toBe("Product");
    expect(config.color).toBe("#8B5CF6");
    expect(config.icon).toBe("Package");
  });

  it("should return config for data-ai domain", () => {
    const config = getDomainConfig("data-ai");
    expect(config.label).toBe("Data & AI");
    expect(config.color).toBe("#06B6D4");
  });

  it("should return config for market-sales domain", () => {
    const config = getDomainConfig("market-sales");
    expect(config.label).toBe("Market & Sales");
    expect(config.color).toBe("#F97316");
  });

  it("should throw for unknown domain", () => {
    expect(() => getDomainConfig("unknown" as never)).toThrow();
  });

  it("should have DOMAIN_LIST with all domains", () => {
    expect(DOMAIN_LIST).toHaveLength(7);
  });
});
