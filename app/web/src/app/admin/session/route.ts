import { NextResponse } from "next/server";

import { ADMIN_COOKIE, ADMIN_MAX_AGE, sessionValue, tokenMatches } from "@/lib/admin-session";

export const dynamic = "force-dynamic";

// The token arrives in a form body, never in an address, so it stays out of access logs and browser history.
export async function POST(request: Request) {
  const expected = process.env.ADMIN_TOKEN;
  const form = await request.formData().catch(() => null);
  const given = form ? form.get("token") : null;
  if (!tokenMatches(given, expected)) return NextResponse.redirect(new URL("/admin", request.url), 303);
  const response = NextResponse.redirect(new URL("/admin/eval", request.url), 303);
  response.cookies.set(ADMIN_COOKIE, sessionValue(expected as string), {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/admin",
    maxAge: ADMIN_MAX_AGE,
  });
  return response;
}
