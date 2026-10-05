import type { Metadata } from "next";

import en from "../../messages/en.json";
import ko from "../../messages/ko.json";

/** The tab title of a static screen, in the page's locale (the root layout adds " · UrbanPulse"). */
export function titleOf(locale: string, pick: (messages: typeof ko) => string): Metadata {
  return { title: pick(locale === "en" ? en : ko) };
}
