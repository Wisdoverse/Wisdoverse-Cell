import { NextResponse, type NextRequest } from "next/server";

import { auth } from "@/lib/auth/config";

export const runtime = "nodejs";

type RouteContext = { params: Promise<{ path: string[] }> };
type Handler = (request: NextRequest, context: RouteContext) => Promise<Response>;

async function proxyControlPlane(request: NextRequest, context: RouteContext): Promise<Response> {
  const session = await auth();
  if (!session?.user) return NextResponse.json({ detail: "authentication_required" }, { status: 401 });

  // The deployment operator token is not tenant-scoped, so only board admins
  // may use this proxy for reads or mutations.
  if (session.user.role !== "admin") {
    return NextResponse.json({ detail: "admin_role_required" }, { status: 403 });
  }
  const origin = request.headers.get("origin");
  if (request.method !== "GET" && origin !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "cross_origin_request_denied" }, { status: 403 });
  }

  const operatorToken = process.env.CONTROL_PLANE_OPERATOR_TOKEN?.trim();
  const internalKey = process.env.CONTROL_PLANE_INTERNAL_KEY?.trim() || process.env.INTERNAL_SERVICE_KEY?.trim();
  if (!operatorToken || !internalKey) {
    return NextResponse.json({ detail: "operator_proxy_not_configured" }, { status: 503 });
  }

  const { path } = await context.params;
  const safePath = path.map((segment) => encodeURIComponent(segment)).join("/");
  const apiBase = process.env.CONTROL_PLANE_API_BASE_URL?.trim() ||
    (process.env.NODE_ENV === "development"
      ? "http://127.0.0.1:8000/api/v1"
      : "http://cell:8000/api/v1");
  const target = new URL(`${apiBase.replace(/\/$/, "")}/control-plane/${safePath}`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  headers.set("accept", request.headers.get("accept") ?? "application/json");
  headers.set("X-Control-Plane-Operator-Token", operatorToken);
  headers.set("X-Internal-Key", internalKey);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(path.includes("run") ? 120_000 : 30_000),
    });
  } catch {
    return NextResponse.json({ detail: "control_plane_unavailable" }, { status: 502 });
  }

  const responseHeaders = new Headers();
  for (const name of ["content-type", "cache-control", "etag"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: responseHeaders,
  });
}

const handler: Handler = proxyControlPlane;
export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
