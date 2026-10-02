import { expect, test } from "@playwright/test";

import { db, kstDate } from "./helpers";

// Live local stack, no mocks.
const today = kstDate();
const cond = "tolerance=moderate&purpose=sight";

test("every route answers with its documented keys", async ({ request }) => {
  const cases: [string, string[]][] = [
    [`/api/home?${cond}`, ["as_of", "stale", "busy_top", "open_quiet"]],
    ["/api/places?q=", ["places"]],
    [`/api/places/POI001/week?${cond}`, ["place", "now", "days", "combos"]],
    [`/api/places/POI001/recommend?date=${today}&${cond}`, ["recommendation", "place", "holiday", "combos", "alt_places", "alt_dates"]],
    [`/api/places/POI001/day?date=${today}`, ["hours"]],
    [`/api/map?date=${today}&${cond}&stations=0`, ["places", "holidays"]],
    ["/api/flags", ["rows"]],
    ["/api/health", ["db", "places"]],
  ];
  for (const [url, keys] of cases) {
    const response = await request.get(url);
    expect(response.status(), url).toBe(200);
    const body = await response.json();
    for (const key of keys) expect(body, `${url} lacks ${key}`).toHaveProperty(key);
  }
});

test("bad input gets 400, 404 or 410, never 500, and an error is never cacheable", async ({ request }) => {
  const q = encodeURIComponent;
  const cases: [string, number][] = [
    ["/api/home", 400],
    ["/api/home?tolerance=x&purpose=sight", 400],
    [`/api/places/NOPE/week?${cond}`, 404],
    ["/api/places/POI001/week?tolerance=moderate", 400],
    [`/api/places/${q("POI001' or '1'='1")}/week?${cond}`, 404],
    [`/api/places/POI001/recommend?date=${kstDate(-1)}&${cond}`, 410],
    [`/api/places/POI001/recommend?date=${kstDate(8)}&${cond}`, 400],
    [`/api/places/POI001/recommend?date=2026-13-45&${cond}`, 400],
    [`/api/places/NOPE/recommend?date=${today}&${cond}`, 404],
    ["/api/places/POI001/day?date=bad", 400],
    [`/api/places/NOPE/day?date=${today}`, 404],
    [`/api/map?date=${today}&${cond}&stations=2`, 400],
    [`/api/map?date=${kstDate(-1)}&${cond}`, 400],
    [`/api/map?date=${kstDate(8)}&${cond}`, 400],
    [`/api/places?q=${"x".repeat(51)}`, 400],
  ];
  for (const [url, status] of cases) {
    const response = await request.get(url);
    expect(response.status(), url).toBe(status);
    expect(response.headers()["cache-control"], url).toBe("no-store");
  }
});

test("a search text is matched literally, whatever characters it has", async ({ request }) => {
  for (const text of [")", "(1호선)", "서울역(1호선)", "\\", "%", "_", "a,b", "name.eq.x,tier.eq.B", "*", "'; drop table places;--", "x".repeat(50)]) {
    const response = await request.get(`/api/places?q=${encodeURIComponent(text)}`);
    expect(response.status(), text).toBe(200);
    // Whatever comes back really contains the text: no character acts as a wildcard or a filter.
    for (const row of (await response.json()).places as { name: string; name_en: string | null; gu: string | null }[]) {
      const lowered = text.toLowerCase();
      expect([row.name, row.name_en, row.gu].some((value) => value?.toLowerCase().includes(lowered)), `${text} -> ${row.name}`).toBe(true);
    }
  }
  const closing = (await (await request.get(`/api/places?q=${encodeURIComponent(")")}`)).json()).places;
  expect(closing.length).toBeGreaterThan(0);
  const wildcard = (await (await request.get(`/api/places?q=${encodeURIComponent("%")}`)).json()).places;
  expect(wildcard).toEqual([]);
  const named = (await (await request.get(`/api/places?q=${encodeURIComponent("강남")}`)).json()).places;
  expect(named.length).toBeGreaterThan(0);
});

test("the week route returns exactly the stored rows for 25 places", async ({ request }) => {
  const { data: places, error } = await db.from("places").select("id, tier").eq("serve_state", "on").order("id");
  expect(error).toBeNull();
  const sample = places!.filter((_, index) => index % Math.ceil(places!.length / 25) === 0).slice(0, 25);
  expect(sample.length).toBe(25);
  for (const place of sample) {
    const purpose = place.tier === "A1" ? "sight" : "none";
    const body = await (await request.get(`/api/places/${place.id}/week?${cond}`)).json();
    const { data: rows } = await db
      .from("recommendations")
      .select("date, state, off_reason, windows, no_window, hours, strip_mode")
      .eq("place_id", place.id)
      .eq("tolerance", "moderate")
      .eq("purpose", purpose)
      .gte("date", today)
      .lte("date", kstDate(7))
      .order("date");
    expect(rows!.length, place.id).toBe(8);
    const served = body.days.map((row: Record<string, unknown>) => Object.fromEntries(Object.entries(row).filter(([key]) => key !== "holiday")));
    expect(served, place.id).toEqual(rows);
  }
});

test("the flags route counts every row of today, past the 1,000-row cap", async ({ request }) => {
  const body = await (await request.get("/api/flags")).json();
  const served = body.rows.reduce((sum: number, row: { count: number }) => sum + row.count, 0);
  const { count, error } = await db.from("recommendations").select("*", { count: "exact", head: true }).eq("date", today);
  expect(error).toBeNull();
  expect(count).toBeGreaterThan(1000);
  expect(served).toBe(count);
});

test("home lists obey their rules on live data", async ({ request }) => {
  const body = await (await request.get(`/api/home?${cond}`)).json();
  const levels = body.busy_top.map((row: { level: number }) => row.level);
  expect(levels.every((level: number) => level >= 2)).toBe(true);
  expect(levels).toEqual([...levels].sort((a: number, b: number) => b - a));
  expect(body.busy_top.length).toBeLessThanOrEqual(5);
  for (const row of body.open_quiet) {
    expect(row.level).toBeLessThanOrEqual(1);
    if (row.tier === "A1") expect(row.activity).toBeGreaterThanOrEqual(0.5);
    else expect(row.activity).toBeNull();
  }
});
