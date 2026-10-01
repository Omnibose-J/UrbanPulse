export const place = {
  id: "POI001",
  tier: "A1",
  name: "Sample",
  name_en: null,
  gu: "Gangnam",
  serve_state: "on",
  foreign_heavy: false,
};

export function hours(mode: "fit" | "window" | "closed" = "fit") {
  return Array.from({ length: 15 }, (_, index) => {
    const h = index + 9;
    const inWindow = mode !== "closed" && h === 13;
    return {
      h,
      rating: mode === "closed" ? 0 : 1,
      in_window: inWindow,
      reason: mode === "closed" ? "closed" : "fit",
      crowd: 1,
      act: "lively",
    };
  });
}

export const week = {
  place,
  now: { level: 1, source: "live", stale: false, ts: "2026-10-01T09:30:00+09:00", pop_min: 10, pop_max: 20 },
  days: Array.from({ length: 8 }, (_, index) => ({
    date: `2026-10-0${index + 1}`,
    state: "on",
    off_reason: null,
    windows: [{ hours: [13, 14], score: 1 - index * 0.1, crowd: 1, act: "sight", act_level: "lively" }],
    no_window: false,
    hours: hours(),
    strip_mode: "windows_only",
    holiday: null,
  })),
  combos: [
    { purpose: "sight", tolerance: "moderate", state: "on" },
    { purpose: "sight", tolerance: "calm", state: "off" },
    { purpose: "sight", tolerance: "busy_ok", state: "on" },
    { purpose: "food", tolerance: "moderate", state: "on" },
    { purpose: "food", tolerance: "calm", state: "off" },
    { purpose: "food", tolerance: "busy_ok", state: "on" },
    { purpose: "shop", tolerance: "moderate", state: "on" },
    { purpose: "shop", tolerance: "calm", state: "off" },
    { purpose: "shop", tolerance: "busy_ok", state: "on" },
  ],
};
