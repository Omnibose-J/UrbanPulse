import { jsonFail, jsonOk, readPurpose, readTolerance } from "@/lib/http";
import { homePayload } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const tolerance = readTolerance(url.searchParams.get("tolerance"));
  const purpose = readPurpose(url.searchParams.get("purpose"));
  if (!tolerance || !purpose) return jsonFail(400, "invalid tolerance or purpose");
  try {
    return jsonOk(await homePayload(tolerance, purpose));
  } catch {
    return jsonFail(500, "unavailable");
  }
}
