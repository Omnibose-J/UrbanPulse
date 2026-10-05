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

/** One sentence plan for the day strip and the map card. `windows_only` never states the two-step verdict. */
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
}):
  | { kind: "notPick"; hour: string }
  | { kind: "verdict"; hour: string; verdict: "window" | "ok" | "avoid"; whys: string[] } {
  const hour = hourLabel(input.hour, input.locale);
  if (input.mode !== "two_step" && !input.inWindow) {
    return { kind: "notPick", hour };
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
