import { kindRank } from "./kind.ts";

export type QuietRow = { tier: string; activity: number | null; category?: string | null };

export function pickBusy<T extends { level: number; popMax: number }>(rows: T[]): T[] {
  return [...rows]
    .filter((row) => row.level >= 2)
    .sort((a, b) => b.level - a.level || b.popMax - a.popMax)
    .slice(0, 5);
}

/** A1 by measured activity, then A2; within each, places worth a visit before commuter stations (design spec 5.7). */
export function pickQuiet<T extends QuietRow>(rows: T[]): T[] {
  const first = rows.filter((row) => row.tier === "A1").sort((a, b) => kindRank(a.category) - kindRank(b.category) || (b.activity ?? 0) - (a.activity ?? 0));
  const second = rows.filter((row) => row.tier !== "A1").sort((a, b) => kindRank(a.category) - kindRank(b.category));
  return [...first, ...second].slice(0, 5);
}
