import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

import { getEnvValue } from "./env";
import { parseAuthRole } from "./roles";
import { authCallbacks, authPages, authSession } from "./session";

function devAuthEmail(username: string): string {
  return username.includes("@") ? username : `${username}@wisdoverse-cell.dev`;
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
        const username =
          typeof credentials?.username === "string"
            ? credentials.username.trim().toLowerCase()
            : undefined;
        const password =
          typeof credentials?.password === "string" ? credentials.password : undefined;

        if (!username || !password) return null;

        const { verifyBootstrapAdminCredentials } = await import("./bootstrap-admin");
        const admin = await verifyBootstrapAdminCredentials(username, password);
        if (admin) {
          return {
            id: admin.id,
            name: admin.displayName,
            email: admin.email,
            role: admin.role,
          };
        }

        if (process.env.ENABLE_DEV_AUTH !== "true") {
          return null;
        }

        const devUsername = getEnvValue("DEV_AUTH_USERNAME");
        const devPassword = getEnvValue("DEV_AUTH_PASSWORD");
        if (!devUsername || !devPassword) return null;
        if (username !== devUsername.toLowerCase() || password !== devPassword) return null;

        return {
          id: username,
          name: getEnvValue("DEV_AUTH_DISPLAY_NAME") ?? getEnvValue("DEV_AUTH_NAME") ?? username,
          email: devAuthEmail(username),
          role: parseAuthRole(getEnvValue("DEV_AUTH_ROLE")),
        };
      },
    }),
  ],
  session: authSession,
  pages: authPages,
  callbacks: authCallbacks,
  trustHost: true,
});
