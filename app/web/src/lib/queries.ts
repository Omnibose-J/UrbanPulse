import "server-only";

import { supabaseServer } from "@/lib/supabase-server";
import { addDays, dayBounds, kstHour, kstNow } from "@/lib/kst";
import { pickBusy, pickQuiet } from "@/lib/home-rules";
import { measuredNow, namedAltPlaces } from "@/lib/shape";

type Place = {
  id: string;
  tier: string;
  name: string;
  name_en: string | null;
  gu: string | null;
  serve_state: string;
  foreign_heavy?: boolean;
  lat?: number | null;
  lon?: number | null;
};

async function must<T>(query: PromiseLike<{ data: T | null; error: { message: string } | null }>): Promise<T> {
  const { data, error } = await query;
  if (error || data === null) throw new Error("unavailable");
  return data;
}

export async function findPlace(id: string): Promise<Place | null> {
  const { data, error } = await supabaseServer()
    .from("places")
    .select("id, tier, name, name_en, gu, serve_state, foreign_heavy, lat, lon")
    .eq("id", id)
    .maybeSingle();
  if (error) throw new Error("unavailable");
  return data;
}

export function purposeFor(tier: string, purpose: string): string {
  return tier === "A1" ? purpose : "none";
}

export async function searchPlaces(q: string) {
  const sb = supabaseServer();
  if (!q) {
    return must(
      sb
        .from("places")
        .select("id, tier, name, name_en, gu, serve_state")
        .in("tier", ["A1", "A2"])
        .eq("serve_state", "on")
        .order("name")
        .limit(200),
    );
  }
  const safe = q.replace(/[%_,]/g, " ");
  return must(
    sb
      .from("places")
      .select("id, tier, name, name_en, gu, serve_state")
      .in("serve_state", ["on", "preparing", "experimental"])
      .or(`name.ilike.%${safe}%,name_en.ilike.%${safe}%,gu.ilike.%${safe}%`)
      .order("name")
      .limit(50),
  );
}

export async function weekPayload(id: string, tolerance: string, purpose: string) {
  const place = await findPlace(id);
  if (!place) return null;
  const used = purposeFor(place.tier, purpose);
  const { date, hour } = kstNow();
  const dates = Array.from({ length: 8 }, (_, index) => addDays(date, index));
  const sb = supabaseServer();
  const days = await must(
    sb
      .from("recommendations")
      .select("date, state, off_reason, windows, no_window, hours, strip_mode")
      .eq("place_id", id)
      .eq("tolerance", tolerance)
      .eq("purpose", used)
      .gte("date", dates[0])
      .lte("date", dates[7])
      .order("date"),
  );
  const holidays = await must(sb.from("holidays").select("date, name, name_en, kind").in("date", dates));
  const holidayByDate = new Map(holidays.map((row: { date: string }) => [row.date, row]));
  const combos = await must(
    sb.from("recommendations").select("purpose, tolerance, state").eq("place_id", id).eq("date", date),
  );
  let now: unknown = null;
  if (place.tier !== "B") {
    const measured = await latestMeasured(date, hour, id);
    const row = measured[0];
    if (row) {
      const { data: liveRows, error: liveError } = await sb
        .from("live_obs")
        .select("ts, pop_min, pop_max")
        .eq("place_id", id)
        .order("ts", { ascending: false })
        .limit(1);
      if (liveError) throw new Error("unavailable");
      const live = liveRows?.[0] ?? null;
      now = measuredNow(row, live);
    }
  }
  return {
    place: {
      id: place.id,
      tier: place.tier,
      name: place.name,
      name_en: place.name_en,
      gu: place.gu,
      serve_state: place.serve_state,
      foreign_heavy: place.foreign_heavy,
    },
    now,
    days: days.map((row: { date: string }) => ({ ...row, holiday: holidayByDate.get(row.date) ?? null })),
    combos,
  };
}

export async function recommendPayload(id: string, date: string, tolerance: string, purpose: string, today: string) {
  const place = await findPlace(id);
  if (!place) return null;
  if (date < today) return "gone" as const;
  const used = purposeFor(place.tier, purpose);
  const sb = supabaseServer();
  const { data, error } = await sb
    .from("recommendations")
    .select("date, state, off_reason, windows, no_window, hours, strip_mode, alt_dates, alt_places, tolerance, purpose")
    .eq("place_id", id)
    .eq("date", date)
    .eq("tolerance", tolerance)
    .eq("purpose", used)
    .maybeSingle();
  if (error) throw new Error("unavailable");
  const holidayQuery = await sb.from("holidays").select("date, name, name_en, kind").eq("date", date).maybeSingle();
  if (holidayQuery.error) throw new Error("unavailable");
  const combos = await must(
    sb.from("recommendations").select("purpose, tolerance, state").eq("place_id", id).eq("date", date),
  );
  const alts = Array.isArray(data?.alt_places) ? data.alt_places : [];
  const ids = alts.map((item: { place_id: string }) => item.place_id);
  let names = new Map<string, { name: string; name_en: string | null }>();
  if (ids.length) {
    const joined = await must(sb.from("places").select("id, name, name_en").in("id", ids));
    names = new Map(joined.map((row: { id: string; name: string; name_en: string | null }) => [row.id, row]));
  }
  return {
    recommendation: data,
    place: {
      id: place.id,
      tier: place.tier,
      name: place.name,
      name_en: place.name_en,
      gu: place.gu,
      serve_state: place.serve_state,
      foreign_heavy: place.foreign_heavy,
    },
    holiday: holidayQuery.data,
    combos,
    alt_places: namedAltPlaces(alts, names),
    alt_dates: data?.alt_dates ?? [],
  };
}

