export function requireForeignHeavy(value: unknown): boolean {
  if (typeof value !== "boolean") throw new Error("foreign_heavy");
  return value;
}

export type LiveStamp = { ts: string; pop_min: number; pop_max: number };

export type MeasuredRow = { level: number; hour: number; target_ts: string };

/** A "now" line needs a real observation. A forecast timestamp is not one. */
export function measuredNow(row: MeasuredRow | undefined, live: LiveStamp | null) {
  if (!row || !live) return null;
  return {
    level: row.level,
    source: "live" as const,
    stale: false,
    ts: live.ts,
    pop_min: live.pop_min,
    pop_max: live.pop_max,
    hour: row.hour,
  };
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
