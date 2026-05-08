import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

export type UserRole = "admin" | "manager" | "viewer";

const ROLE_HIERARCHY: Record<UserRole, number> = {
  admin: 3,
  manager: 2,
  viewer: 1,
};

const USER_ROLES: readonly UserRole[] = ["admin", "manager", "viewer"];

function getEnvValue(name: string): string | undefined {
  const value = process.env[name]?.trim();
  return value ? value : undefined;
}

function parseDevAuthRole(value: string | undefined): UserRole {
  if (USER_ROLES.includes(value as UserRole)) {
    return value as UserRole;
  }
  return "admin";
}

function devAuthEmail(username: string): string {
  return username.includes("@") ? username : `${username}@projectcell.dev`;
}

/**
 * Check if a user role meets the required role level.
 * admin > manager > viewer
 */
export function hasRequiredRole(userRole: UserRole | undefined, requiredRole: UserRole): boolean {
  if (!userRole) return false;
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole];
}

declare module "next-auth" {
  interface User {
    role?: UserRole;
  }

  interface Session {
    user: {
      id?: string;
      name?: string | null;
      email?: string | null;
      image?: string | null;
      role?: UserRole;
    };
  }
}

declare module "@auth/core/jwt" {
  interface JWT {
    role?: UserRole;
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      name: "Credentials",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        // Development credentials require explicit opt-in via ENABLE_DEV_AUTH=true.
        // Real auth via Feishu/WeCom OAuth is configured separately.
        if (process.env.NODE_ENV === "production" || process.env.ENABLE_DEV_AUTH !== "true")
          return null;

        const devUsername = getEnvValue("DEV_AUTH_USERNAME");
        const devPassword = getEnvValue("DEV_AUTH_PASSWORD");
        if (!devUsername || !devPassword) return null;

        const username =
          typeof credentials?.username === "string" ? credentials.username : undefined;
        const password =
          typeof credentials?.password === "string" ? credentials.password : undefined;

        if (!username || !password) return null;
        if (username !== devUsername || password !== devPassword) return null;

        return {
          id: username,
          name: getEnvValue("DEV_AUTH_DISPLAY_NAME") ?? username,
          email: devAuthEmail(username),
          role: parseDevAuthRole(getEnvValue("DEV_AUTH_ROLE")),
        };
      },
    }),
  ],
  session: {
    strategy: "jwt",
  },
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.role = user.role;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.role = token.role;
        session.user.id = token.sub ?? "";
      }
      return session;
    },
  },
  trustHost: true,
});
