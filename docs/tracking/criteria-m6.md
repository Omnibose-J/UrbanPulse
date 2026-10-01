# criteria-m6 — Level thresholds that match Seoul's levels

Written before step 1. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | New rule reproduces the measured agreement | `python -m engine.train.evaluate_levels` → table pasted; each of the ten figures within ±1.0 %p | 0 | 100 places. min 48.6/51.3/0.2/21.5/3.2 PASS. split 79.6/9.0/11.4/2.6/3.2 PASS |
| A2 | Rebuilt | `python -m engine forecast` → exit 0; `detail.levels_rule = "split"`; `select count(*) from level_thresholds where not (t1 <= t2 and t2 <= t3)` → 0 | 0 | forecast exit 0; detail split; monotone violations 0; 121 threshold rows |
| A3 | Fewer false "too busy" hours | before and after the rebuild, paste the reason counts for future moderate hours | 0 | before closed 8204, fit 23461, outside_hours 1432, too_busy 3548. after closed 9480, fit 28684, outside_hours 1504, too_busy 577 |
| A4 | No-pick days | before and after: A1 sight moderate future no_window / rows, and POI083, POI060 alone | 0 | before 18/461, POI083 3/6, POI060 4/6. after 2/537, POI083 0/7, POI060 0/7 |
| A5 | Flag applied | foreign-heavy shop busy_ok on places → `off / failed` only | 0 | only (off, failed) |
| A6 | Invariants still hold | the five queries of SOW-M3 row A4 → 0 each | 0 | all five counts 0 |
| A7 | Tests, lint, web | pytest, ruff, `npm run build`, playwright → exit 0 | 0 | pytest 88 passed, 1 skipped; ruff clean; build exit 0; playwright 19 passed |
| A8 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match | 1 | no match |
| B1 | Map fetch failure shows the error box | Playwright: `/api/map` 500 → error box, zero pins | 0 | fallbacks spec passed |
| B2 | Map style failure shows the error box | Playwright: style URL blocked → error box | 0 | fallbacks spec passed |
| B3 | Off is preparing, not "no time" | Playwright: `state off, off_reason failed` → comboOff text, no AltButton | 0 | fallbacks spec passed |
| B4 | No invented "as of" time | unit test: no live row → now is null | 0 | shape.test.ts passed |
| B5 | Alt places without a name are dropped | unit test: unjoined alt is absent | 0 | shape.test.ts passed |
| B6 | API errors are logged | a thrown error is logged once and the response is 500 unavailable | 0 | logApiError before every 500; health null count returns 500 |
| B7 | Invalid stored settings are rewritten | unit test | 0 | normalizeConditions replaces an unknown purpose |
| B8 | Impossible defaults removed | `tsc` green; health null count → 500 | 0 | tsc exit 0; health returns 500 when count is null |
| B9 | Off rows do not draw an empty strip | Playwright week list with an off day shows the state text | 0 | fallbacks spec passed; D3 still passes |

## Report

1. **Intent** — SOW-M6 replaces the level cut with the error-minimising boundary, turns off foreign-heavy shopping when busy is allowed, softens the closed-hour sentence, and removes fallbacks that hid a failure.

2. **Files** — created `app/engine/train/evaluate_levels.py`, `app/web/src/lib/shape.ts`, `e2e/fallbacks.spec.ts`. Edited `levels.py`, `feature_flags.yaml`, `forecast.py`, `messages/{ko,en}.json`, map/day/home screens, route handlers, `kst.ts`, `storage.ts`, `queries.ts`.

3. **Commands and exit codes** — table above.

4. **Tests** — pytest 88 passed, 1 skipped, exit 0. ruff exit 0. `npm run build` exit 0. `npx playwright test` 19 passed, exit 0. `npx tsc --noEmit` exit 0.

5. **Open facts** —
   - evaluate_levels, 100 on places, mean of per-place rates, ±1.0 %p: min 48.6 / 51.3 / 0.2 / 21.5 / 3.2 PASS; split 79.6 / 9.0 / 11.4 / 2.6 / 3.2 PASS.
   - A3 before (old rule): closed 8204, fit 23461, outside_hours 1432, too_busy 3548. After: closed 9480, fit 28684, outside_hours 1504, too_busy 577.
   - A4 before: no_window 18 of 461; POI083 3 of 6; POI060 4 of 6. After: 2 of 537; POI083 0 of 7; POI060 0 of 7. The two forecasts used different `today` values because the clock crossed midnight (issued 2026-10-01, then 2026-10-02), so the future-date windows are not the same set of days.
   - First-pick hour counts on on rows after the rebuild: 9시 2632, 10시 302, 11시 615, 12시 1297, 13시 401, 14시 117, 15시 85, 16시 161, 17시 185, 18시 444, 19시 314, 20시 139, 21시 55, 22시 80, 23시 12.
   - `level_thresholds` has 121 rows after the rebuild, the same number of A1/A2 places. No separate before count of the ready flag was stored.

6. **Not done** — empty.
