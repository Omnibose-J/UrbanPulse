import { NextResponse } from "next/server";

const OK = { "Cache-Control": "public, s-maxage=300" };
const NO = { "Cache-Control": "no-store" };

export function jsonOk(body: unknown) {
  return NextResponse.json(body, { headers: OK });
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
