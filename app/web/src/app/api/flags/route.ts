import { jsonFail, jsonOk } from "@/lib/http";
import { flagCounts } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const rows = await flagCounts();
    return jsonOk({ rows });
  } catch {
    return jsonFail(500, "unavailable");
  }
}
