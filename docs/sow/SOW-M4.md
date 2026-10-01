# SOW-M4 — Screens (local, `next dev`)

Work units W10, W11, W13: the read-only API and every visitor screen of `UrbanPulse_디자인명세서.md`, Korean and English, running on `next dev` against the local database. The visual reference is `design/UrbanPulse_시안_v6.html`; where it and the design spec differ, the spec wins and you report the difference. No engine change, no schema change, no cloud, no deploy.

## Depends on

SOW-M3 done: `recommendations`, `forecast_hourly`, `similar_places` are filled by the scheduled jobs.

## Decisions already made (do not reopen)

- **Map**: MapLibre GL JS (`maplibre-gl`) with the OpenFreeMap `positron` style (`https://tiles.openfreemap.org/styles/positron`, no key). The local Google key has no billing (see `docs/tracking/findings.md`); Google Maps is reconsidered at SOW-MC. Set label language by switching text fields to `name:ko` / `name:en` with fallback to `name`. If the style cannot be reached, the pins and the card still work on an empty background; report it.
- **Data access**: screens are client components that fetch the route handlers below. Route handlers read tables with the server Supabase client. This gives every screen its loading, error and stale states and lets tests replace API responses.
- **Dependencies you may add** to `app/web`: `next-intl`, `lucide-react`, `maplibre-gl`, `pretendard` (font files for `next/font/local`), dev: `@playwright/test`. Nothing else without reporting why.

## Files you may touch

Everything under `app/web/` except `AGENTS.md`, `CLAUDE.md`, `README.md`; `docs/tracking/criteria-m4.md`; `docs/LLM_PROJECT_MAP.md`.
Read-only: `app/engine/`, `app/supabase/`, `analysis/`, specs, `design/`, `docs/sow/`, `AGENTS.md`.

## Steps

### 1 Foundation
- `src/styles/tokens.css`: every token of design spec §3 as CSS variables, wired into Tailwind `@theme`. Add `--stale-fg: #8A6D1F` (used by §5.7-1; the spec names it without a value). No hex anywhere else.
- Pretendard Variable through `next/font/local`; type scale of §3.2 as utility classes.
- `next-intl`: routes under `src/app/[locale]/` with `ko`, `en`; `/` redirects by `Accept-Language` (default `ko`); `<html lang>` set; language switch in `AppBar` keeps the current path and query.
- `messages/ko.json`, `messages/en.json`: every key of §9.2 byte for byte, the reason sentences of §9.3, and the state texts of §5.2, §5.5, §5.6, §5.8, §5.10, §5.11. Where the spec gives only Korean, write the English yourself in the same plain register, no dashes, and list every such key under Open facts as "new copy". Where a screen needs a string the spec does not have at all, add a key in both files and list it the same way.
- `scripts/check-messages.mjs`: fails when the two files' key sets differ or any value contains `—` or `–`. Run it in `npm run build` (`prebuild`).
- Formatting helpers (`src/lib/format.ts`): dates and times per §9.1 (ko `13~15시`, en `1 to 3 PM`; ko `10월 4일 (일)`, en `Sun, Oct 4`), all in KST regardless of the browser zone.

### 2 API (route handlers under `src/app/api/`, read-only, `Cache-Control: s-maxage=300`)
Validate parameters (`tolerance` in `calm|moderate|busy_ok`, `purpose` in `sight|food|shop|none`, `date` `YYYY-MM-DD`); invalid → 400 `{"error": "..."}`. Unknown place → 404. Database error → 500 `{"error": "unavailable"}`, never cached. Handlers select, filter, sort and shape rows; they never compute a level, a score or a state.

