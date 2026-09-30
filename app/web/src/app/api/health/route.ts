import { NextResponse } from "next/server";

import { supabaseServer } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

// Proves the web → database wiring. Never echoes the error (it may contain the URL or key).
export async function GET() {
  try {
    const { count, error } = await supabaseServer()
      .from("places")
      .select("*", { count: "exact", head: true });
    if (error) throw error;
    return NextResponse.json({ db: "ok", places: count ?? 0 }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ db: "error" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
