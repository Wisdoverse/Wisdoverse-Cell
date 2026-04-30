import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

export type UserRole = "admin" | "manager" | "viewer";

const ROLE_HIERARCHY: Record<UserRole, number> = {
  admin: 3,
  manager: 2,
  viewer: 1,
};

/**
 * Check if a user role meets the required role level.
 * admin > manager > viewer
 */
export function hasRequiredRole(
  userRole: UserRole | undefined,
  requiredRole: UserRole,
): boolean {
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
        // Development credentials - requires explicit opt-in via ENABLE_DEV_AUTH=true
        // Real auth via Feishu/WeCom OAuth added later
        if (
          process.env.NODE_ENV === "production" ||
          process.env.ENABLE_DEV_AUTH !== "true"
        )
          return null;

        const devUsers: Record<
          string,
          { password: string; role: UserRole; name: string }
        > = {
          admin: { password: "admin123", role: "admin", name: "Admin" },
          manager: { password: "manager123", role: "manager", name: "Manager" },
          viewer: { password: "viewer123", role: "viewer", name: "Viewer" },
        };

        const username = credentials?.username as string | undefined;
        const password = credentials?.password as string | undefined;

        if (!username || !password) return null;

        const user = devUsers[username];
        if (!user || user.password !== password) return null;

        return {
          id: username,
          name: user.name,
          email: `${username}@projectcell.dev`,
          role: user.role,
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
