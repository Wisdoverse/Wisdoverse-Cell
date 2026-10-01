import { describe, expect, it, vi } from "vitest";

import { withIdempotencyKey } from "./use-control-plane-workbench";

describe("work-item run idempotency", () => {
  it("creates a UUID once for a new user submission", () => {
    const randomUUID = vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue("0e4d7b94-498c-41f5-8cc5-8c1c2c31a2d9");
    const request = withIdempotencyKey({ actor_id: "human:operator" });
    expect(request.idempotency_key).toBe("0e4d7b94-498c-41f5-8cc5-8c1c2c31a2d9");
    randomUUID.mockRestore();
  });

  it("preserves the key when the same payload is retried", () => {
    const request = { actor_id: "human:operator", idempotency_key: "stable-key" };
    expect(withIdempotencyKey(request)).toEqual(request);
  });

  it("reuses a matching approved execution key for an approval resubmission", () => {
    const randomUUID = vi.spyOn(globalThis.crypto, "randomUUID");
    const request = withIdempotencyKey({ actor_id: "human:operator" }, "approved-execution-key");
    expect(request.idempotency_key).toBe("approved-execution-key");
    expect(randomUUID).not.toHaveBeenCalled();
    randomUUID.mockRestore();
  });
});
