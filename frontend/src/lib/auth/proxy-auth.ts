import NextAuth from "next-auth";

import { authCallbacks, authPages, authSession } from "./session";

export const { auth } = NextAuth({
  providers: [],
  session: authSession,
  pages: authPages,
  callbacks: authCallbacks,
  trustHost: true,
});
