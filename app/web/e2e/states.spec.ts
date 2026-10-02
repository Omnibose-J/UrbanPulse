import { expect, test, type Page } from "@playwright/test";

import { hours, place } from "./fixtures/place";
import { db, kstDate, strayHangul, watch } from "./helpers";

test.use({ locale: "ko-KR" });

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
const retryBox = (page: Page) => page.locator("[data-state=error]");

// ---- live: addresses that do not exist are said to not exist

test("an unknown place is 'not found', not 'could not load'", async ({ page }) => {
  await page.goto("/ko/p/NOPE");
  await expect(page.locator("[data-state=missing]")).toContainText("이 장소는 찾을 수 없어요.");
  await expect(retryBox(page)).toHaveCount(0);
  await page.getByRole("link", { name: "홈으로" }).click();
  await expect(page).toHaveURL(/\/ko$/);
  await page.goto(`/ko/p/NOPE/${kstDate(1)}`);
  await expect(page.locator("[data-state=missing]")).toBeVisible();
  await expect(retryBox(page)).toHaveCount(0);
});

test("a date that cannot be served opens the week with a notice", async ({ page }) => {
  await page.goto("/ko/p/POI001/notadate");
  await expect(page).toHaveURL(/\/ko\/p\/POI001\?notice=range$/);
  await expect(page.locator("[data-notice]")).toHaveText("오늘부터 7일 뒤까지만 볼 수 있어요.");
  await page.goto(`/ko/p/POI001/${kstDate(8)}`);
  await expect(page).toHaveURL(/\/ko\/p\/POI001\?notice=range$/);
  await page.goto(`/ko/p/POI001/${kstDate(-1)}`);
  await expect(page).toHaveURL(/\/ko\/p\/POI001\?notice=past$/);
  await expect(page.locator("[data-notice]")).toHaveText("지난 날짜라 이번 주를 보여 드려요");
  await page.goto(`/ko/p/POI001/${kstDate(7)}`);
  await expect(page).toHaveURL(new RegExp(`/ko/p/POI001/${kstDate(7)}$`));
  await expect(retryBox(page)).toHaveCount(0);
});

test("an unknown address gets the site's own page, in the visitor's language", async ({ page }) => {
  const ko = await page.goto("/ko/nothing-here");
  expect(ko?.status()).toBe(404);
  await expect(page.locator("[data-state=missing]")).toContainText("이 페이지는 찾을 수 없어요.");
  const en = await page.goto("/en/nothing-here");
  expect(en?.status()).toBe(404);
  await expect(page.locator("[data-state=missing]")).toContainText("We cannot find this page.");
  await page.getByRole("link", { name: "Home" }).click();
  await expect(page).toHaveURL(/\/en$/);
});

test("a place still collecting data shows only that", async ({ page }) => {
  const { data } = await db.from("places").select("id").eq("serve_state", "preparing").order("id").limit(1);
  const preparing = data?.[0];
  expect(preparing, "no preparing place to check").toBeTruthy();
  await page.goto(`/ko/p/${preparing!.id}`);
  await expect(page.locator("[data-state=preparing]")).toBeVisible();
  await expect(page.locator("[data-week-time]")).toHaveCount(0);
  await expect(page.locator("[data-field-label]")).toHaveCount(0);
});

test("a condition that is off for the place says so and leaves a way out", async ({ page }) => {
  const seen = watch(page);
  await page.addInitScript(() => {
    if (!localStorage.getItem("urbanpulse.conditions")) localStorage.setItem("urbanpulse.conditions", JSON.stringify({ purpose: "sight", tolerance: "calm" }));
  });
  await page.goto("/ko/p/POI001");
  await expect(page.locator("[data-state=comboOff]")).toContainText("이 조건은 아직 준비하고 있어요.");
  await expect(page.getByText("이번 주에는 추천할 시간이 없어요")).toHaveCount(0);
  await expect(page.locator("[data-week-time]")).toHaveCount(8);
  await page.getByRole("button", { name: /바꾸기/ }).click();
  await page.getByRole("radio", { name: "적당히" }).click();
  await page.getByRole("button", { name: "적용하기" }).click();
  await expect(page.locator("[data-state=comboOff]")).toHaveCount(0);
  await expect(page.locator("[data-field-label]").first()).toHaveText("구경·산책 · 적당히");
  expect(seen.failed).toEqual([]);
});

