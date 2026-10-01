import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api/client";
import { reconcileEvolutionRelease, recoverEvolutionRelease } from "./evolution-operations";

vi.mock("@/lib/api/client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

describe("evolution release reconciliation", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset().mockResolvedValue({ state: "acknowledged" }));

  it("queries the existing pending release without sending a new release payload", async () => {
    await reconcileEvolutionRelease("proposal-1", "company 1");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/control-plane/evolution-proposals/proposal-1/release/reconcile?company_id=company%201",
    );
  });

  it("recovers an existing pending release only through the explicit recovery endpoint", async () => {
    await recoverEvolutionRelease("proposal-1", "company 1");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/control-plane/evolution-proposals/proposal-1/release/recover?company_id=company%201",
    );
  });
});
