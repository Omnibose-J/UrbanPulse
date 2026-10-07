import { NextResponse } from "next/server";
import webpush from "web-push";

import { formatStoredWindows } from "@/lib/format";
import { jsonFail, logApiError } from "@/lib/http";
import { kstNow } from "@/lib/kst";
import { weekendDates, weekendMessage, type Copy } from "@/lib/push";
import { deleteSubscription, listSubscriptions, markSent, weekendPicks } from "@/lib/queries";
import en from "../../../../../messages/en.json";
import ko from "../../../../../messages/ko.json";

export const dynamic = "force-dynamic";
export const maxDuration = 60;
// web-push sets no timeout of its own; one push service that never answers would otherwise hold the whole run.
const SEND_TIMEOUT_MS = 8000;

/** Friday 18:00 KST (Vercel Cron, `vercel.json`): one notification per subscriber naming the best weekend pick of
 * each saved place under the subscriber's own conditions. A subscriber whose places have no weekend pick gets
 * nothing. Endpoints the push service reports gone (404, 410) are removed. */
export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (!secret) return jsonFail(500, "missing env var: CRON_SECRET");
  if (request.headers.get("authorization") !== `Bearer ${secret}`) return jsonFail(401, "unauthorized");
  const vapid = { publicKey: process.env.VAPID_PUBLIC_KEY, privateKey: process.env.VAPID_PRIVATE_KEY, subject: process.env.VAPID_SUBJECT };
  if (!vapid.publicKey || !vapid.privateKey || !vapid.subject) return jsonFail(500, "missing env var: VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY or VAPID_SUBJECT");
  webpush.setVapidDetails(vapid.subject, vapid.publicKey, vapid.privateKey);
  const origin = new URL(request.url).origin;
  const [saturday, sunday] = weekendDates(kstNow().date);
  const counts = { subscribers: 0, sent: 0, skipped: 0, removed: 0, failed: 0 };
  try {
    const subscriptions = await listSubscriptions();
    counts.subscribers = subscriptions.length;
    for (const row of subscriptions) {
      const messages = row.locale === "en" ? en : ko;
      const copy: Copy = {
        title: messages.push.title,
        line: (name, day, range) => messages.push.line.replace("{place}", name).replace("{day}", day).replace("{time}", range),
        none: "",
        sat: messages.time.weekdays[6],
        sun: messages.time.weekdays[0],
      };
      const picks = (await weekendPicks(row.place_ids, [saturday, sunday], row.tolerance, row.purpose)).map((pick) => ({
        ...pick,
        range: formatStoredWindows(pick.windows, row.locale, messages.time.hour)[0],
      }));
      const message = weekendMessage(picks, row.locale, copy, saturday);
      if (!message) {
        counts.skipped += 1;
        continue;
      }
      const first = picks[0];
      const url = `${origin}/${row.locale}/p/${first.place_id}/${first.date}`;
      try {
        await webpush.sendNotification(row.subscription, JSON.stringify({ ...message, url }), { TTL: 60 * 60 * 24, timeout: SEND_TIMEOUT_MS });
        await markSent(row.endpoint);
        counts.sent += 1;
      } catch (error) {
        const status = (error as { statusCode?: number }).statusCode;
        if (status === 404 || status === 410) {
          try {
            await deleteSubscription(row.endpoint);
            counts.removed += 1;
          } catch (deleteError) {
            // One row that cannot be removed must not stop the reminders of everyone after it.
            logApiError("push/weekend", deleteError);
            counts.failed += 1;
          }
        } else {
          logApiError("push/weekend", error);
          counts.failed += 1;
        }
      }
    }
    return NextResponse.json({ saturday, sunday, ...counts }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    logApiError("push/weekend", error);
    return jsonFail(500, "unavailable");
  }
}
