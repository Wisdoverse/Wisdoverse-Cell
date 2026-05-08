import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createBootstrapAdmin,
  hasBootstrapAdmin,
  isBootstrapSetupRequiredForLogin,
  verifyBootstrapAdminCredentials,
} from "./bootstrap-admin";

let tempDir: string;

beforeEach(async () => {
  tempDir = await mkdtemp(path.join(tmpdir(), "projectcell-admin-"));
  vi.stubEnv("WEBUI_ADMIN_STORE_PATH", path.join(tempDir, "webui-admin.json"));
});

afterEach(async () => {
  vi.unstubAllEnvs();
  await rm(tempDir, { recursive: true, force: true });
});

describe("bootstrap admin store", () => {
  it("creates the first admin with a hashed password and verifies credentials", async () => {
    const result = await createBootstrapAdmin({
      username: "Admin@Example.com",
      displayName: "Operator",
      password: "valid-admin-password",
    });

    expect(result.created).toBe(true);
    expect(await hasBootstrapAdmin()).toBe(true);
    const admin = await verifyBootstrapAdminCredentials("admin@example.com", "valid-admin-password");
    expect(admin).toMatchObject({
      username: "admin@example.com",
      displayName: "Operator",
      role: "admin",
    });

    const store = await readFile(path.join(tempDir, "webui-admin.json"), "utf-8");
    expect(store).not.toContain("valid-admin-password");
    expect(store).toContain("passwordHash");
  });

  it("does not overwrite an existing admin", async () => {
    await createBootstrapAdmin({
      username: "admin@example.com",
      password: "first-pass",
    });

    const result = await createBootstrapAdmin({
      username: "other@example.com",
      password: "second-pass",
    });

    expect(result).toEqual({ created: false, reason: "exists" });
    expect(await verifyBootstrapAdminCredentials("admin@example.com", "first-pass")).not.toBeNull();
    expect(await verifyBootstrapAdminCredentials("other@example.com", "second-pass")).toBeNull();
  });

  it("treats malformed login usernames as invalid credentials", async () => {
    await createBootstrapAdmin({
      username: "admin@example.com",
      password: "first-pass",
    });

    await expect(verifyBootstrapAdminCredentials("admin", "first-pass")).resolves.toBeNull();
  });

  it("requires setup for login when no admin exists", async () => {
    await expect(isBootstrapSetupRequiredForLogin()).resolves.toBe(true);
  });

  it("does not require setup after an admin exists", async () => {
    await createBootstrapAdmin({
      username: "admin@example.com",
      password: "first-pass",
    });

    await expect(isBootstrapSetupRequiredForLogin()).resolves.toBe(false);
  });
});
