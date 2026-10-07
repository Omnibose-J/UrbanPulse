import { NextResponse, type NextRequest } from "next/server";

function localeFrom(request: NextRequest, pathname: string): "ko" | "en" {
  if (pathname === "/en" || pathname.startsWith("/en/")) return "en";
  if (pathname === "/ko" || pathname.startsWith("/ko/")) return "ko";
  const preferred = request.headers.get("accept-language")?.split(",")[0]?.split(";")[0]?.trim().toLowerCase() ?? "";
  return preferred.startsWith("en") ? "en" : "ko";
}

/** The policy for one response. Scripts run only with this request's nonce (Next stamps it on its own tags) or
 * when a nonce'd script loads them (`strict-dynamic`); styles allow inline because the screens set colours through
 * `style=` attributes; the map pulls tiles, sprites and glyphs from OpenFreeMap; the map worker and the push worker
 * are same-origin files. Nothing may frame the site. */
function policy(nonce: string): string {
  const dev = process.env.NODE_ENV === "development";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://tiles.openfreemap.org",
    "font-src 'self'",
    "connect-src 'self' https://tiles.openfreemap.org",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
  ].join("; ");
}

function withPolicy(request: NextRequest, extra?: (headers: Headers) => void) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = policy(nonce);
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  extra?.(headers);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return withPolicy(request);
  const hasLocale = pathname === "/ko" || pathname.startsWith("/ko/") || pathname === "/en" || pathname.startsWith("/en/");
  if (!hasLocale) {
    const url = request.nextUrl.clone();
    const locale = localeFrom(request, pathname);
    url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
    return NextResponse.redirect(url);
  }
  return withPolicy(request, (headers) => headers.set("x-next-intl-locale", localeFrom(request, pathname)));
}

export const config = {
  matcher: [
    {
      // Pages only: data routes and static files need no policy, and a prefetch must not spend a nonce.
      source: "/((?!api|_next/static|_next/image|.*\\..*).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
