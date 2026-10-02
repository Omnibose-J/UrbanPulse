# Findings — problems found outside the current SOW's scope

Append one entry per finding: date, where it was found, why it cannot be fixed now, what it touches (blast radius).
Never fix these off-scope; never drop them silently.

| Date | Found in | Finding | Why not now | Touches |
|---|---|---|---|---|
| 2026-09-29 | key check | The local `GOOGLE_MAPS_KEY` loads the Maps JavaScript API but its Google Cloud project has no billing (`BillingNotEnabledMapError`) | Cloud is SOW-MC; decide billing vs MapLibre there | `/map` (design spec §5.11), SOW-MC |
| 2026-10-01 | SOW-M5 archive | Deleting `commerce_obs` older than 90 days would starve `lively_profile`, which averages all history before today for `holiday` and `myeongjeol` | Retention needs a design decision before any non-dry-run archive | `lively.py`, build contract §4.7 |
| 2026-10-02 | forecast midnight fix | `apply_overlay` still bounds `live_obs` and `city_fcst` with SQL `now()`, while the forecast delete now uses the issued day. A job that crosses midnight can overlay the new day. `collect` calls the same function with its own run time | Resolved in SOW-M7 step 6: `apply_overlay` uses the timestamp its caller passes | `forecast.py` `apply_overlay`, `collect.py` |
| 2026-10-02 | SOW-H1 review | The admin token travels in the query string, so it lands in access logs and browser history | Needs a cookie or header flow; the page is local-only until SOW-MC | `app/web/src/app/admin/eval/page.tsx`, SOW-MC |
| 2026-10-02 | SOW-H1 review | Screens navigate with `<a href>` (a full page load each time) instead of client-side links | Works correctly; a speed matter, and the back-stack behaviour is tested as it is | every screen, `components/ui.tsx` |
| 2026-10-02 | SOW-H1 review | `middleware.ts` is deprecated in Next 16 in favour of `proxy.ts` | Still supported; rename with the next Next upgrade | `app/web/src/middleware.ts` |
| 2026-10-02 | SOW-H1 e2e | No place has an English name (`name_en` null for all), so an English search by name finds nothing and English screens show Korean names | Needs the `DATA_GO_KR_KEY` for the English place API | `load_places`, search, every `/en` screen |
| 2026-10-02 | SOW-H1 e2e | Hours of today that were never collected (2026-10-02 03:00 to 09:30) stay `model` rows; no screen says there was a collection gap | Past hours are not shown as "now"; a gap marker is a design question | `forecast_hourly`, the day strip |
