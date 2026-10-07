import type { MetadataRoute } from "next";

import { listServedPlaces } from "@/lib/queries";
import { siteUrl } from "@/lib/site";

export const dynamic = "force-dynamic";

/** The static screens in both languages and the week screen of every served A1/A2 place. Day screens change
 * daily and are left out; station areas (tier B, experimental) are reachable only through the search. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = siteUrl();
  const now = new Date();
  const entries: MetadataRoute.Sitemap = [];
  for (const locale of ["ko", "en"]) {
    entries.push({ url: `${base}/${locale}`, lastModified: now, changeFrequency: "hourly", priority: 1 });
    for (const screen of ["search", "map", "about"]) {
      entries.push({ url: `${base}/${locale}/${screen}`, lastModified: now, changeFrequency: "daily", priority: 0.6 });
    }
  }
  const places = await listServedPlaces();
  for (const place of places) {
    for (const locale of ["ko", "en"]) {
      entries.push({ url: `${base}/${locale}/p/${place.id}`, lastModified: now, changeFrequency: "daily", priority: 0.8 });
    }
  }
  return entries;
}
