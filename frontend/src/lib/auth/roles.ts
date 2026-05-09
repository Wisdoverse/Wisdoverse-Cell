export type UserRole = "admin" | "manager" | "viewer";

export const USER_ROLES: readonly UserRole[] = ["admin", "manager", "viewer"];

const ROLE_HIERARCHY: Record<UserRole, number> = {
  admin: 3,
  manager: 2,
  viewer: 1,
};

export function parseAuthRole(value: string | undefined): UserRole {
  if (USER_ROLES.includes(value as UserRole)) {
    return value as UserRole;
  }
  return "admin";
}

/**
 * Check if a user role meets the required role level.
 * admin > manager > viewer
 */
export function hasRequiredRole(userRole: UserRole | undefined, requiredRole: UserRole): boolean {
  if (!userRole) return false;
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole];
}
