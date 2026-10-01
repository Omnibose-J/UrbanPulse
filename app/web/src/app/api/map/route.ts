import { jsonFail, jsonOk, readDate, readPurpose, readTolerance } from "@/lib/http";
import { mapPayload } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const date = readDate(url.searchParams.get("date"));
  const tolerance = readTolerance(url.searchParams.get("tolerance"));
  const purpose = readPurpose(url.searchParams.get("purpose"));
  const stations = url.searchParams.get("stations") ?? "0";
  if (!date || !tolerance || !purpose || (stations !== "0" && stations !== "1")) {
    return jsonFail(400, "invalid date, tolerance, purpose, or stations");
  }
  try {
    const places = await mapPayload(date, tolerance, purpose, stations === "1");
    return jsonOk({ places });
  } catch {
    return jsonFail(500, "unavailable");
  }
}
