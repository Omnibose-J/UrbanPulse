import { jsonFail, jsonOk, logApiError } from "@/lib/http";
import { flagCounts } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const rows = await flagCounts();
    return jsonOk({ rows });
  } catch (error) {
    logApiError("flags", error);
    return jsonFail(500, "unavailable");
  }
}