export async function dayHours(id: string, date: string) {
  const place = await findPlace(id);
  if (!place) return null;
  const rows = await must(
    supabaseServer()
      .from("forecast_hourly")
      .select("target_ts, source, level, a_all, a_food, a_shop, stale, ready")
      .eq("place_id", id)
      .gte("target_ts", `${date}T09:00:00+09:00`)
      .lt("target_ts", `${addDays(date, 1)}T00:00:00+09:00`)
      .order("target_ts"),
  );
  return { hours: rows };
}

export async function mapPayload(date: string, tolerance: string, purpose: string, stations: boolean) {
  const rows = await must(
    supabaseServer()
      .from("recommendations")
      .select("place_id, purpose, state, windows, hours, strip_mode, places!inner(id, tier, name, name_en, lat, lon)")
      .eq("date", date)
      .eq("tolerance", tolerance)
      .in("purpose", [purpose, "none"])
      .limit(500),
  );
  const list = rows as unknown as {
    purpose: string;
    state: string;
    windows: unknown;
    hours: unknown;
    strip_mode: string | null;
    places: Place | Place[];
  }[];
  return list
    .map((row) => {
      const place = Array.isArray(row.places) ? row.places[0] : row.places;
      return { ...row, place };
    })
    .filter((row) => {
      if (!stations && row.place.tier === "B") return false;
      return row.purpose === purposeFor(row.place.tier, purpose);
    })
    .map((row) => ({
      id: row.place.id,
      tier: row.place.tier,
      name: row.place.name,
      name_en: row.place.name_en,
      lat: row.place.lat,
      lon: row.place.lon,
      state: row.state,
      windows: row.windows,
      hours: row.hours,
      strip_mode: row.strip_mode,
    }));
}

export async function upcomingHolidays() {
  const { date } = kstNow();
  const end = addDays(date, 7);
  return must(
    supabaseServer().from("holidays").select("date, name, name_en").gte("date", date).lte("date", end),
  );
}

export async function flagCounts() {
  const { date } = kstNow();
  const rows = await must(
    supabaseServer()
      .from("recommendations")
      .select("purpose, tolerance, state, places!inner(tier, foreign_heavy)")
      .eq("date", date)
      .limit(2000),
  );
  const counts = new Map<string, number>();
  for (const row of rows as { purpose: string; tolerance: string; state: string; places: { tier: string; foreign_heavy: boolean } | { tier: string; foreign_heavy: boolean }[] }[]) {
    const place = Array.isArray(row.places) ? row.places[0] : row.places;
    const key = [place.tier, place.foreign_heavy, row.purpose, row.tolerance, row.state].join("|");
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].map(([key, count]) => {
    const [tier, foreignHeavy, purpose, tolerance, state] = key.split("|");
    return { tier, foreign_heavy: foreignHeavy === "true", purpose, tolerance, state, count };
  });
}

export async function homePayload(tolerance: string, purpose: string) {
  const { date, hour } = kstNow();
  const sb = supabaseServer();
  const measured = await latestMeasured(date, hour);
  const asOfQuery = await sb.from("live_obs").select("ts").order("ts", { ascending: false }).limit(1);
  if (asOfQuery.error) throw new Error("unavailable");
  const asOf = asOfQuery.data?.[0]?.ts ?? null;
  const stale = asOf ? Date.now() - new Date(asOf).getTime() > 90 * 60 * 1000 : true;
  const liveNow = measured.filter(
    (row) => (row.place.tier === "A1" || row.place.tier === "A2") && row.place.serve_state === "on",
  );
  const ids = liveNow.map((row) => row.place.id);
  const pops = new Map<string, { pop_min: number; pop_max: number }>();
  if (ids.length) {
    const [dayStart] = dayBounds(date);
    const live = await must(
      sb.from("live_obs").select("place_id, ts, pop_min, pop_max").in("place_id", ids).gte("ts", dayStart).order("ts", { ascending: false }).limit(2000),
    );
    for (const row of live as { place_id: string; pop_min: number; pop_max: number }[]) {
      if (!pops.has(row.place_id)) pops.set(row.place_id, { pop_min: row.pop_min, pop_max: row.pop_max });
    }
  }
  const busy = pickBusy(
    liveNow.map((row) => ({
      id: row.place.id,
      tier: row.place.tier,
      name: row.place.name,
      name_en: row.place.name_en,
      gu: row.place.gu,
      level: row.level,
      popMax: pops.get(row.place.id)?.pop_max ?? 0,
      pop_min: pops.get(row.place.id)?.pop_min ?? null,
      pop_max: pops.get(row.place.id)?.pop_max ?? null,
    })),
  );
  const quiet = await quietPlaces(date, liveNow);
  const windowIds = [...busy.map((row) => row.id), ...quiet.map((row) => row.id)];
  const windows = await todayWindows(date, tolerance, purpose, windowIds);
  return {
    as_of: asOf,
    stale,
    busy_top: busy.map((row) => ({ ...row, ...windows.get(row.id) })),
    open_quiet: quiet.map((row) => ({ ...row, ...windows.get(row.id) })),
  };
}

