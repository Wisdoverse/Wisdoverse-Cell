import type { NextAuthConfig } from "next-auth";

import type { UserRole } from "./roles";

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

export const authSession = {
  strategy: "jwt",
} satisfies NextAuthConfig["session"];

export const authPages = {
  signIn: "/login",
} satisfies NextAuthConfig["pages"];

export const authCallbacks = {
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
} satisfies NextAuthConfig["callbacks"];
