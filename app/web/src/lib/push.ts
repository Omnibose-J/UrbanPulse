/** Weekend reminder: the pure parts. Request validation at the boundary, the weekend dates, and the message text.
 * Sending and storage live in the route handlers. */
import { kstParts } from "./format.ts";
import { addDays } from "./kst.ts";

export type Subscription = { endpoint: string; keys: { p256dh: string; auth: string }; expirationTime?: number | null };

export type SubscribeBody = {
  subscription: Subscription;
  locale: "ko" | "en";
  place_ids: string[];
  tolerance: "calm" | "moderate" | "busy_ok";
  purpose: "sight" | "food" | "shop";
};

const PLACE_ID = /^[A-Z]{3}\d{3}$/;
const MAX_PLACES = 20;

/** The body of `POST /api/push/subscribe`. Anything missing or malformed is a 400 with the field named. */
export function parseSubscribeBody(input: unknown): { ok: true; body: SubscribeBody } | { ok: false; error: string } {
  if (!input || typeof input !== "object") return { ok: false, error: "body must be an object" };
  const raw = input as Record<string, unknown>;
  const sub = raw.subscription as Record<string, unknown> | undefined;
  if (!sub || typeof sub !== "object") return { ok: false, error: "subscription missing" };
  if (typeof sub.endpoint !== "string" || !/^https:\/\/\S{1,2000}$/.test(sub.endpoint)) return { ok: false, error: "subscription.endpoint invalid" };
  const keys = sub.keys as Record<string, unknown> | undefined;
  if (!keys || typeof keys.p256dh !== "string" || typeof keys.auth !== "string" || !keys.p256dh || !keys.auth) return { ok: false, error: "subscription.keys invalid" };
  if (raw.locale !== "ko" && raw.locale !== "en") return { ok: false, error: "locale invalid" };
  if (!Array.isArray(raw.place_ids) || raw.place_ids.length === 0 || raw.place_ids.length > MAX_PLACES || !raw.place_ids.every((id) => typeof id === "string" && PLACE_ID.test(id))) {
    return { ok: false, error: `place_ids must be 1 to ${MAX_PLACES} place ids` };
  }
  if (raw.tolerance !== "calm" && raw.tolerance !== "moderate" && raw.tolerance !== "busy_ok") return { ok: false, error: "tolerance invalid" };
  if (raw.purpose !== "sight" && raw.purpose !== "food" && raw.purpose !== "shop") return { ok: false, error: "purpose invalid" };
  return {
    ok: true,
    body: {
      subscription: { endpoint: sub.endpoint, keys: { p256dh: keys.p256dh, auth: keys.auth }, expirationTime: typeof sub.expirationTime === "number" ? sub.expirationTime : null },
      locale: raw.locale,
      place_ids: [...new Set(raw.place_ids as string[])],
      tolerance: raw.tolerance,
      purpose: raw.purpose,
    },
  };
}

/** The coming Saturday and Sunday (KST dates). On a Saturday or Sunday it is the current weekend. */
export function weekendDates(today: string): [string, string] {
  const weekday = kstParts(today).weekday; // 0 Sun .. 6 Sat
  if (weekday === 0) return [addDays(today, -1), today];
  const toSaturday = 6 - weekday;
  const saturday = addDays(today, toSaturday);
  return [saturday, addDays(saturday, 1)];
}

export type WeekendPick = { place_id: string; name: string; name_en: string | null; date: string; range: string };

export type Copy = { title: string; line: (name: string, day: string, range: string) => string; none: string; sat: string; sun: string };

/** One notification per subscriber: a line per saved place that has a weekend pick, nothing for a place without one.
 * Returns null when no saved place has a pick, so nothing is sent. */
export function weekendMessage(picks: WeekendPick[], locale: "ko" | "en", copy: Copy, saturday: string): { title: string; body: string } | null {
  if (picks.length === 0) return null;
  const lines = picks.map((pick) => copy.line(locale === "en" && pick.name_en ? pick.name_en : pick.name, pick.date === saturday ? copy.sat : copy.sun, pick.range));
  return { title: copy.title, body: lines.join("\n") };
}
