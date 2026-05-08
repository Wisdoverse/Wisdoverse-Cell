import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

import { authCallbacks, authPages, authSession } from "./session";

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
          typeof credentials?.username === "string" ? credentials.username : undefined;
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

        return null;
      },
    }),
  ],
  session: authSession,
  pages: authPages,
  callbacks: authCallbacks,
  trustHost: true,
});
