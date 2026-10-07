"use client";

export type Purpose = "sight" | "food" | "shop";
export type Tolerance = "calm" | "moderate" | "busy_ok";

const COND = "urbanpulse.conditions";
const FAV = "urbanpulse.favorites";
const STATIONS = "urbanpulse.stations";

export type Favorite = { id: string; name: string; nameEn: string | null; gu: string | null };

const DEFAULTS = { purpose: "sight" as Purpose, tolerance: "moderate" as Tolerance };
const PURPOSES = new Set<Purpose>(["sight", "food", "shop"]);
const TOLERANCES = new Set<Tolerance>(["calm", "moderate", "busy_ok"]);

/** Saved choices are a convenience: with storage blocked or full the choice still applies on this page. */
function persist(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage unavailable: nothing to keep
  }
}

export function normalizeConditions(parsed: { purpose?: string; tolerance?: string } | null) {
  const purpose = parsed && PURPOSES.has(parsed.purpose as Purpose) ? (parsed.purpose as Purpose) : DEFAULTS.purpose;
  const tolerance = parsed && TOLERANCES.has(parsed.tolerance as Tolerance) ? (parsed.tolerance as Tolerance) : DEFAULTS.tolerance;
  return { purpose, tolerance };
}

export function readConditions(): { purpose: Purpose; tolerance: Tolerance } {
  try {
    const raw = localStorage.getItem(COND);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as { purpose?: string; tolerance?: string };
    const next = normalizeConditions(parsed);
    if (next.purpose !== parsed.purpose || next.tolerance !== parsed.tolerance) writeConditions(next);
    return next;
  } catch {
    return DEFAULTS;
  }
}

export function writeConditions(value: { purpose: Purpose; tolerance: Tolerance }) {
  persist(COND, JSON.stringify(value));
}

export function readFavorites(): Favorite[] {
  try {
    const raw = localStorage.getItem(FAV);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as Favorite[]) : [];
  } catch {
    return [];
  }
}

export function toggleFavorite(place: Favorite): Favorite[] {
  const current = readFavorites();
  const next = current.some((item) => item.id === place.id)
    ? current.filter((item) => item.id !== place.id)
    : [...current, place];
  persist(FAV, JSON.stringify(next));
  return next;
}

export function readStations(): boolean {
  try {
    return localStorage.getItem(STATIONS) === "1";
  } catch {
    return false;
  }
}

export function writeStations(on: boolean) {
  persist(STATIONS, on ? "1" : "0");
}
