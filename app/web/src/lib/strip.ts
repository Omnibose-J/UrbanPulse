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

/** One sentence plan for the day strip and the map card. `windows_only` never states the two-step verdict. */
export function cellSentence(input: {
  mode: string | null;
  inWindow: boolean;
  rating: number;
  reason: string;
  hour: number;
  locale: "ko" | "en";
}):
  | { kind: "notPick"; hour: string }
  | { kind: "verdict"; hour: string; verdict: "window" | "ok" | "avoid"; why: string } {
  const hourNumber = String(input.hour);
  if (input.mode !== "two_step" && !input.inWindow) {
    const face = input.hour % 12 === 0 ? 12 : input.hour % 12;
    const hourLabel = input.locale === "en" ? `${face} ${input.hour < 12 ? "AM" : "PM"}` : hourNumber;
    return { kind: "notPick", hour: hourLabel };
  }
  const verdict = input.inWindow ? "window" : input.mode === "two_step" && input.rating === 1 ? "ok" : "avoid";
  return { kind: "verdict", hour: hourNumber, verdict, why: WHY_KEY[input.reason] ?? "ok" };
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
