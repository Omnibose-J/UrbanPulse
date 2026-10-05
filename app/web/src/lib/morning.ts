/** Home, at night: the places whose first recommendation window of tomorrow starts in the morning. Pure selection
 * over stored recommendation rows; the engine computed every window. */
export type MorningCandidate = {
  state: string;
  serve_state: string;
  tier: string;
  windows: { hours: number[]; score: number }[] | null;
};

export const MORNING_FIRST_HOUR = 9;
export const MORNING_LAST_START = 11;
export const MORNING_LIMIT = 5;

export function morningPicks<T extends MorningCandidate>(rows: T[]): T[] {
  return rows
    .filter((row) => row.state === "on" && row.serve_state === "on" && (row.tier === "A1" || row.tier === "A2"))
    .filter((row) => {
      const first = row.windows?.[0];
      if (!first || first.hours.length === 0) return false;
      const start = first.hours[0];
      return start >= MORNING_FIRST_HOUR && start <= MORNING_LAST_START;
    })
    .sort((a, b) => b.windows![0].score - a.windows![0].score)
    .slice(0, MORNING_LIMIT);
}

/** The home shows tomorrow's morning picks only in the evening and the small hours, when today's lists run dry. */
export function isNight(hour: number): boolean {
  return hour >= 20 || hour < 6;
}
