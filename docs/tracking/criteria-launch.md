# criteria-launch — publish, harden, polish (2026-10-07)

Written before the first edit, from a sweep of the deployed app (`urbanpulse-swart.vercel.app`, build 7baf0e3).
Rows flip to `[x]` with the command and exit code as they pass. Authorised by the user's "전체적으로 앱 점검해서
퍼블리시 단계까지 올리고 폴리싱도 하고 메커니즘 더 단단하게" (straight-through run).

Goal (user's view): the site can be announced. Search engines may index it, a shared link shows a proper card,
the site can be added to a phone's home screen, a broken page says so in the app's own words, a browser cannot be
tricked into running foreign script on it, slow or missing data raises an alert without anyone watching, and the
screens pass an accessibility scan.

## P — publish

- [ ] P1 `X-Robots-Tag: noindex` is gone from every page and API; `/robots.txt` allows `/ko`, `/en` and disallows
      `/api/`, `/admin`; `/sitemap.xml` lists the static screens in both locales and every served A1/A2 place week.
      → verify: `curl -sI /ko | grep -i x-robots` empty; `/robots.txt` 200; `/sitemap.xml` 200 with ≥ 200 `<loc>`;
      `90_verify` flipped to expect no `noindex`
- [ ] P2 Metadata: `metadataBase`, Korean/English `description` per locale, Open Graph + Twitter card with a 1200×630
      PNG, `theme-color`, `manifest.webmanifest` (name, icons 192/512 PNG, maskable), `apple-touch-icon` 180 PNG.
      → verify: `curl -s /ko | grep -o '<meta[^>]*og:image[^>]*>'`; `/manifest.webmanifest` 200 JSON; the PNGs 200
- [ ] P3 `<html lang>` is `ko` on `/ko/**` and `en` on `/en/**` (already via proxy header) and the compare page has a
      title. → verify: Playwright D9 (unchanged) + `curl -s /en | grep -o '<html[^>]*lang="en"'`

## H — harden

- [ ] H1 Content-Security-Policy with a per-request nonce (Next's documented proxy pattern): `script-src 'self'
      'nonce-…' 'strict-dynamic'`, `style-src 'self' 'unsafe-inline'`, `img-src 'self' data: blob:
      https://tiles.openfreemap.org`, `connect-src 'self' https://tiles.openfreemap.org`, `worker-src 'self' blob:`,
      `font-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`.
      The map, the fonts and the service worker keep working.
      → verify: full Playwright on the deployment with console-error watchers (visual, journey, map specs) green;
      `curl -sI /ko | grep -i content-security-policy`
- [ ] H2 Error boundaries: `app/[locale]/error.tsx` and `app/global-error.tsx` show "불러오지 못했어요." + "다시 시도"
      in the visitor's language; a render error in one screen never shows Next's default page.
      → verify: Playwright D26 — a mocked `/api/places/*/recommend` body with a cell lacking `crowd` throws in render
      and the boundary text appears; `expect(errors)` records the thrown message, no uncaught crash
- [ ] H3 `/api/home` origin latency: independent queries run in parallel (`Promise.all`), the cold response drops
      from ~4.0 s to under 1.5 s on the deployment.
      → verify: `curl -o /dev/null -w "%{time_total}"` with `Cache-Control: no-cache` three times, median < 1.5 s;
      `api.spec` home key/rule tests unchanged and green
- [ ] H4 Freshness alert: a Cloud Scheduler trigger runs `urbanpulse-integrity` hourly; the existing failure alert
      policy (any failed job execution) then fires when stored rows break an invariant. `60_schedule.ps1` carries
      the fifth trigger; the runbook table names it.
      → verify: `gcloud scheduler jobs list --location asia-northeast3` shows `urbanpulse-integrity ENABLED`; one
      manual execution `succeededCount 1`
- [ ] H5 Accessibility scan: `@axe-core/playwright` on home, search, week, day, map, compare, about in both
      locales reports zero `serious`/`critical` violations.
      → verify: new `e2e/a11y.spec.ts` green on the deployment

## Q — polish

- [ ] Q1 About page: the per-combination table sits behind a `<details>` whose summary gives the counts (켜짐 / 참고용
      / 준비 중 조합 수); the page opens with the two explanatory paragraphs only.
      → verify: Playwright D27 — summary text present, rows hidden until opened
- [ ] Q2 Home card and row names wrap to two lines instead of truncating ("DMC(디지털미디어시티)" readable).
      → verify: Playwright visual home test still green; screenshot
- [ ] Q3 PC width (1280): the phone column is centred on `--bg-soft`, the map uses the side list; no horizontal
      scroll. → verify: Playwright viewport 1280×800 screenshot + `document.documentElement.scrollWidth <= 1280`

## Gates and deploy

- [ ] G1 `npm test`, `npx tsc --noEmit`, `npm run lint`, `npm run build`, `node scripts/check-messages.mjs`,
      `ruff check`, `pytest` (if engine/scripts touched) all exit 0.
- [ ] G2 `vercel deploy --prod`; full Playwright on the deployment (from `app/web`); `90_verify` product lines OK.
- [ ] G3 Design spec v3.1 (§1 launch notes, §5.10 error state, §6.7 about), build contract v8.0 (§6 CSP/robots/
      sitemap, §4.9 integrity schedule), runbook (schedule table, launch checklist), project map; Korean commits
      pushed.

## Out of scope

- A custom domain (none exists under the Vercel team; the user's call), analytics, dark mode, English place names,
  collection-gap marker, E6, rate limiting beyond input validation (Vercel WAF is a dashboard setting).

## Boundaries

- ✅ always: gates before each commit; strings only in `messages/*.json`; tokens only; no secret values in logs.
- ⚠️ reported, not asked (straight-through run): the Cloud Scheduler trigger, the production deploy, the noindex
  removal (the user asked for the publish stage).
- 🛑 never: weaken a test to pass; `unsafe-inline` for scripts; a fallback page that hides an error.
