import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import createIntlMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";
import { auth } from "./lib/auth/config";

const intlMiddleware = createIntlMiddleware(routing);

// Paths that don't require authentication
const publicPaths = ["/login"];
const locales = routing.locales as readonly string[];

function isPublicPath(pathname: string): boolean {
  // Remove locale prefix to check the actual path
  // e.g. /en/login -> /login, /zh/login -> /login
  const segments = pathname.split("/");
  // segments: ["", "en", "login", ...]
  const pathWithoutLocale = "/" + segments.slice(2).join("/");
  return publicPaths.some((p) => pathWithoutLocale.startsWith(p));
}

function localeFromPath(pathname: string): string {
  const locale = pathname.split("/")[1];
  return locales.includes(locale) ? locale : routing.defaultLocale;
}

function hasLocalePrefix(pathname: string): boolean {
  return locales.includes(pathname.split("/")[1]);
}

function localizedDestination(pathname: string, locale: string): string {
  if (pathname === "/" || pathname === `/${locale}`) {
    return `/${locale}/home`;
  }
  if (!hasLocalePrefix(pathname)) {
    return `/${locale}${pathname}`;
  }
  return pathname;
}

export default auth((req) => {
  const { pathname } = req.nextUrl;
  const locale = localeFromPath(pathname);

  // Skip auth check for public paths
  if (isPublicPath(pathname)) {
    return intlMiddleware(req as unknown as NextRequest);
  }

  const destination = localizedDestination(pathname, locale);

  // Check if the user is authenticated
  if (!req.auth) {
    const loginUrl = new URL(`/${locale}/login`, req.url);
    loginUrl.searchParams.set("callbackUrl", destination);
    return NextResponse.redirect(loginUrl);
  }

  if (destination !== pathname) {
    return NextResponse.redirect(new URL(destination, req.url));
  }

  return intlMiddleware(req as unknown as NextRequest);
});

export const config = {
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
