import { expect, test } from "@playwright/test";

// What a crawler, a share sheet and a phone's "add to home screen" see once the site is announced.

test("pages are indexable, carry a nonce-based CSP, and name their card", async ({ page, request }) => {
  const response = await page.goto("/ko");
  expect(response?.headers()["x-robots-tag"]).toBeUndefined();
  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
  expect(csp).not.toMatch(/script-src[^;]*'unsafe-inline'/);
  expect(csp).toContain("img-src 'self' data: blob: https://tiles.openfreemap.org");
  await expect(page.locator("html")).toHaveAttribute("lang", "ko");
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute("content", /\/og\.png$/);
  await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /서울/);
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", "#0f1822");
  await page.goto("/en/about");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /Seoul/);
  await expect(page.locator('meta[property="og:locale"]')).toHaveAttribute("content", "en_US");
  // Two visits, two nonces.
  const second = await request.get("/ko");
  expect(second.headers()["content-security-policy"]).not.toBe(csp);
  const api = await request.get("/api/health");
  expect(api.headers()["x-robots-tag"]).toBeUndefined();
});

test("robots, sitemap, manifest and the bitmaps answer", async ({ request }) => {
  const robots = await request.get("/robots.txt");
  expect(robots.status()).toBe(200);
  const robotsText = await robots.text();
  expect(robotsText).toContain("Disallow: /api/");
  expect(robotsText).toContain("Disallow: /admin");
  expect(robotsText).toMatch(/Sitemap: https?:\/\/\S+\/sitemap\.xml/);
  const sitemap = await request.get("/sitemap.xml");
  expect(sitemap.status()).toBe(200);
  const xml = await sitemap.text();
  const locs = xml.match(/<loc>/g) ?? [];
  // 2 locales × (home + 3 screens) plus 2 locales × every served place.
  expect(locs.length).toBeGreaterThanOrEqual(8 + 2 * 50);
  expect(xml).toContain("/ko/p/POI001</loc>");
  expect(xml).toContain("/en/about</loc>");
  const manifest = await request.get("/manifest.webmanifest");
  expect(manifest.status()).toBe(200);
  const body = await manifest.json();
  expect(body.name).toBe("UrbanPulse");
  expect(body.icons.map((icon: { sizes: string }) => icon.sizes)).toEqual(["192x192", "512x512", "512x512"]);
  for (const file of ["/og.png", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png", "/icon.svg"]) {
    const asset = await request.get(file);
    expect(asset.status(), file).toBe(200);
  }
});
