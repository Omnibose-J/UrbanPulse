export function requireForeignHeavy(value: unknown): boolean {
  if (typeof value !== "boolean") throw new Error("foreign_heavy");
  return value;
}

export type LiveStamp = { ts: string; pop_min: number; pop_max: number; level: number };

export const STALE_MS = 90 * 60 * 1000;

/** A "now" line needs a real observation. Older than 90 minutes it is stale and states no level. */
export function nowFromLive(live: LiveStamp | null, nowMs: number) {
  if (!live) return null;
  const stale = nowMs - new Date(live.ts).getTime() > STALE_MS;
  return {
    level: stale ? null : live.level,
    source: "live" as const,
    stale,
    ts: live.ts,
    pop_min: live.pop_min,
    pop_max: live.pop_max,
  };
}

export type QuietCandidate = { id: string; tier: string; level: number; hour: number };

/** Open-and-quiet rule: level 0 or 1, and A1 measured activity >= 0.5 within the last two clock hours, or A2 inside its hours. */
export function quietSelection<T extends QuietCandidate>(
  rows: T[],
  clockHour: number,
  measuredActivity: Map<string, { hour: number; value: number }>,
  openA2: Set<string>,
): (T & { activity: number | null })[] {
  const out: (T & { activity: number | null })[] = [];
  for (const row of rows) {
    if (row.level > 1) continue;
    if (row.tier === "A1") {
      const measured = measuredActivity.get(row.id);
      if (!measured || measured.hour < clockHour - 2 || measured.value < 0.5) continue;
      out.push({ ...row, activity: measured.value });
    } else if (row.tier === "A2" && openA2.has(row.id)) {
      out.push({ ...row, activity: null });
    }
  }
  return out;
}

/** PostgREST caps a response at 1,000 rows. Read every page, in a stable order the caller sets. */
export async function selectAll<T>(page: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>, size = 1000): Promise<T[]> {
  const out: T[] = [];
  for (let from = 0; ; from += size) {
    const { data, error } = await page(from, from + size - 1);
    if (error || data === null) throw new Error(error ? error.message : "unavailable");
    out.push(...data);
    if (data.length < size) return out;
  }
}

/** A LIKE pattern that matches the text literally anywhere. */
export function likePattern(text: string): string {
  return `%${text.replace(/[\\%_]/g, (ch) => `\\${ch}`)}%`;
}

export type AltPlace = { place_id: string; hours: number[]; crowd: number };

export function namedAltPlaces(
  alts: AltPlace[],
  names: Map<string, { name: string; name_en: string | null }>,
) {
  return alts.flatMap((item) => {
    const joined = names.get(item.place_id);
    if (!joined?.name) return [];
    return [{ ...item, name: joined.name, name_en: joined.name_en }];
  });
}