| Route | Returns |
|---|---|
| `GET /api/places?q=` | places with `serve_state` in `on`, `preparing`, `experimental`: `id, tier, name, name_en, gu, serve_state`. `q` matches `name`, `name_en`, `gu` case-insensitively. Empty `q` → A1/A2 `on` places only (the "많이 찾는 곳" list), ordered by name. Tier B rows appear only when `q` is non-empty |
| `GET /api/places/[id]/week?tolerance=&purpose=` | `place` (`id, tier, name, name_en, gu, serve_state, foreign_heavy`), `now` (current-hour `forecast_hourly` row: `level, source, stale`, plus the latest `live_obs` `ts, pop_min, pop_max`; null for tier B), `days` (8 `recommendations` rows from today: `date, state, off_reason, windows, no_window, hours, strip_mode`, each with the `holidays` name and kind when the date is one), `combos` (for today: state of all nine purpose × tolerance rows, or three for A2/B). For A2 and B, `purpose` is forced to `none` |
| `GET /api/places/[id]/recommend?date=&tolerance=&purpose=` | one `recommendations` row with `alt_dates`, `alt_places` (each alt place joined to its `name`, `name_en`), `place`, `holiday`, `combos` for that date. `date` before today (KST) → 410 |
| `GET /api/places/[id]/day?date=` | the 15 `forecast_hourly` rows of hours 9…23: `target_ts, source, level, a_all, a_food, a_shop, stale, ready` |
| `GET /api/home?tolerance=&purpose=` | `as_of` (latest `live_obs.ts`), `stale` (`as_of` older than 90 minutes), `busy_top`: 5 A1/A2 `on` places by current-hour `forecast_hourly.level` descending where `source = 'live'`, ties by latest `live_obs.pop_max` descending; each with `level, pop_min, pop_max` and today's first window for the requested tolerance and purpose (`none` for A2). `open_quiet`: up to 5 `on` places with current-hour level 0 or 1 and (A1) `a_all >= 0.5` on the latest today row with `a_actual = true`, no more than 2 hours before the current hour (no such row → the place is not listed) or (A2) today's `moderate`/`none` cell for the current hour has `reason <> 'outside_hours'`; A1 first by `a_all` descending, then A2; each with today's first window, `hours`, `strip_mode` |
| `GET /api/map?date=&tolerance=&purpose=&stations=0|1` | every place with a row for that date: `id, tier, name, name_en, lat, lon, state, windows, hours, strip_mode`. A1 rows use `purpose`; A2 and B use `none`. Tier B only when `stations=1` |
| `GET /api/flags` | today's `recommendations` grouped by tier, `foreign_heavy`, purpose, tolerance, state: counts. Used by `/about` |

