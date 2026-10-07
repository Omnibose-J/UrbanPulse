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
      { id: "POI001", name: "Alpha", name_en: null, gu: "Gangnam", category: "관광특구", level: 3, window: { hours: [18] } },
      { id: "POI002", name: "Beta", name_en: null, gu: "Mapo", level: 2, window: { hours: [19] } },
      { id: "POI003", name: "Gamma", name_en: null, gu: "Jongno", level: 2, window: { hours: [13] } },
      { id: "POI004", name: "Delta", name_en: null, gu: "Songpa", level: 2, window: null },
      { id: "POI005", name: "Epsilon", name_en: null, gu: "Seocho", level: 2, window: { hours: [11] } },
    ],
    open_quiet: [
      { id: "POI006", name: "Quiet A", name_en: null, gu: "Yongsan", category: "발달상권", level: 1, tier: "A1", window: { hours: [13] }, hours: hours(), strip_mode: "windows_only" },
      { id: "POI007", name: "Quiet B", name_en: null, gu: "Nowon", category: null, level: 0, tier: "A2", window: { hours: [10] }, hours: hours(), strip_mode: "windows_only" },
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
  await expect(rows.nth(0).locator("[data-kind]")).toHaveText("관광특구");
  await expect(rows.nth(1).locator("[data-kind]")).toHaveCount(0);
  await expect(rows.nth(3)).toContainText("오늘은 추천 없음");
  await expect(rows.nth(4)).toContainText("Epsilon");
  await expect(page.locator("[data-quiet]")).toHaveCount(2);
  // A pick that includes the current hour is "지금 가기 좋아요"; the fixture's pick is 13.
  const hourNow = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Seoul", hour: "numeric", hourCycle: "h23" }).format(new Date()));
  await expect(page.locator("[data-quiet]").first()).toContainText(hourNow === 13 ? "지금 가기 좋아요13~14시" : "오늘 추천13~14시");
  await expect(page.locator("[data-quiet]").first().locator("[data-kind]")).toHaveText("발달상권");
  await expect(page.locator("[data-quiet]").nth(1).locator("[data-kind]")).toHaveCount(0);
});

test("D19 home sections run saved places, open and uncrowded, tomorrow morning, busiest", async ({ page }) => {
  await mockVisitor(page);
  await page.addInitScript(() => {
    localStorage.setItem("urbanpulse.favorites", JSON.stringify([{ id: "POI009", name: "Saved", nameEn: null, gu: "Jongno" }]));
  });
  await page.clock.setFixedTime(kstInstant(22));
  await page.goto("/ko");
  await expect(page.locator("[data-busy] [data-row]").first()).toBeVisible();
  const tops = await page.evaluate(() => {
    const top = (selector: string) => document.querySelector(selector)!.getBoundingClientRect().top;
    return { saved: top("[data-favorites]"), quiet: top("[data-quiet-section]"), tomorrow: top("[data-tomorrow-section]"), busy: top("[data-busy]") };
  });
  expect(tops.saved).toBeLessThan(tops.quiet);
  expect(tops.quiet).toBeLessThan(tops.tomorrow);
  expect(tops.tomorrow).toBeLessThan(tops.busy);
  await expect(page.locator("[data-favorites] [data-row]")).toHaveText("Saved");
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

const nearMap = {
  places: [
    { ...place, id: "POI011", name: "Far", lat: 37.6, lon: 127.1, state: "on", windows: [{ hours: [23] }], hours: hours(), strip_mode: "windows_only", category: "공원" },
    { ...place, id: "POI012", name: "Near", lat: 37.5005, lon: 127.0005, state: "on", windows: [{ hours: [23] }], hours: hours(), strip_mode: "windows_only", category: "관광특구" },
    { ...place, id: "POI013", name: "Gone", lat: 37.5001, lon: 127.0001, state: "on", windows: [{ hours: [9] }], hours: hours(), strip_mode: "windows_only", category: null },
    { ...place, id: "STN001", tier: "B", name: "Station", lat: 37.5, lon: 127.0, state: "on", windows: [{ hours: [23] }], hours: hours(), strip_mode: "windows_only" },
  ],
  holidays: [],
};

test("D20 nearby now lists the places with a pick left, nearest first, after the visitor asks", async ({ page, context }) => {
  await mockVisitor(page);
  await page.route("**/api/map**", (route) => json(route, nearMap));
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 37.5, longitude: 127.0 });
  await page.clock.setFixedTime(kstInstant(12));
  await page.goto("/ko");
  const section = page.locator("[data-nearby]");
  await expect(section.locator("h2")).toHaveText("내 주변에서 가기 좋은 곳");
  await expect(section.locator("[data-near-row]")).toHaveCount(0);
  await section.locator("[data-near-find]").click();
  const rows = section.locator("[data-near-row]");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("Near");
  await expect(rows.nth(0).locator("[data-near-distance]")).toHaveText(/^\d+ m$/);
  await expect(rows.nth(0).locator("[data-kind]")).toHaveText("관광특구");
  await expect(rows.nth(0)).toContainText("오늘 추천");
  await expect(rows.nth(0)).toContainText("23~24시");
  await expect(rows.nth(1)).toContainText("Far");
  await expect(rows.nth(1).locator("[data-near-distance]")).toHaveText(/^\d+\.\d km$/);
  await expect(rows.nth(0)).toHaveAttribute("href", `/ko/p/POI012/${kstDate(0)}`);
});

