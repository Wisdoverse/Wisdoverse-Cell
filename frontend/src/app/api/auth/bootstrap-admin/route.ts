import { NextResponse } from "next/server";

import {
  BootstrapAdminValidationError,
  createBootstrapAdmin,
  hasBootstrapAdmin,
} from "@/lib/auth/bootstrap-admin";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({
    bootstrapRequired: !(await hasBootstrapAdmin()),
  });
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const payload = body && typeof body === "object" ? (body as Record<string, unknown>) : {};

  try {
    const result = await createBootstrapAdmin({
      username: typeof payload.username === "string" ? payload.username : "",
      password: typeof payload.password === "string" ? payload.password : "",
      displayName: typeof payload.displayName === "string" ? payload.displayName : undefined,
    });

    if (!result.created) {
      return NextResponse.json({ error: "admin_exists" }, { status: 409 });
    }

    return NextResponse.json({ ok: true, admin: result.admin }, { status: 201 });
  } catch (error) {
    if (error instanceof BootstrapAdminValidationError) {
      return NextResponse.json({ error: error.code }, { status: 400 });
    }
    console.error("[bootstrap-admin] Failed to create initial admin:", error);
    return NextResponse.json({ error: "bootstrap_failed" }, { status: 500 });
  }
}
