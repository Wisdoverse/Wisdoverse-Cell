import { randomBytes, scrypt as scryptCallback, timingSafeEqual } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import { getEnvValue } from "./env";
import type { UserRole } from "./roles";

const scrypt = promisify(scryptCallback);
const PASSWORD_KEY_BYTES = 64;
const MIN_PASSWORD_LENGTH = 8;

export type BootstrapAdminPublic = {
  id: string;
  username: string;
  email: string;
  displayName: string;
  role: UserRole;
  createdAt: string;
};

type BootstrapAdminRecord = BootstrapAdminPublic & {
  schemaVersion: 1;
  passwordHash: string;
  passwordSalt: string;
};

type CreateBootstrapAdminInput = {
  username: string;
  password: string;
  displayName?: string;
};

export class BootstrapAdminValidationError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "BootstrapAdminValidationError";
    this.code = code;
  }
}

export function getBootstrapAdminStorePath(): string {
  const configuredPath = getEnvValue("WEBUI_ADMIN_STORE_PATH");
  const storePath = configuredPath ?? ".data/webui-admin.json";
  return path.isAbsolute(storePath)
    ? storePath
    : path.join(/*turbopackIgnore: true*/ process.cwd(), storePath);
}

export async function hasBootstrapAdmin(): Promise<boolean> {
  await ensureConfiguredBootstrapAdmin();
  return (await readBootstrapAdminRecord()) !== null;
}

export async function isBootstrapSetupRequiredForLogin(): Promise<boolean> {
  return !(await hasBootstrapAdmin());
}

export async function createBootstrapAdmin(
  input: CreateBootstrapAdminInput,
): Promise<{ created: true; admin: BootstrapAdminPublic } | { created: false; reason: "exists" }> {
  if ((await readBootstrapAdminRecord()) !== null) {
    return { created: false, reason: "exists" };
  }

  const username = normalizeUsername(input.username);
  const password = validatePassword(input.password);
  const displayName = normalizeDisplayName(input.displayName, username);
  const createdAt = new Date().toISOString();
  const passwordSalt = randomBytes(16).toString("base64");
  const passwordHash = await derivePasswordHash(password, passwordSalt);
  const record: BootstrapAdminRecord = {
    schemaVersion: 1,
    id: username,
    username,
    email: username,
    displayName,
    role: "admin",
    createdAt,
    passwordHash,
    passwordSalt,
  };

  const storePath = getBootstrapAdminStorePath();
  await mkdir(path.dirname(storePath), { recursive: true });

  try {
    await writeFile(storePath, `${JSON.stringify(record, null, 2)}\n`, {
      encoding: "utf-8",
      flag: "wx",
      mode: 0o600,
    });
  } catch (error) {
    if (isNodeError(error) && error.code === "EEXIST") {
      return { created: false, reason: "exists" };
    }
    throw error;
  }

  return { created: true, admin: toPublicAdmin(record) };
}

export async function verifyBootstrapAdminCredentials(
  username: string,
  password: string,
): Promise<BootstrapAdminPublic | null> {
  await ensureConfiguredBootstrapAdmin();
  const record = await readBootstrapAdminRecord();
  if (!record) return null;
  const normalizedUsername = tryNormalizeUsername(username);
  if (!normalizedUsername || normalizedUsername !== record.username) return null;

  const candidate = await derivePasswordHash(password, record.passwordSalt);
  const stored = Buffer.from(record.passwordHash, "base64");
  const attempted = Buffer.from(candidate, "base64");
  if (stored.length !== attempted.length || !timingSafeEqual(stored, attempted)) {
    return null;
  }

  return toPublicAdmin(record);
}

async function ensureConfiguredBootstrapAdmin(): Promise<void> {
  if (getEnvValue("WEBUI_BOOTSTRAP_ADMIN_ENABLED") !== "true") {
    return;
  }

  await seedConfiguredBootstrapAdmin();
}

