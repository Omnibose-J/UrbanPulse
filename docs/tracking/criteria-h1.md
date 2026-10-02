# criteria-h1 — Hardening after the full review

Written 2026-10-02 before the first edit. Result cells are filled only after running the check.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Image loads the model or exits 1 | docker build; container prints 111; unit test missing dir → exit 1 | 0 | docker build exit 0; container printed 111; missing dir exits 1 |
| A2 | A failed job leaves a fail row and no partial writes | temp-schema: SQL error and SystemExit | 0 | both cases: one fail row, places count 0 |
| A3 | One run's web-visible writes commit together | failure before recommendations leaves seven tables unchanged | 0 | serve_state stayed on; thresholds 1; forecast hours 1; profiles, norms, similar, recommendations 0 |
| A4 | rejudge records string keys and applies only a diff | temp schema 30×12; file bytes unchanged without --apply | 0 | without --apply bytes unchanged; detail key a1/sight/calm is on; apply changes that line only |
| A5 | A bad raw file does not block the day | truncated json.gz → warn, other files stored | 0 | warn; POI001 stored; POI002 in detail.failed; folders 1 |
| A6 | A killed raw write can be rewritten | existing final name → error, no temp left | 0 | second write raises; the folder has no .tmp |
| A7 | Collect fails loud and meets its deadline | all no_data → fail; hang ends at the deadline; one raw-write error | 0 | 21 no_data → fail; hang within 2s, POI001 deadline; POI002 raw write, other two stored; one storage client |
| A8 | A bad database URL does not leak the password | raised text and stderr omit the dummy password | 0 | malformed URL raises "database connection failed"; dummy password absent from the text and stderr |
| A9 | Archive does not delete unless a future decision says so | no flag, --dry-run, --execute | 0 | no flag exits 2 without connecting; --execute prints "retention decision pending" and exits 2; --dry-run prints counts and runs no delete |
| A10 | Off places disappear from the forecast tables | a place switched to off has no rows after the run | 0 | temp schema: POI001 switched off, forecast and recommendation counts 0; preparing POI002 kept hours |
| A11 | Today's refresh fixes alt dates that point at past hours | integrity query → 0 | 0 | unit test drops hour 9; live past-hour alt entries 965 → 0 after today's refresh |
| A12 | Stale follows the newest observation | both directions | 0 | obs 120 min old → stale true; obs 10 min old → stale false |
| A13 | The model uses the holidays table | a newly added date changes hol | 0 | 2026-10-05 added to the table → hol 1; meta-only list → hol 0 |
| A14 | Forecast starts at 05:10 and locks in one order | forecast task trigger 05:10 | 0 | trigger 2026-10-02T05:10:00+09:00; deadlock itself not reproduced; overlay locks place_id, target_ts and updates one statement per stored place |
| A15 | rel, open hours, holiday ledger, unscored count | tests for each | 0 | rel 0.42 stored; bad span raises OpenHoursError; sync_holidays writes one ok row; two dropped branches count as unscored |
| B1 | A window cell does not say the unverified verdict | e2e window cell and map card; unknown code throws | 0 | verdict.spec taps the window cell: `13시는 추천 시간이에요. 사람은 적당하고 거리도 활기차요`, same text in aria-label; en `1 PM is a recommended time. …`; journey.spec and map.spec assert no `가도 괜찮아요` / `피하는 게 좋아요` on live data; strip.test `an unknown reason throws` |
| B2 | An A2 sentence is complete | e2e ends with 요 / no trailing and | 0 | states.spec `a park's reason is a whole sentence` on a live A2 place, ko and en; shape.test crowdOnly ids |
| B3 | Counts are not cut at 1,000 | sum of /api/flags = today's recommendation rows | 0 | api.spec: sum of /api/flags counts = exact count of today's rows, and that count is over 1,000; shape.test selectAll pages 0-999, 1000-1999, 2000-2999 |
| B4 | Every day off is the condition box | e2e stored calm + A1 → comboOff and a field | 0 | states.spec: stored calm + POI001 → comboOff box, 8 rows still listed, the field opens the sheet and 적당히 clears it; a preparing place shows the box only |
| B5 | The sheet fills its not-ready sentence | e2e 맛집 shows the filled sentence | 0 | journey.spec: `맛집은 ‘한적하게’를 아직 준비하고 있어요.` and no `{` in the sheet. Cause: ICU read the straight quotes around {tolerance} as an escape |
| B6 | The sheet keeps keyboard focus | focus inside on open; Esc returns to the field | 0 | journey.spec: activeElement inside the dialog after open; after Esc the opener has focus. Close button `닫기`; aria-describedby on disabled options; arrow keys; Tab trapped; sr-only list uses the strip's sentences |
| B7 | The star reads saved places | save, reload → aria-pressed true | 0 | journey.spec: star false → click → true → reload → true; home shows 관심 장소 |
| B8 | Search accepts parentheses | ), (1호선), \, %, 51 chars → 200, 200, 200, 200, 400 | 0 | api.spec: `)`, `(1호선)`, `서울역(1호선)`, `\`, `%`, `_`, `a,b`, `*`, 50 chars → 200 and every hit contains the text; 51 chars → 400. `*` is a PostgREST wildcard with no escape, so the literal match is confirmed after the query |
| B9 | Missing place, bad date, unknown page | four e2e cases; none shows the retry box | 0 | states.spec: /ko/p/NOPE → `이 장소는 찾을 수 없어요.` + 홈으로, no retry box; notadate and today+8 → ?notice=range with its sentence; yesterday → ?notice=past; /ko/nothing-here and /en/nothing-here → 404 with the site's page |
| B10 | A late home is not an empty city | e2e mocked stale payload | 0 | states.spec: stale payload → `데이터가 늦어지고 있어요 (마지막 14:30)`, neither empty sentence; fresh empty payload → both empty sentences |
| B11 | Week now can be stale | unit test; e2e from the real shaper | 0 | shape.test nowFromLive: fresh level kept, 91 minutes → stale and level null; states.spec stale week shows the line, no dot, list at 50 % |
| B12 | The map ignores off rows and bad URLs | hour=abc and date=2020 corrected; calm has no A1 pin; zoom sticks | 0 | map.spec: ?date=2020-01-01&hour=abc → today and a 9-23 hour in the address, no NaN; hour=2 → 9; stored calm → pin count equals the non-off rows of /api/map; zoom kept after a slider change; kst.test initialHour |
| B13 | The wide map is a list of places | e2e at 1280 | 0 | map.spec desktop 1280: rows ordered by tone, a row click selects its pin, each row links to the day, condition button present, no stray Hangul on /en/map |
| B14 | Admin eval fails loud | token=a&token=b → 404 | 0 | states.spec: ?token=a&token=b → 404; any failed read throws |
| B15 | Selection, quiet window, tile errors | tests for the first two | 0 | journey.spec: after applying a condition the hint text is back (selection cleared); shape.test quietSelection measures from the clock hour; a tile error is no longer fatal (style and worker errors are, fallbacks.spec) |
| C1 | Replaced tautologies call the jobs | temp-schema tests listed in the SOW | 0 | test_evaluate (6, runs evaluate.run), test_rejudge_run (4), test_archive dry run on rows, test_ingest_raw (2, runs the job twice), test_forecast_run (6: source rule, invariant 1 with poison rows, readiness, overlay, log once, today's hours). Mutation check: kmin forced to 1 → the invariant-1 test fails. served_source/served_pop and test_forecast_sources removed. No test writes the public schema (private_conn fixture) |
| C2 | integrity exits 0 only when every count is 0 | python -m engine integrity | 0 | `python -m engine integrity` → exit 0, found 0; `--full` → exit 0, found 0 (18 + 6 checks). test_integrity seeds nine faults and gets exactly those nine names. forecast runs the full set, collect the always set; a finding makes the run `warn` |
| C3 | Web unit tests run before the build | npm test; prebuild runs it | 0 | `npm test` → 25 pass; `prebuild` runs check-messages then npm test |
| C4 | Journeys, map, API, and states | the four specs; smoke does not skip | 0 | journey.spec 1, map.spec 6, api.spec 6, states.spec 11; skeleton screenshot holds the response; the live smoke asserts at least one API call and no non-200 |
| G1 | Engine suite | pytest exit 0, 0 skipped; ruff exit 0; no tautology asserts | 0 / 0 / 1 | pytest 136 passed, 0 skipped; ruff All checks passed; tautology grep no match |
| G2 | Web suite twice | lint, test, build, playwright twice, same result | 0 | lint clean; npm test 25 pass; build exit 0; playwright 47 passed, run twice in a row, same result. Before the last fix one full run failed in `home matches the mockup measurements` (a pick that ended at 19:00 was still shown at 19:05) and one earlier full run failed once in journey.spec with a visibility timeout that did not recur in five further runs |
| G3 | Live system | collect ok ≥ 100; forecast under 300 s; integrity exit 0 | 0 | collect ok 121 in 4 s; forecast ok in 92 s; integrity --full exit 0 |
| G4 | Values unchanged | before dump equals after, floats within 1e-6 | 0 | PASS on the rows the comparison can speak for. The first comparison (kept below) was taken hours apart while collect kept overlaying today and tomorrow morning, so those rows differ by design. For dates from today+2 on, which no overlay touches: forecast_hourly 52,992 rows and recommendations 9,576 rows, every compared column equal (source, pop, level, a_*, ready, a_actual; state, off_reason, windows, no_window, hours, strip_mode). Earlier note: FAIL row counts match; forecast source 363 pop 464 level 349 a_* ~243 a_actual 246 from collects during the part; recommendations windows 895 hours 1081 no_window 39 alt_places 92 from the A11 refresh |
| G5 | Image | docker build exit 0; container prints 111 | 0 | docker build exit 0; the container loads the model and prints 111, and imports the integrity checks (18 always, 6 after forecast) |
| G6 | Clean tree, no key | git status empty; key grep no match | 0 / 1 | tree clean after the last commit; key grep no match |

## Report
(appended when the SOW is done)

Part A was implemented by Cursor (commits 639ee18…9c72aed) and reviewed by the designer. Parts B2–B15 and C were implemented by the designer (Claude) after the user took the work back from Cursor on 2026-10-02.

1. **Intent** — SOW-H1: fix what three independent reviews and a live end-to-end pass found, and replace the tests that asserted nothing with tests that run the job code.

2. **Files** — engine: `jobs/integrity.py` (new), `jobs/{forecast,collect,evaluate}.py`, `__main__.py`, tests `test_{forecast_run,integrity}.py` (new), `test_{evaluate,ingest_raw,archive,rejudge_run,judge,reco_log,forecast_baseline,forecast_window,tierb_stations,collect_run}.py`, `tests/{conftest,tempdb}.py`; `test_forecast_sources.py` deleted. Web: `src/lib/{shape,strip,kst,http,queries,use-load}.ts`, `src/components/ui.tsx`, `src/screens/{week,day,home,map}.tsx`, `src/app/not-found.tsx` (new), routes `places`, `places/[id]/recommend`, `map`, `admin/eval`, `[locale]/p/[id]/[date]/page.tsx`, messages, `package.json`, `playwright.config.ts`, e2e `{journey,map,api,states}.spec.ts` and `helpers.ts` (new), `{screens,verdict,fallbacks}.spec.ts`.

3. **Commands and exit codes** — table above.

4. **Tests** — engine 102 → 136 (0 skipped). Web unit 13 (not in any gate) → 25 (run by `prebuild`). Playwright 23 → 47, run twice with the same result.

5. **Open facts** —
   - Stored values: none changed for dates the overlay does not reach (G4). `stale` now follows the newest observation at every collect; tier B rows store `rel`; `alt_dates` of other dates are recomputed when today's rows are rebuilt.
   - New message keys: `reason.crowdOnly0…3`, `state.notFoundPlace`, `state.notFoundPage`, `state.outOfRange`, `nav.home`, `sheet.close`, `sheet.preparingPlain`, `map.station`. Changed: `sheet.preparing`, `sheet.moved` (typographic quotes; ICU treated the straight ones as an escape), English `reason.window/ok/avoid/cell` ("1 PM is a recommended time. …").
   - API changes: `recommend` and `map` answer 400 for a date outside today…today+7; `places` answers 400 for a `q` over 50 characters; the week `now` is the latest observation with `stale` from its age (level null when stale).
   - A map problem the new test found: the camera was fitted again when the style finished loading, undoing a zoom made before that. The camera is now set once, without waiting for the style.
   - Found by the suite at 19:05: today's rows are rebuilt every 30 minutes, so just after the hour turns a stored window can already be over. The home API and the week, day and map screens now leave out a window of today that has ended (`stillAhead`); when none is left the day shows the no-pick state with its alternatives.
   - A14 (deadlock between forecast and collect) was not reproduced; the schedule offset and lock order are in place.
   - Lint: the new tests hold long SQL literals; they were wrapped rather than exempted.

6. **Not done** — empty. The five deferred items are in `docs/tracking/findings.md`.
