import { NextResponse, type NextRequest } from "next/server";

function localeFrom(request: NextRequest, pathname: string): "ko" | "en" {
  if (pathname === "/en" || pathname.startsWith("/en/")) return "en";
  if (pathname === "/ko" || pathname.startsWith("/ko/")) return "ko";
  const preferred = request.headers.get("accept-language")?.split(",")[0]?.split(";")[0]?.trim().toLowerCase() ?? "";
  return preferred.startsWith("en") ? "en" : "ko";
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return NextResponse.next();
  const hasLocale = pathname === "/ko" || pathname.startsWith("/ko/") || pathname === "/en" || pathname.startsWith("/en/");
  if (!hasLocale) {
    const url = request.nextUrl.clone();
    const locale = localeFrom(request, pathname);
    url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
    return NextResponse.redirect(url);
  }
  const headers = new Headers(request.headers);
  headers.set("x-next-intl-locale", localeFrom(request, pathname));
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
