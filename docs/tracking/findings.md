# Findings — problems found outside the current SOW's scope

Append one entry per finding: date, where it was found, why it cannot be fixed now, what it touches (blast radius).
Never fix these off-scope; never drop them silently.

| Date | Found in | Finding | Why not now | Touches |
|---|---|---|---|---|
| 2026-09-29 | key check | The local `GOOGLE_MAPS_KEY` loads the Maps JavaScript API but its Google Cloud project has no billing (`BillingNotEnabledMapError`) | Closed: the map stays MapLibre + OpenFreeMap (SOW-MC scope note); the key is unused | `/map` (design spec §5.11) |
| 2026-10-01 | SOW-M5 archive | Deleting `commerce_obs` older than 90 days would starve `lively_profile`, which averages all history before today for `holiday` and `myeongjeol` | Retention needs a design decision before any non-dry-run archive | `lively.py`, build contract §4.7 |
| 2026-10-02 | forecast midnight fix | `apply_overlay` still bounds `live_obs` and `city_fcst` with SQL `now()`, while the forecast delete now uses the issued day. A job that crosses midnight can overlay the new day. `collect` calls the same function with its own run time | Resolved in SOW-M7 step 6: `apply_overlay` uses the timestamp its caller passes | `forecast.py` `apply_overlay`, `collect.py` |
| 2026-10-02 | SOW-H1 review | The admin token travels in the query string, so it lands in access logs and browser history | Resolved in SOW-L1: token form at `/admin`, httpOnly session cookie, no token in any address | `app/web/src/app/admin/`, `lib/admin-session.ts` |
| 2026-10-02 | SOW-H1 review | Screens navigate with `<a href>` (a full page load each time) instead of client-side links | Resolved in SOW-L1: `next/link` everywhere except the language switch (the `lang` attribute is set by the server) | every screen, `components/ui.tsx` |
| 2026-10-02 | SOW-H1 review | `middleware.ts` is deprecated in Next 16 in favour of `proxy.ts` | Resolved in SOW-L1: renamed to `proxy.ts` | `app/web/src/proxy.ts` |
| 2026-10-02 | SOW-H1 e2e | No place has an English name (`name_en` null for all), so an English search by name finds nothing and English screens show Korean names | Needs the `DATA_GO_KR_KEY` for the English place API | `load_places`, search, every `/en` screen |
| 2026-10-02 | SOW-H1 e2e | Hours of today that were never collected (2026-10-02 03:00 to 09:30) stay `model` rows; no screen says there was a collection gap | Past hours are not shown as "now"; a gap marker is a design question | `forecast_hourly`, the day strip |
| 2026-10-02 | SOW-L1 rehearsal | Alternative dates with equal scores came out in a different order from `forecast` and from the `collect` refresh, so a visitor could see the alternatives swap for no reason | Resolved in SOW-L1: ties go to the nearer date (`reco._alt_dates`), with a test | `recommendations.alt_dates` |
| 2026-10-02 | SOW-L1 | No alert when a job fails; the jobs table on `/admin` is the only place it shows | Needs a notification channel the user owns | every scheduled job, `docs/RUNBOOK.md` §6 |
| 2026-10-02 | SOW-L1 rehearsal | `ingest_raw` lets a storage error escape as a traceback instead of a `fail` ledger row | The run still exits non-zero; ledger handling is a small change best made with the first real bucket | `jobs/ingest_raw.py`, `raw_gcs.py` |
| 2026-10-02 | SOW-L1 | `next build` while `next dev` is running left the dev server answering API routes with 404 until it was restarted | A dev-box nuisance; build with the dev server stopped | `app/web/.next` |
| 2026-10-02 | SOW-L1 | The map selects the first place of the list on load; nothing in the design spec says whether that or no selection is intended | A design question for the designer and the user | `screens/map.tsx`, design spec §5.11 |
