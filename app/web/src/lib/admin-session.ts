import { createHmac, timingSafeEqual } from "node:crypto";

// The admin session cookie. It never holds the token itself: the value is a keyed digest of a fixed label,
// so a leaked cookie does not reveal the token, and rotating ADMIN_TOKEN ends every session.
export const ADMIN_COOKIE = "up_admin";
export const ADMIN_MAX_AGE = 12 * 60 * 60;

function same(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

export function sessionValue(token: string): string {
  return createHmac("sha256", token).update("urbanpulse-admin-session").digest("hex");
}

/** True only for the configured token. An unset ADMIN_TOKEN admits nobody. */
export function tokenMatches(given: unknown, expected: string | undefined): boolean {
  return typeof given === "string" && Boolean(expected) && same(given, expected as string);
}

export function sessionValid(cookie: string | undefined, expected: string | undefined): boolean {
  return Boolean(cookie) && Boolean(expected) && same(cookie as string, sessionValue(expected as string));
}
