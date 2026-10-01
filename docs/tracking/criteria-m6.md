# criteria-m6 — Level thresholds that match Seoul's levels

Written before step 1. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | New rule reproduces the measured agreement | `python -m engine.train.evaluate_levels` → table pasted; each of the ten figures within ±1.0 %p | | |
| A2 | Rebuilt | `python -m engine forecast` → exit 0; `detail.levels_rule = "split"`; `select count(*) from level_thresholds where not (t1 <= t2 and t2 <= t3)` → 0 | | |
| A3 | Fewer false "too busy" hours | before and after the rebuild, paste the reason counts for future moderate hours | | |
| A4 | No-pick days | before and after: A1 sight moderate future no_window / rows, and POI083, POI060 alone | | |
| A5 | Flag applied | foreign-heavy shop busy_ok on places → `off / failed` only | | |
| A6 | Invariants still hold | the five queries of SOW-M3 row A4 → 0 each | | |
| A7 | Tests, lint, web | pytest, ruff, `npm run build`, playwright → exit 0 | | |
| A8 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match | | |
| B1 | Map fetch failure shows the error box | Playwright: `/api/map` 500 → error box, zero pins | | |
| B2 | Map style failure shows the error box | Playwright: style URL blocked → error box | | |
| B3 | Off is preparing, not "no time" | Playwright: `state off, off_reason failed` → comboOff text, no AltButton | | |
| B4 | No invented "as of" time | unit test: no live row → now is null | | |
| B5 | Alt places without a name are dropped | unit test: unjoined alt is absent | | |
| B6 | API errors are logged | a thrown error is logged once and the response is 500 unavailable | | |
| B7 | Invalid stored settings are rewritten | unit test | | |
| B8 | Impossible defaults removed | `tsc` green; health null count → 500 | | |
| B9 | Off rows do not draw an empty strip | Playwright week list with an off day shows the state text | | |

## Report
(AGENTS.md format, appended when done)
