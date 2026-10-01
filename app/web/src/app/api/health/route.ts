import { NextResponse } from "next/server";

import { logApiError } from "@/lib/http";
import { supabaseServer } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

// Proves the web → database wiring. Never echoes the error (it may contain the URL or key).
export async function GET() {
  try {
    const { count, error } = await supabaseServer()
      .from("places")
      .select("*", { count: "exact", head: true });
    if (error) throw error;
    if (count === null) {
      return NextResponse.json({ error: "unavailable" }, { status: 500, headers: { "Cache-Control": "no-store" } });
    }
    return NextResponse.json({ db: "ok", places: count }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    logApiError("health", error);
    return NextResponse.json({ error: "unavailable" }, { status: 500, headers: { "Cache-Control": "no-store" } });
  }
}