test("D21 nearby now says so when the permission is refused", async ({ page, context }) => {
  await mockVisitor(page);
  await context.clearPermissions();
  await page.goto("/ko");
  await page.locator("[data-near-find]").click();
  await expect(page.locator("[data-near-state='denied']")).toHaveText("위치 권한이 없어 찾을 수 없어요");
  await expect(page.locator("[data-state=error]")).toHaveCount(0);
});

test("D22 share uses the system sheet when there is one, otherwise copies the link and says so", async ({ page }) => {
  await mockVisitor(page);
  await page.addInitScript(() => {
    const shared: unknown[] = [];
    (window as unknown as { __shared: unknown[] }).__shared = shared;
    Object.defineProperty(navigator, "share", { configurable: true, value: (data: unknown) => { shared.push(data); return Promise.resolve(); } });
  });
  await page.goto(`/ko/p/POI001/${day}`);
  await page.getByRole("button", { name: "공유" }).click();
  const shared = await page.evaluate(() => (window as unknown as { __shared: { text: string; url: string }[] }).__shared);
  expect(shared).toHaveLength(1);
  expect(shared[0].url).toMatch(new RegExp(`/ko/p/POI001/${day}$`));
  expect(shared[0].text).toContain("Sample");
  expect(shared[0].text).toContain("18~20시");
  await expect(page.locator("[data-toast]")).toHaveCount(0);

  await page.addInitScript(() => {
    Object.defineProperty(navigator, "share", { configurable: true, value: undefined });
    const copied: string[] = [];
    (window as unknown as { __copied: string[] }).__copied = copied;
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: (text: string) => { copied.push(text); return Promise.resolve(); } } });
  });
  await page.goto("/ko/p/POI001");
  await page.getByRole("button", { name: "공유" }).click();
  await expect(page.locator("[data-toast]")).toHaveText("링크를 복사했어요");
  const copied = await page.evaluate(() => (window as unknown as { __copied: string[] }).__copied);
  expect(copied[0]).toMatch(/\/ko\/p\/POI001$/);
});

