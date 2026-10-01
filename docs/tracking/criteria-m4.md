# criteria-m4 — Screens on next dev

Written 2026-10-01 before implementation. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Build, lint, messages | `cd app/web; npm run lint` → exit 0; `npm run build` → exit 0; `node scripts/check-messages.mjs` → exit 0 with the key count | 0 / 0 / 0 | lint clean; build compiled and generated 12 routes; message check printed 108 |
| A2 | API live | with `npm run dev`: each route of step 2 → 200 and the documented top-level keys (paste one line per route); bad `tolerance` → 400; unknown id → 404; yesterday's `date` on `recommend` → 410 | 200 / 400 / 404 / 410 | places `places`; week `place,now,days,combos`; recommend `recommendation,place,holiday,combos,alt_places,alt_dates`; day `hours`; home `as_of,stale,busy_top,open_quiet`; map `places`; flags `rows`; bad tolerance `{"error":"invalid tolerance or purpose"}`; `NO_SUCH` `{"error":"unknown place"}`; 2026-09-30 recommend `{"error":"date has passed"}` |
| A3 | Design checks | `npx playwright test` → exit 0; paste the count of passed tests and the D-numbers they cover | 0 | first run 9 passed and the live smoke failed; later run after 20:00 became `live`: 11 passed (D1, D3, D4, D5, D6, D9, D10, D11, D12, admin 404, live smoke), exit 0 |
| A4 | Contrast | `node scripts/contrast.mjs` → exit 0, table pasted | 0 | text/bg 17.89, text-2/bg 6.40, text-3/bg 4.74, go-text/bg 5.39, go-text/go-soft 4.88, on-ink/ink 17.89, go-bright/ink 10.59, on-ink-2/ink 9.60, on-ink-3/ink 5.57, error-fg/bg 6.57, hol/bg 4.92, stale-fg/bg 4.90, all ok |
| A5 | No literal copy, no hex | `git grep -n -P "[가-힣]" -- app/web/src ':!app/web/src/**/*.test.*'` → no match outside comments; `git grep -n -E "#[0-9A-Fa-f]{3,8}\b" -- app/web/src ':!app/web/src/styles/tokens.css'` → no match | 1 / 1 | no text match after removing the default `favicon.ico` (it had matched as a binary); no hex outside `tokens.css` |
| A6 | No dash in copy; error colour scope | `git grep -n -e "—" -e "–" -- app/web/messages` → no match; `git grep -n "error-fg" -- app/web/src` → only the error state component and `tokens.css` | 1 | no dash in messages; `error-fg` is in `src/components/ui.tsx` and `src/styles/tokens.css` only |
| A7 | Secrets stay on the server | after `npm run build`: the service-role key value and `DATABASE_URL` value do not occur under `app/web/.next/static` (script prints `no match`, never the value) | 0 | `no match` |
| A8 | Live walk-through | Playwright live smoke passes; paste the place id it walked and the answer-card time text in ko and en | 0 | earlier `busy_top` was 0 while hour 20 was `seoul`; the passing run walked `POI109`. Best windows `[9],[10],[11]` display as `9~12시` / `9 AM to 12 PM` |
| A9 | Engine untouched | `git diff --stat 4aa14fe..HEAD -- app/engine app/supabase analysis` → empty | 0 | empty |

## Report

1. **Intent** — SOW-M4 serves the visitor screens from the local database: read-only route handlers, Korean and English copy, and the design-spec tokens. MapLibre is the map. No engine or schema change.

2. **Files** — created under `app/web`: `messages/{ko,en}.json`, `scripts/{check-messages,contrast}.mjs`, `src/styles/tokens.css`, `src/i18n/`, `src/middleware.ts`, `src/lib/{font,format,format.test,http,kst,queries,home-rules,storage,strip,use-load}.ts`, `src/app/api/{places,home,map,flags}`, `src/components/ui.tsx`, `src/screens/`, `src/app/[locale]/`, `e2e/`, `playwright.config.ts`. Modified: `package.json`, `package-lock.json`, `next.config.ts`, `tsconfig.json`, `src/app/{layout,page,globals.css}`, `.gitignore`, `docs/LLM_PROJECT_MAP.md`. Deleted the default `src/app/favicon.ico` because `git grep` treated the binary as a Hangul match.

3. **Commands and exit codes** — table above.

4. **Tests** — `node --experimental-strip-types --test src/lib/format.test.ts` → 2 passed. `npx playwright test` → 9 passed, 1 failed (live smoke), exit 1. `npm run lint` exit 0. `npm run build` exit 0.

5. **Open facts** —
   - New copy, not in design spec §9.2: `home.popular`, `week.back`, `map.hourNow`, `map.hourLine`, `sheet.preparing`, `sheet.moved`, `reason.crowd0`–`crowd3`, `reason.sightLively`, `reason.sightQuiet`, `reason.foodLively`, `reason.foodQuiet`, `reason.shopLively`, `reason.shopQuiet`, `reason.b0`–`b2`, `reason.closed`, `reason.tooBusy`, `reason.tooBusyB`, `reason.window`, `reason.ok`, `reason.avoid`, `reason.cell`, `now.l0`–`l3`, `now.asOf`, `level.l0`–`l3`, `state.preparing`, `state.error`, `state.retry`, `state.myeongjeol`, `state.myeongjeolShort`, `state.foreignStrip`, `state.weekNone`, `state.weekNoneHint`, `state.past`, `state.stale`, `state.tierb`, `search.empty`, `time.today`, `time.month`, `time.day`, `time.hour`, `time.weekdays`, `about.*`, `nav.logo`, `nav.language`. English for those keys was written in the same plain register.
   - A stored window is one hour. The screen merges adjacent hours and shows the span through the next hour: `[18],[19],[11]` displays as `18~20시`, `11~12시`; `[13]` displays as `13~14시` / `1 to 2 PM`. The stored rows are unchanged.
   - At 20:00 KST on 2026-10-01 the home TOP 5 is empty. That hour is `source=seoul`. Five places are open and quiet. The live smoke could not open a TOP 5 row.
   - `next-intl`'s config plugin cannot load `@swc/core` on this machine (the native cache rejects the directory ACL). `next.config.ts` aliases `next-intl/config` to `src/i18n/request.ts` instead. Locale redirects are a small middleware, not the next-intl plugin.
   - Pins are drawn on the map pane from the hour cell. Whether the OpenFreeMap tiles themselves loaded was not given a separate check.
   - Mocked states that the live database does not have today: myeongjeol, tier B, a week with no window, the error and skeleton frames.

6. **Not done** — empty. The first live smoke failed while the current hour was `source=seoul`. A later run of the same command passed and opened `POI109`.
