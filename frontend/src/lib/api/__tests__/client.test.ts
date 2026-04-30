import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// We test the apiClient exported from client.ts.
// Auth is handled via `credentials: "include"` (HttpOnly cookie forwarding).
// No session preflight — each API call is a single fetch.
// ---------------------------------------------------------------------------

let apiClient: typeof import("@/lib/api/client")["apiClient"];
let ApiClientError: typeof import("@/lib/api/client")["ApiClientError"];
let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(async () => {
  mockFetch = vi.fn();
  vi.stubGlobal("fetch", mockFetch);

  // Re-import so each test gets a fresh module
  vi.resetModules();
  const mod = await import("@/lib/api/client");
  apiClient = mod.apiClient;
  ApiClientError = mod.ApiClientError;
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function mockResponse(data: unknown, status = 200) {
  mockFetch.mockResolvedValueOnce(
    new Response(JSON.stringify(data), { status }),
  );
}

// -------------------------------------------------------------------------
// Tests
// -------------------------------------------------------------------------

describe("apiClient", () => {
  describe("GET requests", () => {
    it("returns parsed JSON on a successful GET", async () => {
      const payload = { items: [{ id: "1" }], total: 1 };
      mockResponse(payload);

      const result = await apiClient.get("/requirements");
      expect(result).toEqual(payload);

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain("/requirements");
      expect(opts.credentials).toBe("include");
    });

    it("retries on 500 server error and eventually succeeds", async () => {
      // 1st attempt: 500
      mockResponse({ detail: "Internal" }, 500);
      // 2nd attempt (retry): success
      const payload = { ok: true };
      mockResponse(payload);

      const result = await apiClient.get("/test");
      expect(result).toEqual(payload);
      // 2 calls total: 500 + 200
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it("does NOT retry on 4xx client errors", async () => {
      mockResponse({ detail: "Not found" }, 404);

      await expect(apiClient.get("/missing")).rejects.toThrow(ApiClientError);
      // Only 1 call: the 404 response (no retry)
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe("timeout handling", () => {
    it("sets up an AbortController with a 10s timeout", async () => {
      mockResponse({ ok: true });

      await apiClient.post("/test");

      const [, opts] = mockFetch.mock.calls[0];
      expect(opts.signal).toBeInstanceOf(AbortSignal);
    });

    it("throws ApiClientError with status 408 on timeout", async () => {
      mockFetch.mockRejectedValueOnce(
        new DOMException("The operation was aborted", "AbortError"),
      );

      await expect(apiClient.post("/slow")).rejects.toThrow(
        expect.objectContaining({
          name: "ApiClientError",
          status: 408,
        }),
      );
    });
  });

  describe("POST requests", () => {
    it("sends JSON body on POST", async () => {
      const body = { title: "New req" };
      const response = { id: "1", ...body };
      mockResponse(response);

      const result = await apiClient.post("/requirements", body);
      expect(result).toEqual(response);

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [, opts] = mockFetch.mock.calls[0];
      expect(opts.method).toBe("POST");
      expect(JSON.parse(opts.body)).toEqual(body);
    });
  });
});