test("D23 compare shows two weeks side by side, entered from the week screen through the search", async ({ page }) => {
  await mockVisitor(page);
  const other = { ...week, place: { ...place, id: "POI002", name: "Beta2" } };
  await page.route("**/api/places/POI002/week**", (route) => json(route, other));
  await page.route("**/api/places?**", (route) => json(route, { places: [{ ...place, name: "Alpha", level: 1 }, { ...place, id: "POI002", name: "Beta2", level: 0 }] }));
  await page.goto("/ko/p/POI001");
  await page.locator("[data-compare-link]").click();
  await expect(page).toHaveURL(/\/ko\/search\?compare=POI001$/);
  await expect(page.locator("[data-compare-pick]")).toHaveText("비교할 장소를 고르세요");
  const rows = page.locator("[data-row]");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Beta2");
  await rows.first().click();
  await expect(page).toHaveURL(/\/ko\/compare\?a=POI001&b=POI002$/);
  await expect(page.locator("[data-compare-head='a']")).toContainText("Sample");
  await expect(page.locator("[data-compare-head='b']")).toContainText("Beta2");
  await expect(page.locator("[data-compare-best]").first()).toContainText("13~15시");
  await expect(page.locator("[data-compare-row]")).toHaveCount(8);
  await expect(page.locator("[data-compare-row] [data-mini-strip]")).toHaveCount(16);
  await expect(page.locator("[data-compare-time]").first()).toHaveText("13~15시");
  await expect(page.locator("h1")).toHaveText("비교");
  await page.goto("/ko/compare?a=POI001");
  await expect(page).toHaveURL(/\/ko\/search\?compare=POI001$/);
  await page.goto("/ko/compare?a=nope&b=POI002");
  await expect(page).toHaveURL(/\/ko$/);
});

test("D24 the weekend reminder switch subscribes the saved places and reports a refused permission", async ({ page }) => {
  await mockVisitor(page);
  const posted: unknown[] = [];
  await page.route("**/api/push/subscribe", async (route) => {
    posted.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: "application/json", body: "{\"ok\":true}" });
  });
  // A push stack that always succeeds: the browser pieces are stubbed, the request to our own API is real.
  await page.addInitScript(() => {
    const subscription = { endpoint: "https://push.invalid/stub", toJSON: () => ({ endpoint: "https://push.invalid/stub", keys: { p256dh: "p", auth: "a" } }), unsubscribe: () => Promise.resolve(true) };
    const registration = { pushManager: { getSubscription: () => Promise.resolve(null), subscribe: () => Promise.resolve(subscription) } };
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { register: () => Promise.resolve(registration), getRegistration: () => Promise.resolve(registration) } });
    (window as unknown as { PushManager: unknown }).PushManager = function PushManager() {};
    (window as unknown as { Notification: unknown }).Notification = { permission: "default", requestPermission: () => Promise.resolve((window as unknown as { __perm: string }).__perm ?? "granted") };
    localStorage.setItem("urbanpulse.favorites", JSON.stringify([{ id: "POI001", name: "Sample", nameEn: null, gu: "Gangnam" }, { id: "POI009", name: "Other", nameEn: null, gu: "Jongno" }]));
  });
  await page.goto("/ko/p/POI001");
  const toggle = page.locator("[data-push-toggle]");
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(page.locator("[data-push-note]")).toHaveText("금요일 저녁에 관심 장소의 주말 추천 시간을 알려 드려요");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  expect(posted).toHaveLength(1);
  expect(posted[0]).toMatchObject({ locale: "ko", place_ids: ["POI001", "POI009"], tolerance: "moderate", purpose: "sight" });
  await page.reload();
  await expect(page.locator("[data-push-toggle]")).toHaveAttribute("aria-checked", "true");
  await page.locator("[data-push-toggle]").click();
  await expect(page.locator("[data-push-toggle]")).toHaveAttribute("aria-checked", "false");

  await page.addInitScript(() => {
    (window as unknown as { __perm: string }).__perm = "denied";
  });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-push-toggle]").click();
  await expect(page.locator("[data-push-note]")).toHaveText("알림 권한이 없어 켤 수 없어요");
  await expect(page.locator("[data-push-toggle]")).toHaveAttribute("aria-checked", "false");
});

