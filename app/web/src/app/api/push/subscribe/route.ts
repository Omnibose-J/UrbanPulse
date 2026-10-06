import { jsonFail, logApiError } from "@/lib/http";
import { parseSubscribeBody } from "@/lib/push";
import { deleteSubscription, upsertSubscription } from "@/lib/queries";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

async function readJson(request: Request): Promise<unknown | undefined> {
  try {
    return await request.json();
  } catch {
    return undefined;
  }
}

/** The browser registers (or re-registers) its push endpoint with the places and conditions to remind about. */
export async function POST(request: Request) {
  const parsed = parseSubscribeBody(await readJson(request));
  if (!parsed.ok) return jsonFail(400, parsed.error);
  try {
    await upsertSubscription(parsed.body);
    return NextResponse.json({ ok: true }, { headers: NO_STORE });
  } catch (error) {
    logApiError("push/subscribe", error);
    return jsonFail(500, "unavailable");
  }
}

export async function DELETE(request: Request) {
  const body = (await readJson(request)) as { endpoint?: unknown } | undefined;
  if (!body || typeof body.endpoint !== "string" || !body.endpoint.startsWith("https://")) return jsonFail(400, "endpoint invalid");
  try {
    await deleteSubscription(body.endpoint);
    return NextResponse.json({ ok: true }, { headers: NO_STORE });
  } catch (error) {
    logApiError("push/subscribe", error);
    return jsonFail(500, "unavailable");
  }
}
