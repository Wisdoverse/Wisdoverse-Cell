import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import createIntlMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";
import { auth } from "./lib/auth/config";

const intlMiddleware = createIntlMiddleware(routing);

// Paths that don't require authentication
const publicPaths = ["/login"];

function isPublicPath(pathname: string): boolean {
  // Remove locale prefix to check the actual path
  // e.g. /en/login -> /login, /zh/login -> /login
  const segments = pathname.split("/");
  // segments: ["", "en", "login", ...]
  const pathWithoutLocale = "/" + segments.slice(2).join("/");
  return publicPaths.some((p) => pathWithoutLocale.startsWith(p));
}

export default auth((req) => {
  const { pathname } = req.nextUrl;

  // Run the intl middleware first to handle locale routing
  const intlResponse = intlMiddleware(req as unknown as NextRequest);

  // Skip auth check for public paths
  if (isPublicPath(pathname)) {
    return intlResponse;
  }

  // Check if the user is authenticated
  if (!req.auth) {
    // Determine the locale from the URL or default to the first locale
    const segments = pathname.split("/");
    const locale = (routing.locales as readonly string[]).includes(segments[1])
      ? segments[1]
      : routing.defaultLocale;

    const loginUrl = new URL(`/${locale}/login`, req.url);
    loginUrl.searchParams.set("callbackUrl", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return intlResponse;
});

export const config = {
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
