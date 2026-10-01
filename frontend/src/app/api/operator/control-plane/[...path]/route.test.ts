import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const authMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth/config", () => ({ auth: authMock }));

import { GET, POST } from "./route";

const context = { params: Promise.resolve({ path: ["executions", "run-1", "control"] }) };

describe("operator control plane proxy", () => {
  beforeEach(() => {
    vi.stubEnv("CONTROL_PLANE_OPERATOR_TOKEN", "server-secret");
    vi.stubEnv("CONTROL_PLANE_INTERNAL_KEY", "internal-secret");
    vi.stubEnv("CONTROL_PLANE_API_BASE_URL", "http://control-plane.test/api/v1");
    authMock.mockReset();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ state: "requested" }), {
      status: 200,
      headers: {
        "X-Control-Plane-Operator-Token": "upstream-secret",
        "X-Internal-Key": "upstream-internal-secret",
      },
    })));
  });

  it("forwards authenticated operations using only the server-held operator credential", async () => {
    authMock.mockResolvedValue({ user: { role: "admin" } });
    const request = new NextRequest("http://localhost/api/operator/control-plane/executions/run-1/control", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost", "X-Control-Plane-Operator-Token": "attacker-value" },
      body: JSON.stringify({ company_id: "co-1", action: "pause", reason: "review" }),
    });
    const response = await POST(request, context);
    expect(response.status).toBe(200);
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe("http://control-plane.test/api/v1/control-plane/executions/run-1/control");
    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get("X-Control-Plane-Operator-Token")).toBe("server-secret");
    expect(new Headers(init.headers).get("X-Control-Plane-Operator-Token")).not.toBe("attacker-value");
    expect(new Headers(init.headers).get("X-Internal-Key")).toBe("internal-secret");
    expect(response.headers.get("X-Control-Plane-Operator-Token")).toBeNull();
    expect(response.headers.get("X-Internal-Key")).toBeNull();
  });

  it("denies reads and writes to non-admin users before contacting the backend", async () => {
    authMock.mockResolvedValue({ user: { role: "viewer" } });
    const request = new NextRequest("http://localhost/api/operator/control-plane/executions", {
      method: "POST", headers: { "content-type": "application/json", origin: "http://localhost" }, body: "{}",
    });
    const response = await POST(request, context);
    expect(response.status).toBe(403);
    const readResponse = await GET(new NextRequest("http://localhost/api/operator/control-plane/executions"), context);
    expect(readResponse.status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("requires both server-side credentials", async () => {
    authMock.mockResolvedValue({ user: { role: "admin" } });
    vi.stubEnv("CONTROL_PLANE_INTERNAL_KEY", "");
    vi.stubEnv("INTERNAL_SERVICE_KEY", "");
    const request = new NextRequest("http://localhost/api/operator/control-plane/executions");
    const response = await GET(request, context);
    expect(response.status).toBe(503);
    expect(fetch).not.toHaveBeenCalled();

    vi.stubEnv("CONTROL_PLANE_INTERNAL_KEY", "internal-secret");
    vi.stubEnv("CONTROL_PLANE_OPERATOR_TOKEN", "");
    const missingOperator = await GET(request, context);
    expect(missingOperator.status).toBe(503);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uses the documented internal service key fallback", async () => {
    authMock.mockResolvedValue({ user: { role: "admin" } });
    vi.stubEnv("CONTROL_PLANE_INTERNAL_KEY", "");
    vi.stubEnv("INTERNAL_SERVICE_KEY", "fallback-secret");
    await GET(new NextRequest("http://localhost/api/operator/control-plane/executions"), context);
    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get("X-Internal-Key")).toBe("fallback-secret");
  });

  it("rejects writes when the same-origin browser header is absent", async () => {
    authMock.mockResolvedValue({ user: { role: "admin" } });
    const request = new NextRequest("http://localhost/api/operator/control-plane/executions/run-1/control", {
      method: "POST", headers: { "content-type": "application/json" }, body: "{}",
    });
    const response = await POST(request, context);
    expect(response.status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("preserves backend company-scope denials for requests outside the operator grant", async () => {
    authMock.mockResolvedValue({ user: { role: "admin" } });
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "operator_scope_denied" }), { status: 403 }));
    const request = new NextRequest("http://localhost/api/operator/control-plane/executions/run-1/control", {
      method: "POST", headers: { "content-type": "application/json", origin: "http://localhost" },
      body: JSON.stringify({ company_id: "out-of-scope", action: "pause", reason: "review" }),
    });
    const response = await POST(request, context);
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ detail: "operator_scope_denied" });
  });
});
