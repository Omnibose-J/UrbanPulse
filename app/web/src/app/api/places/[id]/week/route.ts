import { jsonFail, jsonOk, logApiError, readPurpose, readTolerance } from "@/lib/http";
import { weekPayload } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const url = new URL(request.url);
  const tolerance = readTolerance(url.searchParams.get("tolerance"));
  const purpose = readPurpose(url.searchParams.get("purpose"));
  if (!tolerance || !purpose) return jsonFail(400, "invalid tolerance or purpose");
  try {
    const body = await weekPayload(id, tolerance, purpose);
    if (!body) return jsonFail(404, "unknown place");
    return jsonOk(body);
  } catch (error) {
    logApiError("places/week", error);
    return jsonFail(500, "unavailable");
  }
}
