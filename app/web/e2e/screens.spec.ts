import { expect, test, type Page, type Route } from "@playwright/test";

import { hours, place, week } from "./fixtures/place";
import { kstDate } from "./helpers";

// The day screen only opens dates the service can answer for, so the mocked day is always two days ahead.
const day = kstDate(2);

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockVisitor(page: Page, overrides?: { week?: unknown; home?: unknown; recommend?: unknown }) {
  const weekBody = overrides?.week ?? week;
  const home = overrides?.home ?? {
    as_of: "2026-10-01T10:00:00+09:00",
    stale: false,
    busy_top: [
      { id: "POI001", name: "Alpha", name_en: null, gu: "Gangnam", level: 3, window: { hours: [18] } },
      { id: "POI002", name: "Beta", name_en: null, gu: "Mapo", level: 2, window: { hours: [19] } },
      { id: "POI003", name: "Gamma", name_en: null, gu: "Jongno", level: 2, window: { hours: [13] } },
      { id: "POI004", name: "Delta", name_en: null, gu: "Songpa", level: 2, window: null },
      { id: "POI005", name: "Epsilon", name_en: null, gu: "Seocho", level: 2, window: { hours: [11] } },
    ],
    open_quiet: [
      { id: "POI006", name: "Quiet A", name_en: null, gu: "Yongsan", level: 1, tier: "A1", window: { hours: [13] }, hours: hours(), strip_mode: "windows_only" },
      { id: "POI007", name: "Quiet B", name_en: null, gu: "Nowon", level: 0, tier: "A2", window: { hours: [10] }, hours: hours(), strip_mode: "windows_only" },
    ],
    tomorrow_morning: [
      { id: "POI008", name: "Morning A", name_en: null, gu: "Jongno", date: kstDate(1), window: { hours: [10], score: 0.8 }, hours: hours(), strip_mode: "windows_only" },
    ],
  };
  const recommend = overrides?.recommend ?? {
    recommendation: {
      state: "on",
      off_reason: null,
      windows: [{ hours: [18] }, { hours: [19] }, { hours: [11] }],
      no_window: false,
      hours: hours(),
      strip_mode: "windows_only",
    },
    place,
    holiday: null,
    combos: week.combos,
    alt_dates: [{ date: kstDate(3), hours: [13], score: 0.9 }],
    alt_places: [{ place_id: "POI045", hours: [18], name: "Nearby", name_en: null, crowd: 1 }],
  };
  await page.route("**/api/home**", (route) => json(route, home));
  await page.route("**/api/places?**", (route) => json(route, { places: [{ ...place, name: "Alpha" }] }));
  await page.route("**/api/places/*/week**", (route) => json(route, weekBody));
  await page.route("**/api/places/*/recommend**", (route) => json(route, recommend));
  await page.route("**/api/places/*/day**", (route) => json(route, { hours: [] }));
  await page.route("**/api/map**", (route) =>
    json(route, {
      places: [
        {
          ...place,
          lat: 37.5,
          lon: 127,
          state: "on",
          windows: [{ hours: [13] }],
          hours: hours(),
          strip_mode: "windows_only",
        },
      ],
      holidays: [],
    }),
  );
  await page.route("**/api/flags**", (route) => json(route, { rows: [] }));
}

test("D1 answer card is inside the first viewport", async ({ page }) => {
  await mockVisitor(page);
  for (const locale of ["ko", "en"]) {
    await page.goto(`/${locale}/p/POI001`);
    const weekCard = page.locator("[data-answer-card]");
    await expect(weekCard).toBeVisible();
    const weekBox = await weekCard.boundingBox();
    expect(weekBox).toBeTruthy();
    expect(weekBox!.y).toBeGreaterThanOrEqual(0);
    expect(weekBox!.y + weekBox!.height).toBeLessThanOrEqual(844);
    await page.goto(`/${locale}/p/POI001/${day}`);
    const dayCard = page.locator("[data-answer-card]");
    await expect(dayCard).toBeVisible();
    const dayBox = await dayCard.boundingBox();
    expect(dayBox!.y).toBeGreaterThanOrEqual(0);
    expect(dayBox!.y + dayBox!.height).toBeLessThanOrEqual(844);
  }
});

