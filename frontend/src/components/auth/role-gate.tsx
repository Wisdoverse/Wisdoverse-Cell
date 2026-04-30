"use client";

import { useSession } from "next-auth/react";
import { type UserRole, hasRequiredRole } from "@/lib/auth/config";

interface RoleGateProps {
  role: UserRole;
  children: React.ReactNode;
  /** Optional fallback to render when role check fails */
  fallback?: React.ReactNode;
}

/**
 * Conditionally renders children only if the current user has the required role
 * or higher in the hierarchy: admin > manager > viewer
 */
export function RoleGate({ role, children, fallback = null }: RoleGateProps) {
  const { data: session } = useSession();

  if (!hasRequiredRole(session?.user?.role, role)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
