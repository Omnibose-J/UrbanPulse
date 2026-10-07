import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { kstDate } from "./helpers";

// Every visitor screen in both languages: no serious or critical WCAG 2.x A/AA violation (axe-core). The map's
// canvas is excluded (a drawing, not content); the pins are buttons with names and are scanned.
const screens = (locale: string) => [
  `/${locale}`,
  `/${locale}/search`,
  `/${locale}/p/POI001`,
  `/${locale}/p/POI001/${kstDate(1)}`,
  `/${locale}/map`,
  `/${locale}/compare?a=POI001&b=POI002`,
  `/${locale}/about`,
];

for (const locale of ["ko", "en"]) {
  test(`axe: no serious or critical violation on the ${locale} screens`, async ({ page }) => {
    test.setTimeout(120000);
    const failures: string[] = [];
    for (const path of screens(locale)) {
      await page.goto(path);
      await expect(page.locator("main, .phone-shell, [data-map]").first()).toBeVisible();
      await page.waitForLoadState("networkidle");
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).exclude("canvas").analyze();
      for (const violation of results.violations) {
        if (violation.impact !== "serious" && violation.impact !== "critical") continue;
        failures.push(`${path} ${violation.id} (${violation.impact}): ${violation.nodes.slice(0, 3).map((node) => node.target.join(" ")).join(" | ")}`);
      }
    }
    expect(failures).toEqual([]);
  });
}
