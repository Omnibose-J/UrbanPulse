import { jsonFail, jsonOk, logApiError } from "@/lib/http";
import { searchPlaces } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  if (q.length > 50) return jsonFail(400, "q is longer than 50 characters");
  try {
    const places = await searchPlaces(q);
    return jsonOk({ places });
  } catch (error) {
    logApiError("places", error);
    return jsonFail(500, "unavailable");
  }
}