async function seedConfiguredBootstrapAdmin(): Promise<void> {
  if ((await readBootstrapAdminRecord()) !== null) {
    return;
  }

  const username = getEnvValue("WEBUI_BOOTSTRAP_ADMIN_USERNAME");
  const password = getEnvValue("WEBUI_BOOTSTRAP_ADMIN_PASSWORD");
  if (!username || !password) {
    throw new Error(
      "WEBUI_BOOTSTRAP_ADMIN_USERNAME and WEBUI_BOOTSTRAP_ADMIN_PASSWORD are required when WEBUI_BOOTSTRAP_ADMIN_ENABLED=true",
    );
  }

  await createBootstrapAdmin({
    username,
    password,
    displayName: getEnvValue("WEBUI_BOOTSTRAP_ADMIN_DISPLAY_NAME"),
  });
}

async function readBootstrapAdminRecord(): Promise<BootstrapAdminRecord | null> {
  try {
    const raw = await readFile(getBootstrapAdminStorePath(), "utf-8");
    return parseBootstrapAdminRecord(JSON.parse(raw));
  } catch (error) {
    if (isNodeError(error) && error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

function parseBootstrapAdminRecord(value: unknown): BootstrapAdminRecord {
  if (!value || typeof value !== "object") {
    throw new Error("Invalid bootstrap admin record");
  }
  const record = value as Partial<BootstrapAdminRecord>;
  if (
    record.schemaVersion !== 1 ||
    typeof record.username !== "string" ||
    typeof record.email !== "string" ||
    typeof record.displayName !== "string" ||
    record.role !== "admin" ||
    typeof record.createdAt !== "string" ||
    typeof record.passwordHash !== "string" ||
    typeof record.passwordSalt !== "string"
  ) {
    throw new Error("Invalid bootstrap admin record");
  }
  return {
    schemaVersion: 1,
    id: record.id ?? record.username,
    username: record.username,
    email: record.email,
    displayName: record.displayName,
    role: record.role,
    createdAt: record.createdAt,
    passwordHash: record.passwordHash,
    passwordSalt: record.passwordSalt,
  };
}

function normalizeUsername(value: string): string {
  const username = value.trim().toLowerCase();
  if (username.length > 120) {
    throw new BootstrapAdminValidationError("username_too_long", "Admin username is too long");
  }
  if (!isValidEmailUsername(username)) {
    throw new BootstrapAdminValidationError("invalid_username", "Admin username must be an email");
  }
  return username;
}

function isValidEmailUsername(username: string): boolean {
  const atIndex = username.indexOf("@");
  const lastAtIndex = username.lastIndexOf("@");
  if (atIndex <= 0 || atIndex !== lastAtIndex || atIndex === username.length - 1) {
    return false;
  }

  const localPart = username.slice(0, atIndex);
  const domain = username.slice(atIndex + 1);
  const dotIndex = domain.indexOf(".");
  if (dotIndex <= 0 || dotIndex === domain.length - 1) {
    return false;
  }

  return !hasWhitespace(localPart) && !hasWhitespace(domain);
}

function hasWhitespace(value: string): boolean {
  for (const character of value) {
    if (
      character === " " ||
      character === "\t" ||
      character === "\n" ||
      character === "\r" ||
      character === "\f" ||
      character === "\v"
    ) {
      return true;
    }
  }
  return false;
}

function tryNormalizeUsername(value: string): string | null {
  try {
    return normalizeUsername(value);
  } catch (error) {
    if (error instanceof BootstrapAdminValidationError) {
      return null;
    }
    throw error;
  }
}

function normalizeDisplayName(value: string | undefined, username: string): string {
  const displayName = value?.trim() || "Admin";
  if (displayName.length > 80) {
    throw new BootstrapAdminValidationError("display_name_too_long", "Display name is too long");
  }
  return displayName || username;
}

function validatePassword(value: string): string {
  if (value.length < MIN_PASSWORD_LENGTH) {
    throw new BootstrapAdminValidationError(
      "password_too_short",
      `Password must be at least ${MIN_PASSWORD_LENGTH} characters`,
    );
  }
  if (value.length > 256) {
    throw new BootstrapAdminValidationError("password_too_long", "Password is too long");
  }
  return value;
}

async function derivePasswordHash(password: string, salt: string): Promise<string> {
  const key = (await scrypt(password, salt, PASSWORD_KEY_BYTES)) as Buffer;
  return key.toString("base64");
}

function toPublicAdmin(record: BootstrapAdminRecord): BootstrapAdminPublic {
  return {
    id: record.id,
    username: record.username,
    email: record.email,
    displayName: record.displayName,
    role: record.role,
    createdAt: record.createdAt,
  };
}

function isNodeError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error;
}
