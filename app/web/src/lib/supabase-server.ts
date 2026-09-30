import "server-only";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// The browser never receives this client or its key (AGENTS.md hard rule 4).
// `server-only` makes any import from client code fail the build.
let cached: SupabaseClient | null = null;

export function supabaseServer(): SupabaseClient {
  if (cached) return cached;
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error("missing env var: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY");
  }
  cached = createClient(url, key, { auth: { persistSession: false } });
  return cached;
}
