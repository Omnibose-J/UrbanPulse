export type QuietRow = { tier: string; activity: number | null };

export function pickBusy<T extends { level: number; popMax: number }>(rows: T[]): T[] {
  return [...rows]
    .filter((row) => row.level >= 2)
    .sort((a, b) => b.level - a.level || b.popMax - a.popMax)
    .slice(0, 5);
}

export function pickQuiet<T extends QuietRow>(rows: T[]): T[] {
  const first = rows.filter((row) => row.tier === "A1").sort((a, b) => (b.activity ?? 0) - (a.activity ?? 0));
  const second = rows.filter((row) => row.tier !== "A1");
  return [...first, ...second].slice(0, 5);
}