async function quietPlaces(
  date: string,
  measured: { place: Place; level: number; hour: number }[],
) {
  const sb = supabaseServer();
  const onNow = measured.filter((row) => row.level <= 1);
  const latest = new Map<string, number>();
  if (onNow.length) {
    const [dayStart, dayEnd] = dayBounds(date);
    const rows = await must(
      sb
        .from("forecast_hourly")
        .select("place_id, target_ts, a_all")
        .eq("a_actual", true)
        .in("place_id", onNow.map((row) => row.place.id))
        .gte("target_ts", dayStart)
        .lt("target_ts", dayEnd)
        .order("target_ts", { ascending: false })
        .limit(4000),
    );
    for (const row of rows as { place_id: string; target_ts: string; a_all: number | null }[]) {
      if (latest.has(row.place_id) || row.a_all === null) continue;
      const owner = onNow.find((item) => item.place.id === row.place_id);
      if (!owner) continue;
      if (kstHour(row.target_ts) < owner.hour - 2) continue;
      latest.set(row.place_id, row.a_all);
    }
  }
  const a2ids = onNow.filter((row) => row.place.tier === "A2").map((row) => row.place.id);
  const openA2 = new Set<string>();
  if (a2ids.length) {
    const rows = await must(
      sb
        .from("recommendations")
        .select("place_id, hours")
        .eq("date", date)
        .eq("tolerance", "moderate")
        .eq("purpose", "none")
        .in("place_id", a2ids),
    );
    for (const row of rows as { place_id: string; hours: { h: number; reason: string }[] | null }[]) {
      const owner = onNow.find((item) => item.place.id === row.place_id);
      const cell = row.hours?.find((item) => item.h === owner?.hour);
      if (cell && cell.reason !== "outside_hours") openA2.add(row.place_id);
    }
  }
  const candidates = onNow
    .filter((row) => {
      if (row.place.tier === "A1") {
        const activity = latest.get(row.place.id);
        return activity !== undefined && activity >= 0.5;
      }
      return openA2.has(row.place.id);
    })
    .map((row) => ({
      id: row.place.id,
      tier: row.place.tier,
      name: row.place.name,
      name_en: row.place.name_en,
      gu: row.place.gu,
      level: row.level,
      activity: row.place.tier === "A1" ? latest.get(row.place.id) ?? null : null,
    }));
  return pickQuiet(candidates);
}

async function latestMeasured(date: string, clockHour: number, placeId?: string) {
  const [dayStart, dayEnd] = dayBounds(date);
  let query = supabaseServer()
    .from("forecast_hourly")
    .select("place_id, target_ts, level, places!inner(id, tier, name, name_en, gu, serve_state)")
    .eq("source", "live")
    .gte("target_ts", dayStart)
    .lt("target_ts", dayEnd)
    .order("target_ts", { ascending: false })
    .limit(4000);
  if (placeId) query = query.eq("place_id", placeId);
  const rows = await must(query);
  const seen = new Map<string, { place: Place; level: number; hour: number; target_ts: string }>();
  for (const row of rows as {
    place_id: string;
    target_ts: string;
    level: number | null;
    places: Place | Place[];
  }[]) {
    if (seen.has(row.place_id) || row.level === null) continue;
    const hour = kstHour(row.target_ts);
    if (hour < clockHour - 1) continue;
    const place = Array.isArray(row.places) ? row.places[0] : row.places;
    seen.set(row.place_id, { place, level: row.level, hour, target_ts: row.target_ts });
  }
  return [...seen.values()];
}

async function todayWindows(date: string, tolerance: string, purpose: string, ids: string[]) {
  const out = new Map<string, { window: unknown; hours: unknown; strip_mode: string | null }>();
  if (!ids.length) return out;
  const rows = await must(
    supabaseServer()
      .from("recommendations")
      .select("place_id, purpose, windows, hours, strip_mode, places!inner(tier)")
      .eq("date", date)
      .eq("tolerance", tolerance)
      .in("place_id", ids)
      .limit(1000),
  );
  for (const row of rows as { place_id: string; purpose: string; windows: { hours: number[] }[] | null; hours: unknown; strip_mode: string | null; places: { tier: string } | { tier: string }[] }[]) {
    const place = Array.isArray(row.places) ? row.places[0] : row.places;
    const wanted = purposeFor(place.tier, purpose);
    if (row.purpose !== wanted) continue;
    if (out.has(row.place_id)) continue;
    out.set(row.place_id, {
      window: row.windows?.[0] ?? null,
      hours: row.hours,
      strip_mode: row.strip_mode,
    });
  }
  return out;
}
