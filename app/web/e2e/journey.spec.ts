import { expect, test } from "@playwright/test";

import { kstDate, watch } from "./helpers";

// Live local stack, no mocks. The device clock is in another zone on purpose: the site must still speak KST.
test.use({ timezoneId: "America/Los_Angeles", locale: "ko-KR" });

test("search to week to day, conditions, back chain, favourite and share link", async ({ page, request }) => {
  const seen = watch(page);

  // Walk a place that has a pick this week. With none the service has nothing to show, which is a failure.
  const popular = (await (await request.get("/api/places?q=")).json()).places as { id: string; tier: string; name: string }[];
  let target: { id: string; name: string } | undefined;
  for (const candidate of popular.filter((row) => row.tier === "A1")) {
    const body = await (await request.get(`/api/places/${candidate.id}/week?tolerance=moderate&purpose=sight`)).json();
    if (body.days.some((day: { state: string; windows: unknown[] | null }) => day.state !== "off" && day.windows && day.windows.length > 0)) {
      target = candidate;
      break;
    }
  }
  expect(target, "no A1 place has a recommendation this week").toBeTruthy();

  // ① home
  await page.goto("/");
  await expect(page).toHaveURL(/\/ko$/);
  await expect(page.locator("[data-busy] [data-row], [data-busy-empty], [data-state=stale], [data-state=preparing]").first()).toBeVisible();

  // ② search
  await page.locator('a[href$="/search"]').click();
  await expect(page).toHaveURL(/\/ko\/search$/);
  const input = page.locator("input");
  await expect(input).toBeFocused();
  await input.fill("zzzz없는곳");
  await expect(page.getByText("찾는 장소가 없어요")).toBeVisible();
  await input.fill("서울역(1호선)");
  await expect(page.locator("[data-state=error]")).toHaveCount(0);
  await expect(page.getByText("찾는 장소가 없어요")).toBeVisible();
  await input.fill(target!.name);
  const hit = page.locator(`[data-row][href$="/p/${target!.id}"]`);
  await expect(hit).toBeVisible();
  await hit.click();

  // ③ week
  await expect(page).toHaveURL(/\/ko\/p\/[A-Z0-9]+$/);
  const weekUrl = page.url();
  const id = weekUrl.split("/").pop()!;
  const card = page.locator("[data-answer-card]");
  await expect(card).toBeVisible();
  await expect(page.locator("[data-week-time]")).toHaveCount(8);
  expect(id).toBe(target!.id);
  await card.click();

  // ⑤ day
  await expect(page).toHaveURL(/\/ko\/p\/[A-Z0-9]+\/\d{4}-\d{2}-\d{2}$/);
  const cells = page.locator("[data-cell]");
  await expect(cells).toHaveCount(15);
  const sentence = page.locator("[data-hour-sentence]");
  const hint = "칸을 누르면 그 시간이 어떤지 알려 드려요";
  await expect(sentence).toHaveText(hint);
  const windowCell = page.locator("[data-cell][data-tone=go]").first();
  await windowCell.click();
  await expect(sentence).toContainText("추천 시간이에요");
  await expect(sentence).not.toContainText("가도 괜찮아요");
  await expect(sentence).not.toContainText("피하는 게 좋아요");
  const plain = page.locator("[data-cell][data-tone=bad]").first();
  await plain.click();
  await expect(sentence).toHaveText(/^\d+시는 추천 시간이 아니에요\.$/);
  await plain.click();
  await expect(sentence).toHaveText(hint);
  await plain.focus();
  await page.keyboard.press("Enter");
  await expect(sentence).toHaveText(/^\d+시는 추천 시간이 아니에요\.$/);

  // ④ conditions: closing changes nothing and sends nothing
  const field = page.locator("[data-field-label]").first();
  await expect(field).toHaveText("구경·산책 · 적당히");
  const before = seen.api.length;
  const opener = page.getByRole("button", { name: /바꾸기/ });
  await opener.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  expect(await page.evaluate(() => Boolean(document.activeElement?.closest("[role=dialog]")))).toBe(true);
  await page.getByRole("radio", { name: "맛집" }).click();
  await expect(dialog).toContainText("맛집은 ‘한적하게’를 아직 준비하고 있어요.");
  await expect(dialog).not.toContainText("{");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(field).toHaveText("구경·산책 · 적당히");
  expect(seen.api.length).toBe(before);
  await expect(opener).toBeFocused();

  // apply: the field, the request and the stored conditions change; a tapped cell is cleared
  await opener.click();
  await page.getByRole("radio", { name: "맛집" }).click();
  const calm = page.getByRole("radio", { name: "한적하게" });
  await calm.click({ force: true });
  await expect(calm).toHaveAttribute("aria-checked", "false");
  await page.getByRole("button", { name: "적용하기" }).click();
  await expect(field).toHaveText("맛집 · 적당히");
  await expect.poll(() => seen.api[seen.api.length - 1]).toContain("purpose=food");
  expect(await page.evaluate(() => localStorage.getItem("urbanpulse.conditions"))).toBe('{"purpose":"food","tolerance":"moderate"}');
  await expect(page.locator("[data-state=error]")).toHaveCount(0);

  // back chain
  await page.goBack();
  await expect(page).toHaveURL(weekUrl);
  await expect(page.locator("[data-field-label]").first()).toHaveText("맛집 · 적당히");
  await page.goBack();
  await expect(page).toHaveURL(/\/ko\/search$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/ko$/);

  // favourite survives a reload and shows on home
  await page.goto(weekUrl);
  const star = page.locator("button.icon-hit[aria-pressed]");
  await expect(star).toHaveAttribute("aria-pressed", "false");
  await star.click();
  await expect(star).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.locator("button.icon-hit[aria-pressed]")).toHaveAttribute("aria-pressed", "true");
  await page.goto("/ko");
  await expect(page.getByRole("heading", { name: "관심 장소" })).toBeVisible();

  // a share link overrides the conditions for that view without storing them; the app back button opens the week
  await page.goto(`/ko/p/${id}/${kstDate(2)}?purpose=shop&tol=busy_ok`);
  await expect(page.locator("[data-field-label]").first()).toHaveText("쇼핑 · 붐벼도 돼요");
  expect(await page.evaluate(() => localStorage.getItem("urbanpulse.conditions"))).toBe('{"purpose":"food","tolerance":"moderate"}');
  await page.locator("header a").first().click();
  await expect(page).toHaveURL(new RegExp(`/ko/p/${id}$`));

  expect(seen.errors).toEqual([]);
  expect(seen.failed).toEqual([]);
});
