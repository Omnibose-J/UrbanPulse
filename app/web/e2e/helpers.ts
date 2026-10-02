import path from "node:path";

import type { Page } from "@playwright/test";
import { createClient } from "@supabase/supabase-js";
import { config } from "dotenv";

// The database is read directly only to compare it with what the screens and routes show, or to find a row in a given state.
config({ path: path.resolve(__dirname, "../../../.env"), quiet: true });
export const db = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!, { auth: { persistSession: false } });

/** A KST calendar date `offset` days from today, as YYYY-MM-DD. */
export function kstDate(offset = 0): string {
  return new Date(Date.now() + 9 * 3600e3 + offset * 86400e3).toISOString().slice(0, 10);
}

export function kstHourNow(): number {
  return new Date(Date.now() + 9 * 3600e3).getUTCHours();
}

/** Collects console errors and failed API responses so a test can assert there were none. */
export function watch(page: Page) {
  const errors: string[] = [];
  const failed: string[] = [];
  const api: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith("/api/")) return;
    api.push(url.pathname + url.search);
    if (response.status() >= 400) failed.push(`${response.status()} ${url.pathname}${url.search}`);
  });
  return { errors, failed, api };
}

/** Text nodes with Hangul that are not inside an element marked lang="ko". */
export function strayHangul(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const found: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (/[가-힣]/.test(node.textContent ?? "") && !node.parentElement?.closest("[lang=ko]")) found.push((node.textContent ?? "").trim());
    }
    return found;
  });
}
