import { notFound } from "next/navigation";

import { supabaseServer } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

function allowed(given: string): boolean {
  const expected = process.env.ADMIN_TOKEN ?? "";
  if (!expected || given.length !== expected.length) return false;
  let mismatch = 0;
  for (let index = 0; index < expected.length; index += 1) {
    mismatch |= given.charCodeAt(index) ^ expected.charCodeAt(index);
  }
  return mismatch === 0;
}

export default async function Page({ searchParams }: { searchParams: Promise<{ token?: string | string[] }> }) {
  const given = (await searchParams).token;
  // A repeated parameter arrives as an array; only a single string can be the token.
  if (typeof given !== "string" || !allowed(given)) notFound();
  const db = supabaseServer();
  const [models, forecast, reco, strip, places, jobs] = await Promise.all([
    db.from("model_registry").select("name, version, horizons, active"),
    db.from("eval_daily").select("date, horizon_d, segment, wape_model, wape_baseline, n").order("date", { ascending: false }).limit(200),
    db.from("reco_eval_daily").select("purpose, tolerance, n_hours, n_lively, n_crowd_ok, chance_hours, chance_lively"),
    db.from("strip_eval_daily").select("purpose, tolerance, n_ok, n_ok_lively, n_ok_crowd_ok, n_avoid, n_avoid_unfit"),
    db.from("places").select("tier, serve_state"),
    db.from("job_runs").select("job, status, started_at, finished_at, detail").order("id", { ascending: false }).limit(50),
  ]);
  // A failed read must not render as an empty table.
  const failed = Object.entries({ models, forecast, reco, strip, places, jobs }).filter(([, result]) => result.error).map(([name]) => name);
  if (failed.length) throw new Error(`admin read failed: ${failed.join(", ")}`);
  return (
    <main>
      <h1>Model registry</h1>
      <Table rows={models.data ?? []} />
      <h1>Forecast WAPE</h1>
      <Table rows={forecast.data ?? []} />
      <h1>Recommendation quality</h1>
      <Table rows={reco.data ?? []} />
      <h1>Strip quality</h1>
      <Table rows={strip.data ?? []} />
      <h1>Places</h1>
      <Table rows={places.data ?? []} />
      <h1>Jobs</h1>
      <Table rows={(jobs.data ?? []).map((row) => ({ ...row, detail: JSON.stringify(row.detail).slice(0, 200) }))} />
    </main>
  );
}

function Table({ rows }: { rows: Record<string, unknown>[] }) {
  const keys = rows[0] ? Object.keys(rows[0]) : [];
  return (
    <table>
      <thead>
        <tr>
          {keys.map((key) => (
            <th key={key}>{key}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {keys.map((key) => (
              <td key={key}>{String(row[key])}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