test("D25 without a saved place the reminder switch is off and says why; without push support it is absent", async ({ page }) => {
  await mockVisitor(page);
  // Chromium has the push stack; with nothing saved the switch is there but cannot be turned on.
  await page.goto("/ko/p/POI001");
  await expect(page.locator("[data-push-toggle]")).toBeDisabled();
  await expect(page.locator("[data-push-note]")).toHaveText("별표한 장소가 있을 때 켤 수 있어요");
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: undefined });
  });
  await page.goto("/ko/p/POI001");
  await expect(page.locator("[data-answer-card]")).toBeVisible();
  await expect(page.locator("[data-push-toggle]")).toHaveCount(0);
});

test("D26 a render error inside a screen shows the app's own error box with a retry, not the framework page", async ({ page }) => {
  // A served cell without a crowd level is a data defect; painting it throws (strip.ts cellFill), and the screen's
  // error boundary catches it.
  const broken = hours().map((cell) => (cell.h === 15 ? { h: cell.h, rating: cell.rating, in_window: false, reason: "fit" } : cell));
  await mockVisitor(page, {
    recommend: {
      recommendation: { state: "on", off_reason: null, windows: [{ hours: [13] }], no_window: false, hours: broken, strip_mode: "windows_only" },
      place,
      holiday: null,
      combos: week.combos,
      alt_dates: [],
      alt_places: [],
    },
  });
  // The boundary catches the error, so it is not an uncaught page error; error.tsx logs it to the console.
  const thrown: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") thrown.push(message.text());
  });
  await page.goto(`/ko/p/POI001/${day}`);
  const box = page.locator("[data-state=error]");
  await expect(box).toContainText("불러오지 못했어요.");
  await expect(box.getByRole("button", { name: "다시 시도" })).toBeVisible();
  await expect(page.getByText(/Application error|Unhandled Runtime Error/)).toHaveCount(0);
  expect(thrown.join(" ")).toContain("crowd");
});

test("D27 the about page opens with a summary of the settings and keeps the table behind a disclosure", async ({ page }) => {
  await page.route("**/api/flags**", (route) =>
    json(route, {
      rows: [
        { tier: "A1", foreign_heavy: false, purpose: "sight", tolerance: "moderate", state: "on", count: 68 },
        { tier: "A1", foreign_heavy: false, purpose: "shop", tolerance: "moderate", state: "reference", count: 68 },
        { tier: "A1", foreign_heavy: false, purpose: "sight", tolerance: "calm", state: "off", count: 71 },
        { tier: "A2", foreign_heavy: false, purpose: "none", tolerance: "calm", state: "on", count: 22 },
      ],
    }),
  );
  await page.goto("/ko/about");
  await expect(page.locator("[data-flags-summary]")).toHaveText("오늘 켜진 조합 2개, 참고용 1개, 준비 중·꺼짐 1개");
  const rows = page.locator("[data-flags-details] tbody tr");
  await expect(rows).toHaveCount(4);
  await expect(rows.first()).toBeHidden();
  await page.locator("[data-flags-details] summary").click();
  await expect(rows.first()).toBeVisible();
});

test("D28 at desktop width the phone column is centred and nothing scrolls sideways", async ({ page }) => {
  await mockVisitor(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  for (const path of ["/ko", "/ko/p/POI001", `/ko/compare?a=POI001&b=POI002`]) {
    await page.goto(path);
    await expect(page.locator(".phone-shell").first()).toBeVisible();
    const box = await page.locator(".phone-shell").first().boundingBox();
    expect(box!.width).toBeLessThanOrEqual(480);
    expect(Math.abs(box!.x + box!.width / 2 - 640)).toBeLessThanOrEqual(8);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1280);
  }
  await page.goto("/ko/map");
  await expect(page.locator("[data-map-list]")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1280);
});