`open_quiet` reads measured activity only (`a_actual`, written by the engine's overlay in SOW-M3). Never fall back to the expected profile value: that choice failed its bar (E16).

### 3 Components (design spec §5; sizes §4)
`AppBar`, `AnswerCard` (week / day / none / preparing variants), `ConditionField`, `ConditionSheet`, `WeekList`, `DayStrip`, `PlaceCard`, `BusyRank`, `PlaceRow`, `SearchField`, `AltButton`, `Badge`, `StateBox` (preparing, error with retry, skeleton), `MapView`. Rules that are easy to miss:
- The strip and the pins draw three kinds only when `strip_mode = 'two_step'`; with `windows_only` they draw window cells `--go` and everything else `--bad`, and the legend shows only "추천" (§7.3). The hourly reason line still shows on tap.
- `ConditionSheet` takes option states from `combos`; it holds no table of its own. Off → disabled with the explanation line; the auto-move rule of §5.6.
- A1 on a myeongjeol date (`off_reason = 'myeongjeol'`): hatched grey strip, the closure sentence, no `ConditionField` (§5.10).
- `stale` → the status line changes and the strip is 50 % opaque. API failure → error box with retry; never render older data.
- Conditions (purpose, tolerance) and favourites live in `localStorage`; with storage unavailable the defaults (`sight`, `moderate`) apply and nothing throws.
- Tier B (`tier = 'B'`): `추정 · 실험` badge, no purpose row, B reason sentences (§9.3), no "now" line. Build and test these with mocked responses; real B rows arrive in SOW-MB.

### 4 Screens (design spec §2, §6)
- ① `/[locale]`: order of §6.1. TOP 5 row → ③; open-and-quiet card → today's ⑤; favourites → ③; map button → ⑦.
- ② `/[locale]/search`: input focused, results from `/api/places?q=` (debounced 200 ms), empty-state sentences of §5.8.
- ③ `/[locale]/p/[id]`: answer card (best window of the week = highest first-window score among the 8 days) → condition field → week list → legend. `serve_state = 'preparing'` or every day off/preparing → the preparing box.
- ⑤ `/[locale]/p/[id]/[date]`: answer card → (⑥ alt buttons when `no_window`) → condition field → strip → legend → reason box. Query `?purpose=&tol=` overrides stored conditions for that view (share link). A past date → redirect to ③ with the one-time notice of §2.2. Back button → ③ of the same place even without history.
- ⑦ `/[locale]/map?date=&hour=`: date chips, hour slider (one fetch per date and condition; moving the slider fetches nothing), pins, legend, "역세권 포함" toggle (default off, remembered), bottom card → ⑤; returning from ⑤ restores date and hour. Width ≥ 1024: full-width map with a 400 px list on the right ordered recommended → OK → avoid; clicking a row flies to the pin.
- `/[locale]/about`: what it does, how the forecast works, the on / reference / preparing table from `/api/flags`, limits, data sources with the 공공누리 attribution. Take the facts from `UrbanPulse_PRD.md` and 서비스정의서; do not add claims.
- Width ≥ 1024 on ①–⑤: a 440 px centred column on `--bg-soft`.
- Accessibility per §8 (radiogroup, dialog focus, `aria-label` on cells, screen-reader table for the strip, focus ring).

### 5 Tests
- `npm run lint`, `npm run build` (includes the message check).
- `scripts/contrast.mjs`: contrast ratios of the colour pairs of §3.1 against §8 (D2).
- Playwright (`app/web/e2e/`, viewport 390 × 844, both locales), responses mocked with `page.route` from fixtures in `e2e/fixtures/` unless a test says "live":
  - D1 answer card fully inside the first viewport on ③ and ⑤.
  - D3 one screenshot per state: preparing, stale, error, skeleton, A1 myeongjeol, ⑥ no window, reference badge, tier B, week with no pick. Saved under `e2e/screenshots/` (gitignored).
  - D4 condition rules. D5 flow and back order incl. a share link. D6 sizes: every pressable box height equals the §4.1 table, text starts at x = 16.
  - D9 no Hangul on `/en/...` outside `lang="ko"` elements.
  - D10 map: pin colour equals the ⑤ cell colour for the same hour; slider moves add no request; card → ⑤ → back restores date and hour.
  - D11 `windows_only` draws two kinds. D12 home list rules on a fixture.
  - Live smoke (no mocks): ① loads, the first TOP 5 row opens ③, its answer card opens ⑤; every API route returns 200 with the documented keys.

## Acceptance (`docs/tracking/criteria-m4.md`, rows created before step 1)

| # | Criterion | Command |
|---|---|---|
| A1 | Build, lint, messages | `cd app/web; npm run lint` → exit 0; `npm run build` → exit 0; `node scripts/check-messages.mjs` → exit 0 with the key count |
| A2 | API live | with `npm run dev`: each route of step 2 → 200 and the documented top-level keys (paste one line per route); bad `tolerance` → 400; unknown id → 404; yesterday's `date` on `recommend` → 410 |
| A3 | Design checks | `npx playwright test` → exit 0; paste the count of passed tests and the D-numbers they cover |
| A4 | Contrast | `node scripts/contrast.mjs` → exit 0, table pasted |
| A5 | No literal copy, no hex | `git grep -n -P "[가-힣]" -- app/web/src ':!app/web/src/**/*.test.*'` → no match outside comments; `git grep -n -E "#[0-9A-Fa-f]{3,8}\b" -- app/web/src ':!app/web/src/styles/tokens.css'` → no match |
| A6 | No dash in copy; error colour scope | `git grep -n -e "—" -e "–" -- app/web/messages` → no match; `git grep -n "error-fg" -- app/web/src` → only the error state component and `tokens.css` |
| A7 | Secrets stay on the server | after `npm run build`: the service-role key value and `DATABASE_URL` value do not occur under `app/web/.next/static` (script prints `no match`, never the value) |
| A8 | Live walk-through | Playwright live smoke passes; paste the place id it walked and the answer-card time text in ko and en |
| A9 | Engine untouched | `git diff --stat <M3 last commit>..HEAD -- app/engine app/supabase analysis` → empty |

## Open facts to report

- Every "new copy" key with its ko and en text.
- Differences found between mockup v6 and the design spec.
- Whether the OpenFreeMap style loaded and whether `name:en` labels showed.
- Screens or states that could only be checked with mocked data because the live database has no such row today (for example myeongjeol, tier B).
- Lighthouse or bundle numbers if you measured any; not required.
