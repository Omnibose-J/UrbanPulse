# criteria-m4.1 — Screens match the design; today's picks stay ahead

Written 2026-10-01 before implementation. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Today's picks are ahead | `python -m engine collect` → exit 0 or warn; `select count(*) from recommendations r cross join lateral jsonb_array_elements(r.windows) w where r.date = (now() at time zone 'Asia/Seoul')::date and r.state <> 'off' and (w->'hours'->>0)::int < extract(hour from now() at time zone 'Asia/Seoul')` → 0 | 0 | collect exit 0, 121/121 ok; past-window count 0 at 22:28 KST |
| A2 | Home has a "now" at any minute | within the first 10 minutes of an hour: `/api/home` → `busy_top` has 5 rows (paste the time and the five levels) | 0 | 22:28 KST (minute 28, not the first 10); busy_top 5; levels 3,1,1,1,1 |
| A3 | Engine tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 | 0 | 74 passed in 26.66s; ruff All checks passed |
| A4 | Web checks | `cd app/web; npm run lint; npm run build; npx playwright test` → exit 0 (paste the passed count) | 0 | lint exit 0; build exit 0; playwright 15 passed |
| A5 | Visual assertions | `npx playwright test e2e/visual.spec.ts` → exit 0; list the screenshot files written | 0 | 4 passed; e2e/screenshots/live/{ko,en}-{home,week-a1,week-a2,day-window,day-none,map}.png |
| A6 | Map renders | paste the console message that was the cause and the fix; pin bounding box size from the test | 0 | Worker failed to load; after the worker URL fix, visual spec pin box 294x240 |
| A7 | Admin guarded and reachable | M5 row A7 filled: no token 404, token 200 | 0 | no token 404; token 200. criteria-m5 A7 updated |
| A8 | No literal copy, no hex, no key | the three `git grep` commands of SOW-M4 rows A5, A6 and SOW-M3 row A10 → no match | 1 | Hangul, hex, dash, and key greps exit 1 (no match). error-fg only in ui.tsx and tokens.css |

## Report

1. **Intent** — SOW-M4.1 makes the live screens read like the v6 mockup and the design spec, and stops today's recommendations from offering hours that have already passed. The home "now" lists use the latest measured live hour. The map renders with MapLibre.

2. **Files** — created `src/lib/reason.ts`, `src/app/vendor/maplibre/[file]/route.ts`, `e2e/visual.spec.ts`. Modified `reco` and forecast in earlier steps; this step's screen pass modified `messages/{ko,en}.json`, `src/styles/tokens.css`, `src/app/globals.css`, `src/middleware.ts`, `src/components/ui.tsx`, `src/lib/queries.ts`, `src/screens/{home,week,day,map}.tsx`, `src/app/api/map/route.ts`.

3. **Commands and exit codes** — table above.

4. **Tests** — `python -m pytest app/engine/tests -q` 74 passed, exit 0. `ruff check app/engine` exit 0. `npm run lint` exit 0. `npm run build` exit 0 (message check printed 110). `npx playwright test e2e/visual.spec.ts` 4 passed, exit 0. `npx playwright test` 15 passed, exit 0.

5. **Open facts** —
   - Map console message before the fix: `Error: Worker failed to load. Check that the worker URL is correct.` The OpenFreeMap style request then aborted (`net::ERR_ABORTED`). Cause: MapLibre derives the worker URL from `import.meta.url` and asks for `maplibre-gl-worker.mjs` next to that file. Turbopack emits the library as a chunk under `/_next/static/chunks/`, so that sibling does not exist and `new Worker` fails. The pins were HTML buttons on a container without an explicit height, so they stacked at the top left. Fix: serve `maplibre-gl-worker.mjs` and `maplibre-gl-shared.mjs` from `/vendor/maplibre/`, call `setWorkerUrl` before `new Map`, import `maplibre-gl.css`, set an explicit container height, and add MapLibre markers at `[lon, lat]` with `fitBounds`. After that the style loaded, a canvas had a non-zero size, and the page logged no console error. The plain `--map-land` fallback was not used. Pin centres on the 390×844 visual run spanned 294×240. The later full-suite log printed 1026×834; both are above the 150 bar.
   - New message keys: `home.todayLabel` "오늘 추천" / "Today"; `home.busyTopEmpty` "지금은 붐비는 곳이 없어요" / "Nothing is busy right now".
   - Mockup vs spec: the mockup puts the weekday inline beside the time; SOW-M4.1 puts it on its own line above the range (followed the SOW, which also stops the English card overflowing). The mockup's A2 card says "공원 · 한산해요"; spec §5.7 says "● 한산해요" (followed the spec, using the level word). The mockup's busy-level colours are hex that already exist as `--star` and `--hol`. The mockup map is an SVG drawing; the spec and this SOW require MapLibre (followed MapLibre). The mockup joins extra ranges with a middle dot; spec §9.1 keeps that dot for conditions and holiday names, so extra ranges use a comma. When a day is both the best day and a holiday, the mockup shows the holiday name; the spec names both "추천" and the holiday as the date replacement (followed the mockup: holiday wins). The day card's place name has no size in the spec; the mockup uses 13px meta rather than the week card's 24px title (followed the mockup). Spec §4.2 fixes the week-list time column at 72px, and §9.1 writes English as "11 AM to 1 PM"; that string does not fit 72px at 15px, so the English list clips on one line (followed 72px). Spec §5.11 sets the map card 28px from the bottom; the Next dev badge covers that, so the card sits 64px up and the button stays inside the viewport. The mockup's condition button adds 16px of inner padding; spec §4.2 keeps the 16px text line, so the condition row stays on that line. The search field is the exception: its text starts at x ≥ 28 because the icon sits inside the field.
   - A2 was measured at 22:28 KST, which is past the first 10 minutes of the hour. `busy_top` still had 5 rows (levels 3, 1, 1, 1, 1).
   - `/admin` was redirected to `/ko/admin` by the locale middleware, so the token check never reached the page. The middleware now leaves `/admin` alone.

6. **Not done** — empty.
