import { jsonFail, jsonOk } from "@/lib/http";
import { searchPlaces } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  try {
    const places = await searchPlaces(q);
    return jsonOk({ places });
  } catch {
    return jsonFail(500, "unavailable");
  }
}