test("D3 screenshots of each state", async ({ page }) => {
  await page.goto("/ko");
  await mockVisitor(page, {
    week: { ...week, place: { ...place, serve_state: "preparing" }, days: week.days.map((row) => ({ ...row, state: "off", off_reason: "preparing", windows: null, hours: null })) },
  });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-state=preparing]").screenshot({ path: "e2e/screenshots/preparing.png" });

  await mockVisitor(page, { week: { ...week, now: { ...week.now, stale: true } } });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/stale.png" });

  await page.unroute("**/api/places/*/week**");
  await page.route("**/api/places/*/week**", (route) => json(route, { error: "unavailable" }, 500));
  await page.goto("/ko/p/POI001");
  await page.locator("[data-state=error]").screenshot({ path: "e2e/screenshots/error.png" });

  await page.unroute("**/api/places/*/week**");
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/places/*/week**", async (route) => {
    await held;
    await json(route, week);
  });
  await page.goto("/ko/p/POI001");
  await expect(page.locator("[data-state=skeleton]")).toBeVisible();
  await page.locator("[data-state=skeleton]").screenshot({ path: "e2e/screenshots/skeleton.png" });
  release();
  await expect(page.locator("[data-answer-card]")).toBeVisible();

  await mockVisitor(page, {
    recommend: {
      recommendation: { state: "off", off_reason: "myeongjeol", windows: null, no_window: null, hours: null, strip_mode: null },
      place,
      holiday: { name: "추석", kind: "chuseok" },
      combos: week.combos,
      alt_dates: [],
      alt_places: [],
    },
  });
  await page.goto(`/ko/p/POI001/${day}`);
  await page.locator("[data-state=myeongjeol]").screenshot({ path: "e2e/screenshots/myeongjeol.png" });

  await mockVisitor(page, {
    recommend: {
      recommendation: { state: "on", off_reason: null, windows: [], no_window: true, hours: hours("closed"), strip_mode: "windows_only" },
      place,
      holiday: null,
      combos: week.combos,
      alt_dates: [{ date: kstDate(3), hours: [13], score: 0.4 }],
      alt_places: [],
    },
  });
  await page.goto(`/ko/p/POI001/${day}`);
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/no-window.png" });

  await mockVisitor(page, {
    recommend: {
      recommendation: { state: "reference", off_reason: null, windows: [{ hours: [13] }], no_window: false, hours: hours(), strip_mode: "windows_only" },
      place,
      holiday: null,
      combos: week.combos,
      alt_dates: [],
      alt_places: [],
    },
  });
  await page.goto(`/ko/p/POI001/${day}`);
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/reference.png" });

  await mockVisitor(page, {
    week: { ...week, place: { ...place, tier: "B", serve_state: "experimental" }, now: null },
  });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/tier-b.png" });

  await mockVisitor(page, {
    week: { ...week, days: week.days.map((row) => ({ ...row, windows: [], no_window: true, state: "on" })) },
  });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/week-no-pick.png" });
});

test("D4 changing purpose moves off a tolerance that is not ready", async ({ page }) => {
  await mockVisitor(page);
  await page.addInitScript(() => {
    localStorage.setItem("urbanpulse.conditions", JSON.stringify({ purpose: "sight", tolerance: "calm" }));
  });
  await page.goto("/ko/p/POI001");
  await page.getByRole("button", { name: "바꾸기" }).click();
  await page.getByRole("radio", { name: "맛집" }).click();
  await expect(page.getByText("바꿨어요")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "닫기" }).click();
  await expect(page.getByRole("button", { name: /한적하게/ })).toBeVisible();
});

test("D5 share link back opens the week of the same place", async ({ page }) => {
  await mockVisitor(page);
  await page.goto(`/ko/p/POI001/${day}?purpose=food&tol=moderate`);
  await page.getByRole("link", { name: "이번 주" }).click();
  await expect(page).toHaveURL(/\/ko\/p\/POI001$/);
});

test("D6 pressable heights and the 16px text line", async ({ page }) => {
  await mockVisitor(page);
  await page.goto("/ko");
  const title = page.getByRole("heading", { level: 1 });
  const box = await title.boundingBox();
  expect(Math.round(box!.x)).toBe(16);
  const presses = page.locator("[data-press]");
  const count = await presses.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const height = (await presses.nth(index).boundingBox())!.height;
    expect(height).toBe(48);
  }
  const bar = page.locator("header").first();
  expect((await bar.boundingBox())!.height).toBe(56);
});

test("D9 english pages keep Hangul inside lang=ko", async ({ page }) => {
  await mockVisitor(page);
  await page.goto("/en");
  const leaked = await page.evaluate(() => {
    const found: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = walker.currentNode.textContent ?? "";
      if (!/[가-힣]/.test(text)) continue;
      const parent = walker.currentNode.parentElement;
      if (parent?.closest('[lang="ko"]')) continue;
      found.push(text.trim());
    }
    return found;
  });
  expect(leaked).toEqual([]);
});

test("D10 slider does not refetch and back restores the map hour", async ({ page }) => {
  await mockVisitor(page);
  let mapCalls = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/map")) mapCalls += 1;
  });
  await page.goto(`/ko/map?date=${day}&hour=13`);
  await expect(page.locator("[data-pin]")).toHaveAttribute("data-tone", "go");
  const before = mapCalls;
  await page.locator("[data-hour]").fill("18");
  expect(mapCalls).toBe(before);
  await page.locator("[data-map-card]").click();
  await page.getByRole("link", { name: "지도" }).click();
  await expect(page).toHaveURL(new RegExp(`date=${day}`));
  await expect(page).toHaveURL(/hour=18/);
});

test("D11 windows_only never paints the two-step verdict; the other cells are shaded by forecast crowd", async ({ page }) => {
  const shaded = hours().map((cell) => {
    if (cell.h === 9) return { ...cell, reason: "outside_hours", crowd: 0 };
    if (cell.h >= 14 && cell.h <= 16) return { ...cell, crowd: 3 };
    if (cell.h === 11) return { ...cell, crowd: 0 };
    return cell;
  });
  await mockVisitor(page, {
    recommend: {
      recommendation: { state: "on", off_reason: null, windows: [{ hours: [13] }], no_window: false, hours: shaded, strip_mode: "windows_only" },
      place,
      holiday: null,
      combos: week.combos,
      alt_dates: [],
      alt_places: [],
    },
  });
  await page.goto(`/ko/p/POI001/${day}`);
  await expect(page.locator("[data-cell]").first()).toBeVisible();
  const cells = await page.locator("[data-cell]").evaluateAll((nodes) =>
    nodes.map((node) => ({ tone: node.getAttribute("data-tone"), crowd: node.getAttribute("data-crowd"), bg: getComputedStyle(node).backgroundColor })),
  );
  expect(cells.map((cell) => cell.tone)).toContain("go");
  expect(cells.map((cell) => cell.tone)).not.toContain("ok");
  expect(cells[13 - 9]).toMatchObject({ tone: "go", crowd: null });
  expect(cells[9 - 9]).toMatchObject({ tone: "bad", crowd: null });
  expect(cells[11 - 9].crowd).toBe("0");
  expect(cells[12 - 9].crowd).toBe("1");
  expect(cells[14 - 9].crowd).toBe("3");
  // Four distinct paints among the non-window cells: the hollow one and three crowd shades.
  expect(new Set(cells.filter((cell) => cell.tone === "bad").map((cell) => cell.bg)).size).toBe(4);
  const legend = page.locator("[data-legend-row] [data-legend-item]");
  await expect(legend).toHaveText(["추천", "예상 혼잡한산붐빔", "운영 시간 아님"]);
});

test("D17 today's strips dim the hours gone by and ring the current hour", async ({ page }) => {
  const days = week.days.map((row, index) => ({ ...row, date: kstDate(index) }));
  await mockVisitor(page, { week: { ...week, days } });
  await page.clock.setFixedTime(kstInstant(14));
  await page.goto("/ko/p/POI001");
  const today = page.locator("[data-row]", { hasText: "오늘" });
  await expect(today.locator("[data-mini-strip] [data-past]")).toHaveCount(5);
  await expect(today.locator("[data-mini-strip] [data-now]")).toHaveCount(1);
  await expect(page.locator("[data-row]").nth(1).locator("[data-mini-strip] [data-past]")).toHaveCount(0);
  await expect(page.locator("[data-week-axis] span")).toHaveText(["9", "12", "15", "18", "21"]);
  await page.goto(`/ko/p/POI001/${kstDate(0)}`);
  await expect(page.locator("[data-cell][data-past]")).toHaveCount(5);
  await expect(page.locator("[data-cell][data-now]")).toHaveAttribute("data-hour", "14");
  await expect(page.locator("[data-axis-now]")).toHaveText("지금");
  await page.goto(`/ko/p/POI001/${kstDate(2)}`);
  await expect(page.locator("[data-cell]").first()).toBeVisible();
  await expect(page.locator("[data-cell][data-past]")).toHaveCount(0);
  await expect(page.locator("[data-axis-now]")).toHaveCount(0);
});

test("D18 a holiday row and the best row keep their date", async ({ page }) => {
  const days = week.days.map((row, index) => (index === 2 ? { ...row, holiday: { name: "개천절", name_en: "National Foundation Day", kind: "holiday" } } : row));
  await mockVisitor(page, { week: { ...week, days } });
  await page.goto("/ko/p/POI001");
  const rows = page.locator("[data-row]");
  await expect(rows.nth(2).locator("[data-week-third]")).toHaveText("개천절");
  await expect(rows.nth(2)).toContainText("10/3");
  // The first day scores highest in the fixture, so it is the best row: its date stays and "추천" is the third line.
  await expect(rows.nth(0).locator("[data-week-third]")).toHaveText("추천");
  await expect(rows.nth(0)).toContainText("10/1");
  await expect(rows.nth(1).locator("[data-week-third]")).toHaveCount(0);
  const heights = await rows.evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height));
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
  await page.goto("/en/p/POI001");
  await expect(page.locator("[data-row]").nth(2).locator("[data-week-third]")).toHaveText("National Foundation Day");
});

test("D12 home draws the rows in the order served, each with its level and pick", async ({ page }) => {
  // Which rows are served is the API's rule: unit-tested in home-rules and shape tests, live-checked in api.spec.
  await mockVisitor(page);
  await page.goto("/ko");
  const rows = page.locator("[data-busy] [data-row]");
  await expect(rows).toHaveCount(5);
  await expect(rows.nth(0)).toContainText("Alpha");
  await expect(rows.nth(0)).toContainText("붐빔");
  await expect(rows.nth(0)).toContainText("추천 18~19시");
  await expect(rows.nth(3)).toContainText("오늘은 추천 없음");
  await expect(rows.nth(4)).toContainText("Epsilon");
  await expect(page.locator("[data-quiet]")).toHaveCount(2);
  // A pick that includes the current hour is "지금 가기 좋아요"; the fixture's pick is 13.
  const hourNow = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Seoul", hour: "numeric", hourCycle: "h23" }).format(new Date()));
  await expect(page.locator("[data-quiet]").first()).toContainText(hourNow === 13 ? "지금 가기 좋아요13~14시" : "오늘 추천13~14시");
});

test("live smoke: home answers, and a listed place opens its week", async ({ page }) => {
  const statuses: { url: string; status: number }[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/")) statuses.push({ url: response.url(), status: response.status() });
  });
  await page.goto("/ko");
  // Fresh data shows rows or the empty sentence; late data says it is late. Anything else is a failure.
  const shown = page.locator("[data-busy] [data-row], [data-busy-empty], [data-state=stale]").first();
  await expect(shown).toBeVisible();
  const firstRow = page.locator("[data-busy] [data-row], [data-quiet]").first();
  if (await firstRow.count()) {
    await firstRow.click();
    await expect(page).toHaveURL(/\/ko\/p\//);
    await expect(page.locator("[data-answer-card], [data-state=comboOff], [data-state=preparing]").first()).toBeVisible();
  }
  expect(statuses.length).toBeGreaterThan(0);
  expect(statuses.filter((item) => item.status !== 200)).toEqual([]);
});

// Night: 22:00 KST on the mocked day; day: 12:00 KST. `page.clock` moves the browser's clock, not the server's.
function kstInstant(hour: number): number {
  const date = kstDate(0);
  return Date.parse(`${date}T${String(hour).padStart(2, "0")}:00:00+09:00`);
}

test("D13 the home shows tomorrow's morning picks at night and not by day", async ({ page }) => {
  await mockVisitor(page);
  await page.clock.setFixedTime(kstInstant(22));
  await page.goto("/ko");
  const section = page.locator("[data-tomorrow-section]");
  await expect(section).toBeVisible();
  await expect(section.locator("h2")).toHaveText("내일 아침 가기 좋은 곳");
  const card = page.locator("[data-tomorrow]");
  await expect(card).toHaveCount(1);
  await expect(card).toContainText("Morning A");
  await expect(card).toContainText("내일 추천10~11시");
  await expect(card.locator("[data-place-status]")).toHaveCount(0);
  await expect(card.locator("[data-mini-strip] > *")).toHaveCount(15);
  await expect(card).toHaveAttribute("href", `/ko/p/POI008/${kstDate(1)}`);
  await page.clock.setFixedTime(kstInstant(12));
  await page.goto("/ko");
  await expect(page.locator("[data-busy] [data-row]").first()).toBeVisible();
  await expect(page.locator("[data-tomorrow-section]")).toHaveCount(0);
});

test("D14 an empty morning list says so, and a quiet card without a pick says 'no pick today'", async ({ page }) => {
  await mockVisitor(page, {
    home: {
      as_of: "2026-10-01T10:00:00+09:00",
      stale: false,
      busy_top: [],
      open_quiet: [{ id: "POI006", name: "Quiet A", name_en: null, gu: "Yongsan", level: 1, tier: "A1", window: null, hours: null, strip_mode: null }],
      tomorrow_morning: [],
    },
  });
  await page.clock.setFixedTime(kstInstant(23));
  await page.goto("/ko");
  await expect(page.locator("[data-tomorrow-empty]")).toHaveText("내일 아침에 추천할 곳이 없어요");
  await expect(page.locator("[data-quiet]")).toContainText("오늘은 추천 없음");
  await expect(page.locator("[data-quiet]")).not.toContainText("오늘 추천추천");
});

test("D15 the answer card and the week rows name the busiest hours and their level", async ({ page }) => {
  // Peak crowd 3 at 14 to 16 and again at 20 to 21; the window hour 13 is also crowd 3 but never counts. The longest
  // run at the peak wins: 14~17시.
  const busyHours = hours().map((cell) => {
    if (cell.h === 11) return { ...cell, in_window: false, reason: "fit", crowd: 2 };
    if (cell.h === 13) return { ...cell, in_window: true, reason: "fit", crowd: 3 };
    if (cell.h >= 14 && cell.h <= 16) return { ...cell, in_window: false, reason: "fit", crowd: 3 };
    if (cell.h >= 20 && cell.h <= 21) return { ...cell, in_window: false, reason: "too_busy", crowd: 3 };
    return cell;
  });
  const days = week.days.map((row) => ({ ...row, hours: busyHours }));
  await mockVisitor(page, { week: { ...week, days }, recommend: undefined });
  await page.route("**/api/places/*/recommend**", (route) =>
    json(route, {
      recommendation: { state: "on", off_reason: null, windows: [{ hours: [13] }], no_window: false, hours: busyHours, strip_mode: "windows_only" },
      place,
      holiday: null,
      combos: week.combos,
      alt_dates: [],
      alt_places: [],
    }),
  );
  await page.goto("/ko/p/POI001");
  await expect(page.locator("[data-answer-card] [data-avoid]")).toHaveText("가장 붐빌 때 14~17시 · 붐빔");
  await expect(page.locator("[data-week-avoid]").first()).toHaveText("14~17시");
  await expect(page.locator("[data-week-avoid]").first()).toHaveAttribute("aria-label", "가장 붐빌 때 14~17시 · 붐빔");
  await expect(page.locator("[data-week-avoid] [data-status-dot]").first()).toHaveCount(1);
  await expect(page.locator("[data-week-avoid]")).toHaveCount(8);
  await expect(page.locator("[data-legend-busiest]")).toHaveText("가장 붐빌 때");
  await page.goto(`/ko/p/POI001/${day}`);
  await expect(page.locator("[data-answer-card] [data-avoid]")).toHaveText("가장 붐빌 때 14~17시 · 붐빔");
  await page.goto("/en/p/POI001");
  await expect(page.locator("[data-answer-card] [data-avoid]")).toHaveText("Busiest 2 to 5 PM · Busy");
  await expect(page.locator("[data-week-avoid]").first()).toHaveText("2 to 5 PM");
  await expect(page.locator("[data-week-avoid]").first()).toHaveAttribute("aria-label", "Busiest 2 to 5 PM · Busy");
});

test("D16 no busiest line when no hour of the day is too busy", async ({ page }) => {
  await mockVisitor(page);
  await page.goto("/ko/p/POI001");
  await expect(page.locator("[data-answer-card]")).toBeVisible();
  await expect(page.locator("[data-avoid]")).toHaveCount(0);
  await expect(page.locator("[data-week-avoid]")).toHaveCount(0);
  await expect(page.locator("[data-legend-busiest]")).toHaveCount(0);
});
