import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/site";

/** Visitors' screens may be indexed; the data routes and the admin screen may not. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: ["/ko", "/en"], disallow: ["/api/", "/admin"] }],
    sitemap: `${siteUrl()}/sitemap.xml`,
  };
}
