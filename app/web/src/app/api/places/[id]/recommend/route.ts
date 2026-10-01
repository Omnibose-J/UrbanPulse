import { jsonFail, jsonOk, logApiError, readDate, readPurpose, readTolerance } from "@/lib/http";
import { kstNow } from "@/lib/kst";
import { recommendPayload } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const url = new URL(request.url);
  const date = readDate(url.searchParams.get("date"));
  const tolerance = readTolerance(url.searchParams.get("tolerance"));
  const purpose = readPurpose(url.searchParams.get("purpose"));
  if (!date || !tolerance || !purpose) return jsonFail(400, "invalid date, tolerance, or purpose");
  const today = kstNow().date;
  if (date < today) return jsonFail(410, "date has passed");
  try {
    const body = await recommendPayload(id, date, tolerance, purpose, today);
    if (!body) return jsonFail(404, "unknown place");
    if (body === "gone") return jsonFail(410, "date has passed");
    return jsonOk(body);
  } catch (error) {
    logApiError("places/recommend", error);
    return jsonFail(500, "unavailable");
  }
}
