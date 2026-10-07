/** The public origin of the site, for absolute links in metadata, the sitemap and push notifications. Vercel gives
 * `VERCEL_PROJECT_PRODUCTION_URL` (no scheme) on every deployment; `SITE_URL` overrides it when a custom domain
 * exists. A missing value is a build-time defect, not a silent "localhost". */
export function siteUrl(): string {
  const explicit = process.env.SITE_URL;
  if (explicit) return explicit.replace(/\/$/, "");
  const vercel = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  if (vercel) return `https://${vercel}`;
  if (process.env.NODE_ENV !== "production") return "http://localhost:3000";
  throw new Error("missing env var: SITE_URL or VERCEL_PROJECT_PRODUCTION_URL");
}
