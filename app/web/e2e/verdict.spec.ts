import { expect, test } from "@playwright/test";
import fs from "node:fs";

import { hours, place } from "./fixtures/place";
import { kstDate } from "./helpers";

const dayBody = (mode: "windows_only" | "two_step") => ({
  recommendation: {
    state: "on",
    off_reason: null,
    windows: [{ hours: [13], score: 1, crowd: 1, act: "sight", act_level: "lively" }],
    no_window: false,
    hours: hours(),
    strip_mode: mode,
  },
  place,
  holiday: null,
  combos: [{ purpose: "sight", tolerance: "moderate", state: "on" }],
  alt_dates: [],
  alt_places: [],
});

test("windows_only does not state an unverified verdict", async ({ page }) => {
  await page.route("**/api/places/*/recommend**", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(dayBody("windows_only")) }),
  );
  await page.goto(`/ko/p/POI001/${kstDate(2)}`);
  await page.locator("[data-hour='12']").click();
  const sentence = page.locator("[data-hour-sentence]");
  // The forecast crowd level and the next pick, never the two-step verdict (design spec 9.3, v3.0).
  await expect(sentence).toHaveText("12시는 추천 시간이 아니에요. 사람이 적당해요. 13~14시부터 추천 시간이에요.");
  await expect(page.getByText("피하는 게 좋아요")).toHaveCount(0);
  await expect(page.getByText("가도 괜찮아요")).toHaveCount(0);
  // The recommended cell says how busy and how lively it is, not the two-step verdict.
  await page.locator("[data-hour='13']").click();
  await expect(sentence).toHaveText("13시는 추천 시간이에요. 사람은 적당하고 거리도 활기차요");
  await expect(page.locator("[data-hour='13']")).toHaveAttribute("aria-label", "13시는 추천 시간이에요. 사람은 적당하고 거리도 활기차요");
  await expect(page.getByText("가도 괜찮아요")).toHaveCount(0);
  await page.locator("[data-hour='12']").click();
  fs.mkdirSync("e2e/screenshots/live", { recursive: true });
  await page.screenshot({ path: "e2e/screenshots/live/ko-day-not-pick.png", fullPage: true });

  await page.route("**/api/map**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        places: [
          {
            id: "POI001",
            tier: "A1",
            name: "Sample",
            name_en: null,
            lat: 37.57,
            lon: 126.98,
            state: "on",
            windows: [{ hours: [13] }],
            hours: hours(),
            strip_mode: "windows_only",
          },
        ],
        holidays: [],
      }),
    }),
  );
  await page.goto(`/ko/map?date=${kstDate(2)}&hour=12`);
  await expect(page.locator("[data-map-card] [data-hour-sentence]")).toHaveText("12시는 추천 시간이 아니에요. 사람이 적당해요. 13~14시부터 추천 시간이에요.");
  await expect(page.locator("[data-map-card]").getByText("피하는 게 좋아요")).toHaveCount(0);
  await expect(page.locator("[data-map-card]").getByText("가도 괜찮아요")).toHaveCount(0);
  await expect(page.locator("[data-legend]")).toHaveCount(1);
});

test("two_step still states the verdict and a reason", async ({ page }) => {
  await page.route("**/api/places/*/recommend**", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(dayBody("two_step")) }),
  );
  await page.goto(`/ko/p/POI001/${kstDate(2)}`);
  await page.locator("[data-hour='12']").click();
  const sentence = page.locator("[data-hour-sentence]");
  await expect(sentence).toHaveText("12시는 가도 괜찮아요. 사람은 적당하고 거리도 활기차요");
  await page.goto(`/en/p/POI001/${kstDate(2)}`);
  await page.locator("[data-hour='13']").click();
  await expect(page.locator("[data-hour-sentence]")).toHaveText("1 PM is a recommended time. It is moderately busy and the street is lively too");
});
