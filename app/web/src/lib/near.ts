/** "Near me, good now": pure selection over today's map payload. The browser gives the position; nothing is stored. */
import { stillAhead } from "./kst.ts";

export type NearCandidate = {
  id: string;
  tier: string;
  name: string;
  name_en: string | null;
  category?: string | null;
  lat: number | null;
  lon: number | null;
  state: string;
  windows: { hours: number[] }[] | null;
};

export const NEAR_LIMIT = 5;

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(a));
}

/** A1/A2 places with a position and a pick still ahead today, nearest first, at most five. `window` is the first
 * pick still ahead; `now` says whether the current hour is inside it. */
export function nearbyPicks<T extends NearCandidate>(
  places: T[],
  lat: number,
  lon: number,
  hour: number,
): (T & { km: number; window: { hours: number[] }; now: boolean })[] {
  const out: (T & { km: number; window: { hours: number[] }; now: boolean })[] = [];
  for (const place of places) {
    if (place.tier === "B" || place.state === "off" || place.lat === null || place.lon === null) continue;
    const ahead = stillAhead(place.windows, true, hour);
    if (ahead.length === 0) continue;
    const window = ahead[0];
    out.push({ ...place, km: haversineKm(lat, lon, place.lat, place.lon), window, now: window.hours.includes(hour) });
  }
  return out.sort((a, b) => a.km - b.km).slice(0, NEAR_LIMIT);
}

/** "850 m" under a kilometre, otherwise one decimal "1.2 km". */
export function distanceParts(km: number): { unit: "m" | "km"; value: string } {
  if (km < 1) return { unit: "m", value: String(Math.round(km * 100) * 10) };
  return { unit: "km", value: km.toFixed(1) };
}
