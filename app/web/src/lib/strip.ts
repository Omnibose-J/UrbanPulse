export type HourCell = {
  h: number;
  rating: number;
  in_window: boolean;
  reason: string;
  crowd?: number;
  act?: string | null;
};

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
