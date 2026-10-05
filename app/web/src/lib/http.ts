import { NextResponse } from "next/server";

const NO = { "Cache-Control": "no-store" };

/** Stored rows change at most every 30 minutes (collect) and once a day (forecast), so the edge may hold a success
 * for `ttl` seconds; a route that carries "now" passes a shorter one. The edge strips `s-maxage` from what the
 * browser sees and keeps `public`, so the browser itself never caches. Errors are never cacheable. */
export function jsonOk(body: unknown, ttl = 300) {
  return NextResponse.json(body, { headers: { "Cache-Control": `public, s-maxage=${ttl}` } });
}

export function jsonFail(status: number, error: string) {
  return NextResponse.json({ error }, { status, headers: NO });
}

export { logApiError } from "@/lib/api-log";

const TOLERANCES = new Set(["calm", "moderate", "busy_ok"]);
const PURPOSES = new Set(["sight", "food", "shop", "none"]);

export function readTolerance(value: string | null): string | null {
  if (!value || !TOLERANCES.has(value)) return null;
  return value;
}

export function readPurpose(value: string | null): string | null {
  if (!value || !PURPOSES.has(value)) return null;
  return value;
}

export { inServedRange } from "@/lib/kst";

export function readDate(value: string | null): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const utc = new Date(Date.UTC(year, month - 1, day));
  if (utc.getUTCFullYear() !== year || utc.getUTCMonth() !== month - 1 || utc.getUTCDate() !== day) return null;
  return value;
}
