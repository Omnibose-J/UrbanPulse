/** The week's best day: the served day with the highest first-window score, the earlier date on a tie. Today's windows
 * that have already ended are dropped first. The week screen and the compare screen share this rule. */
import { stillAhead } from "./kst.ts";

export type BestDay = {
  date: string;
  state: string;
  windows: { hours: number[]; score: number }[] | null;
};

export function withTodayTrimmed<T extends BestDay>(days: T[], today: string, hour: number): T[] {
  return days.map((day) => (day.date === today && day.windows ? { ...day, windows: stillAhead(day.windows, true, hour) } : day));
}

export function bestDay<T extends BestDay>(days: T[]): T | undefined {
  const ranked = days.filter((day) => day.windows && day.windows.length > 0 && day.state !== "off");
  ranked.sort((a, b) => b.windows![0].score - a.windows![0].score || a.date.localeCompare(b.date));
  return ranked[0];
}
