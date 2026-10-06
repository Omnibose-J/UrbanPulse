export type ReasonWindow = {
  crowd?: number;
  act?: string | null;
  act_level?: string | null;
};

/** Message ids for the answer-card sentence. The caller translates them. */
export function reasonMessageIds(tier: string, window: ReasonWindow | null | undefined): string[] {
  if (!window || window.crowd === undefined || window.crowd === null) return [];
  if (tier === "B") {
    const band = window.crowd <= 0 ? 0 : window.crowd === 1 ? 1 : 2;
    return [`reason.b${band}`];
  }
  if (window.act && window.act_level) {
    const level = window.act_level === "lively" ? "Lively" : "Quiet";
    return [`reason.crowd${window.crowd}`, `reason.${window.act}${level}`];
  }
  return [`reason.crowdOnly${window.crowd}`];
}

export type HourCell = {
  h: number;
  rating: number;
  in_window: boolean;
  reason: string;
  crowd?: number;
  act?: string | null;
};

const WHY_KEY: Record<string, string> = {
  too_busy: "tooBusy",
  closed: "closed",
  outside_hours: "outsideHours",
};

function hourLabel(hour: number, locale: "ko" | "en"): string {
  if (locale === "ko") return String(hour);
  const face = hour % 12 === 0 ? 12 : hour % 12;
  return `${face} ${hour < 12 ? "AM" : "PM"}`;
}

function knownWhy(reason: string): string {
  const key = WHY_KEY[reason];
  if (!key) throw new Error(`unknown reason: ${reason}`);
  return `reason.${key}`;
}

/** The next recommended hour after `hour` on this day (`from`), or, when every window is already behind it, the day's
 * first window (`day`). Null when the day has no window. Both are stated as a run of adjacent window hours. */
export function nextPick(hours: HourCell[] | null | undefined, hour: number): { kind: "from" | "day"; start: number; end: number } | null {
  if (!hours || hours.length === 0) return null;
  const sorted = [...hours].filter((cell) => cell.in_window).sort((a, b) => a.h - b.h);
  if (sorted.length === 0) return null;
  const first = sorted.find((cell) => cell.h > hour) ?? sorted[0];
  let end = first.h + 1;
  while (sorted.some((cell) => cell.h === end)) end += 1;
  return { kind: first.h > hour ? "from" : "day", start: first.h, end };
}

/** One sentence plan for the day strip and the map card. `windows_only` never states the two-step verdict: a cell
 * outside the windows says the forecast crowd level (or that the place is outside its hours) and the next pick. */
export function cellSentence(input: {
  mode: string | null;
  inWindow: boolean;
  rating: number;
  reason: string;
  hour: number;
  locale: "ko" | "en";
  tier?: string;
  purpose?: string;
  crowd?: number;
  act?: string | null;
  hours?: HourCell[] | null;
}):
  | { kind: "notPick"; hour: string; whys: string[]; next: { kind: "from" | "day"; start: number; end: number } | null }
  | { kind: "verdict"; hour: string; verdict: "window" | "ok" | "avoid"; whys: string[] } {
  const hour = hourLabel(input.hour, input.locale);
  if (input.mode !== "two_step" && !input.inWindow) {
    const whys =
      input.reason === "outside_hours"
        ? ["reason.outsideHours"]
        : input.tier === "B"
          ? reasonMessageIds("B", { crowd: input.crowd })
          : reasonMessageIds("", { crowd: input.crowd });
    if (whys.length === 0) throw new Error(`cell ${input.hour} without a crowd level`);
    return { kind: "notPick", hour, whys, next: nextPick(input.hours, input.hour) };
  }
  const verdict = input.inWindow ? "window" : input.mode === "two_step" && input.rating === 1 ? "ok" : "avoid";
  if (input.inWindow || input.reason === "fit") {
    const whys = reasonMessageIds(input.tier ?? "", {
      crowd: input.crowd,
      act: input.purpose && input.purpose !== "none" ? input.purpose : null,
      act_level: input.act,
    });
    if (whys.length === 0) throw new Error(`unknown reason: ${input.reason}`);
    return { kind: "verdict", hour, verdict, whys };
  }
  return { kind: "verdict", hour, verdict, whys: [knownWhy(input.reason)] };
}

const BUSY_FROM = 2;

/** The busiest hours of the day: among the open hours outside the recommended windows (`fit` or `too_busy`, never
 * `closed` / `outside_hours`), the day's highest forecast crowd level when it is at least "a bit busy", and the longest
 * run of hours at that level (the earliest on a tie). A recommended hour never counts, so the line never contradicts
 * the pick. This states the forecast level, which the product promises; it is not the two-step verdict. */
export function busiestRange(hours: HourCell[] | null | undefined): { start: number; end: number; crowd: number } | null {
  if (!hours || hours.length === 0) return null;
  const open = hours.filter((cell) => !cell.in_window && (cell.reason === "fit" || cell.reason === "too_busy") && typeof cell.crowd === "number");
  const peak = Math.max(-1, ...open.map((cell) => cell.crowd as number));
  if (peak < BUSY_FROM) return null;
  const sorted = open.filter((cell) => cell.crowd === peak).sort((a, b) => a.h - b.h);
  let best: { start: number; end: number } | null = null;
  let run: { start: number; end: number } | null = null;
  for (const cell of sorted) {
    if (run && cell.h === run.end) run.end = cell.h + 1;
    else run = { start: cell.h, end: cell.h + 1 };
    if (!best || run.end - run.start > best.end - best.start) best = run;
  }
  return best ? { ...best, crowd: peak } : null;
}

export function cellTone(cell: { in_window?: boolean; rating?: number }, mode: string | null): "go" | "ok" | "bad" {
  if (cell.in_window) return "go";
  if (mode === "two_step" && cell.rating === 1) return "ok";
  return "bad";
}

export function toneColor(tone: "go" | "ok" | "bad", pin = false): string {
  if (tone === "go") return "var(--go)";
  if (tone === "ok") return "var(--ok)";
  return pin ? "var(--bad-pin)" : "var(--bad)";
}

export type CellFill = { tone: "go" | "ok" | "bad"; crowd: number | null; hollow: boolean; color: string };

/** How a strip cell is painted. A window cell is `--go`. In `two_step` the rest is the verified verdict colour.
 * In `windows_only` the rest states the forecast crowd level (a product promise, unlike the verdict): one of four
 * neutral shades `--crowd-0..3`; an hour outside the place's opening hours is hollow (background, hairline). */
export function cellFill(cell: { in_window?: boolean; rating?: number; reason?: string; crowd?: number }, mode: string | null): CellFill {
  const tone = cellTone(cell, mode);
  if (tone !== "bad" || mode === "two_step") return { tone, crowd: null, hollow: false, color: toneColor(tone) };
  if (cell.reason === "outside_hours") return { tone, crowd: null, hollow: true, color: "var(--bg)" };
  if (typeof cell.crowd !== "number") throw new Error("cell without a crowd level");
  const crowd = Math.min(Math.max(Math.round(cell.crowd), 0), 3);
  return { tone, crowd, hollow: false, color: `var(--crowd-${crowd})` };
}
