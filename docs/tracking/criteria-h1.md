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
| B1 | A window cell does not say the unverified verdict | e2e window cell and map card; unknown code throws | | |
| B2 | An A2 sentence is complete | e2e ends with 요 / no trailing and | | |
| B3 | Counts are not cut at 1,000 | sum of /api/flags = today's recommendation rows | | |
| B4 | Every day off is the condition box | e2e stored calm + A1 → comboOff and a field | | |
| B5 | The sheet fills its not-ready sentence | e2e 맛집 shows the filled sentence | | |
| B6 | The sheet keeps keyboard focus | focus inside on open; Esc returns to the field | | |
| B7 | The star reads saved places | save, reload → aria-pressed true | | |
| B8 | Search accepts parentheses | ), (1호선), \, %, 51 chars → 200, 200, 200, 200, 400 | | |
| B9 | Missing place, bad date, unknown page | four e2e cases; none shows the retry box | | |
| B10 | A late home is not an empty city | e2e mocked stale payload | | |
| B11 | Week now can be stale | unit test; e2e from the real shaper | | |
| B12 | The map ignores off rows and bad URLs | hour=abc and date=2020 corrected; calm has no A1 pin; zoom sticks | | |
| B13 | The wide map is a list of places | e2e at 1280 | | |
| B14 | Admin eval fails loud | token=a&token=b → 404 | | |
| B15 | Selection, quiet window, tile errors | tests for the first two | | |
| C1 | Replaced tautologies call the jobs | temp-schema tests listed in the SOW | | |
| C2 | integrity exits 0 only when every count is 0 | python -m engine integrity | | |
| C3 | Web unit tests run before the build | npm test; prebuild runs it | | |
| C4 | Journeys, map, API, and states | the four specs; smoke does not skip | | |
| G1 | Engine suite | pytest exit 0, 0 skipped; ruff exit 0; no tautology asserts | | |
| G2 | Web suite twice | lint, test, build, playwright twice, same result | | |
| G3 | Live system | collect ok ≥ 100; forecast under 300 s; integrity exit 0 | | |
| G4 | Values unchanged | before dump equals after, floats within 1e-6 | | |
| G5 | Image | docker build exit 0; container prints 111 | | |
| G6 | Clean tree, no key | git status empty; key grep no match | | |

## Report
(appended when the SOW is done)