test("a park's reason is a whole sentence", async ({ page, request }) => {
  const parks = (await (await request.get("/api/places?q=" + encodeURIComponent("공원"))).json()).places as { id: string; tier: string; serve_state: string }[];
  let found = false;
  for (const park of parks.filter((row) => row.tier === "A2" && row.serve_state === "on")) {
    const week = await (await request.get(`/api/places/${park.id}/week?tolerance=moderate&purpose=sight`)).json();
    if (!week.days.some((day: { state: string; windows: unknown[] | null }) => day.state !== "off" && day.windows?.length)) continue;
    found = true;
    await page.goto(`/ko/p/${park.id}`);
    const card = page.locator("[data-answer-card]");
    await expect(card).toContainText(/(사람이 적어요|사람이 적당해요|조금 붐벼요|꽤 붐벼요)/);
    await expect(card).not.toContainText(/(적고|적당하고|붐비지만)\s*$/m);
    await page.goto(`/en/p/${park.id}`);
    await expect(page.locator("[data-answer-card]")).toContainText(/It is (quiet|moderately busy|a bit busy|quite busy)(?! (and|but))/);
    break;
  }
  expect(found, "no A2 park with a pick this week").toBe(true);
});

// ---- mocked: states the live data does not have right now

test("late data on home is said as late data, not as a calm city", async ({ page }) => {
  await page.route("**/api/home**", (route) => route.fulfill(json({ as_of: "2026-10-02T05:30:00+00:00", stale: true, busy_top: [], open_quiet: [] })));
  await page.goto("/ko");
  await expect(page.locator("[data-state=stale]")).toHaveText("데이터가 늦어지고 있어요 (마지막 14:30)");
  await expect(page.getByText("지금은 붐비는 곳이 없어요")).toHaveCount(0);
  await expect(page.getByText("지금은 열려 있고 한산한 곳이 없어요")).toHaveCount(0);
});

test("fresh data with nothing busy says so", async ({ page }) => {
  await page.route("**/api/home**", (route) => route.fulfill(json({ as_of: new Date().toISOString(), stale: false, busy_top: [], open_quiet: [] })));
  await page.goto("/ko");
  await expect(page.locator("[data-busy-empty]")).toHaveText("지금은 붐비는 곳이 없어요");
  await expect(page.locator("[data-quiet-empty]")).toHaveText("지금은 열려 있고 한산한 곳이 없어요");
});

test("a late observation on the week screen shows the stale line and a dimmed list", async ({ page }) => {
  const day = (offset: number) => ({
    date: kstDate(offset), state: "on", off_reason: null, no_window: false, strip_mode: "windows_only", holiday: null,
    windows: [{ hours: [13], score: 0.8, crowd: 1, act: "sight", act_level: "lively" }], hours: hours(),
  });
  await page.route("**/api/places/*/week**", (route) =>
    route.fulfill(json({
      place,
      now: { level: null, source: "live", stale: true, ts: "2026-10-02T05:30:00+00:00", pop_min: 1, pop_max: 2 },
      days: Array.from({ length: 8 }, (_, index) => day(index)),
      combos: [{ purpose: "sight", tolerance: "moderate", state: "on" }],
    })),
  );
  await page.goto("/ko/p/POI001");
  await expect(page.locator("[data-answer-card]")).toContainText("데이터가 늦어지고 있어요 (마지막 14:30)");
  await expect(page.locator("[data-answer-card] [data-status-dot]")).toHaveCount(0);
  await expect(page.locator(".opacity-50 [data-week-time]")).toHaveCount(8);
});

test("the admin page refuses a repeated token", async ({ request }) => {
  expect((await request.get("/admin/eval?token=a&token=b")).status()).toBe(404);
  expect((await request.get("/admin/eval")).status()).toBe(404);
});

test("english pages keep Hangul inside lang=ko", async ({ page }) => {
  for (const path of ["/en", "/en/search", "/en/p/POI014", `/en/p/POI014/${kstDate(1)}`, "/en/map", "/en/about"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    expect(await strayHangul(page), path).toEqual([]);
  }
});
