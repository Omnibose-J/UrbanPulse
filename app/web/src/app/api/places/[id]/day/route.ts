import { inServedRange, jsonFail, jsonOk, logApiError, readDate } from "@/lib/http";
import { kstNow } from "@/lib/kst";
import { dayHours } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const date = readDate(new URL(request.url).searchParams.get("date"));
  if (!date) return jsonFail(400, "invalid date");
  const today = kstNow().date;
  if (date < today) return jsonFail(410, "date has passed");
  if (!inServedRange(date, today)) return jsonFail(400, "date beyond the served range");
  try {
    const body = await dayHours(id, date);
    if (!body) return jsonFail(404, "unknown place");
    return jsonOk(body);
  } catch (error) {
    logApiError("places/day", error);
    return jsonFail(500, "unavailable");
  }
}
