# SOW-H1 — Hardening after the full review (local)

On 2026-10-02 the designer had three independent reviewers read the engine and the web app, ran an API fuzz and a database-integrity sweep against the live local stack, and walked the user journeys in a browser. Every item below was confirmed by the designer against the code or the running system unless marked "unconfirmed". The suites were green while these existed, so Part C (tests that execute the real code) matters as much as the fixes.

Run this before SOW-MC. Three parts; do them in the order A → B → C, but write each fix's test with the fix.

## Files you may touch

`app/engine/**`, `app/web/**` (not its `AGENTS.md`, `CLAUDE.md`, `README.md`), `scripts/*.ps1`, `docs/tracking/criteria-h1.md`, `docs/tracking/findings.md`, `docs/LLM_PROJECT_MAP.md`. No schema change. No change to any computed value except where a row says so.

---

# Part A — Engine

| # | Defect (where) | Failure it causes | Fix | Check |
|---|---|---|---|---|
| A1 | The image has no model: `Dockerfile` copies only `app/engine`; `forecast._active_model` (`forecast.py:132`) looks under `REPO_ROOT/models`, finds nothing, returns "no model", and the job ends `ok` | In a container every place drops to `preparing` and every recommendation to `off`, with exit 0 | `settings.MODELS_DIR` = env `MODELS_DIR` or `REPO_ROOT/models`. Dockerfile: `COPY models /srv/models`, `ENV MODELS_DIR=/srv/models`. When `model_registry` has an active row and its artifact or `meta.json` is missing, or `meta` does not match the registry row's version, exit 1 naming the path | `docker build`; `docker run --rm --entrypoint python urbanpulse-engine -c "from engine import ratio_model, settings; m = ratio_model.load(settings.MODELS_DIR / 'ratio_v1'); print(len(m.place_index))"` → 111. Unit test: active row + missing dir → exit 1 |
| A2 | Failure handlers update `job_runs` on a connection whose transaction is aborted (`forecast.py:170`, `evaluate.py:42`); `SystemExit` bypasses `except Exception` | The row stays `running` forever; on a Python error a half-done transaction is committed | One helper used by every job: `rollback()` first, then write the ledger on its own short transaction; catch `BaseException` for the ledger write and re-raise. A job start marks any `running` row of the same job older than 2 hours as `fail` with `detail.reason = "abandoned"` | Tests on a temp schema: an injected SQL error and an injected `SystemExit` each leave one `fail` row and no partial writes in the web-visible tables |
| A3 | `forecast` commits `places`/thresholds early and the forecast tables later (`:287`, `:368`, `:497`) | A failure leaves new `serve_state` beside yesterday's rows | The web-visible writes of one run (`places` state, `level_thresholds`, `lively_profile`, `lively_norm`, `forecast_hourly`, `recommendations`, `similar_places`) commit together; the two logs commit after them | Test: failure injected before the recommendation write → all seven tables unchanged |
| A4 | `rejudge` puts tuple keys into the JSON detail (`rejudge.py:84`) and writes the flag file before the ledger | The first time any combination has enough data the job crashes; with `--apply` the flags change with no record | String keys (`"a1/sight/calm"`); write the ledger, then the file; rewrite the file only when a state differs and print the diff; bootstrap groups are per-row arrays per place (`n_lively` ones, `n_hours − n_lively` zeros), as in the research `boot()` | Temp-schema test with 30 dates × 12 places: runs, records, `--apply` on a temp copy changes only the differing lines; without `--apply` bytes unchanged |
| A5 | `ingest_raw` has no per-file error handling; `read_day` loads a whole day into memory (≈1.5 GB) | One bad file blocks replay of the day; the cloud job would be killed | Iterate lazily; a file that cannot be read or parsed is counted in `detail.failed` with its name and the run continues (`warn`); add `detail.folders` | Test: a day with one truncated `.json.gz` → `warn`, other files stored |
| A6 | Local raw write is `open("xb")` + write | A kill mid-write leaves a truncated file that can never be rewritten | Write `<name>.tmp`, `os.link` to the final name (fails if it exists), unlink the temp | Test: existing final name → error, no temp left |
| A7 | `collect`: an exception from the raw write escapes the worker pool; `no_data` has no threshold; per-place failure reasons are dropped; worst-case fetch time (≈760 s) exceeds the 10-minute limit; one GCS client per place | A storage error kills the run with no ledger row; an API shape change makes every place `no_data` with status `ok`; a hung API never reaches the ledger | Raw-write error → that place is `failed` with reason `raw write`; `failed + no_data` among places not `off` above 20 → `fail`, above 0 → `warn`; `detail.failed_places = {code: reason}`; `httpx.Timeout(20, connect=5)` and an overall fetch deadline of 6 minutes after which unfinished places are `failed` with reason `deadline`; one storage client per run | Tests with a fake API: all places `no_data` → `fail`; a hanging place → run ends within the deadline with that place `failed`; raw-write error on one place → others stored |
| A8 | A malformed `DATABASE_URL` raises `psycopg.ProgrammingError` whose text contains the connection string | The password lands in a log | One `db.connect()` used everywhere: `connect_timeout=5`, catches `psycopg.Error` on connect and raises a fixed-text error `from None` | Test: a bad URL with a dummy password → the raised text and captured stderr do not contain the password |
| A9 | `archive` deletes by default; `--dry-run` is opt-in | A forgotten flag deletes the history the activity profile needs | No flag → exit 2 with a message; `--dry-run` as now; `--execute` exists but exits 2 with "retention decision pending" | Test: the three invocations |
| A10 | Rows of a place that turned `off`, or of a purpose its tier no longer has, are never removed | The map keeps recommending a dead place for days | The full run deletes `forecast_hourly` and `recommendations` rows not in the set it just built | Test: a place switched to `off` has no rows after the run |
| A11 | Collect's today-refresh leaves `alt_dates` of other dates pointing at today's hours that are over (14 such rows on 2026-10-02 13:54) | "오늘 13~15시가 더 나아요" opens a day with no pick | The refresh recomputes `alt_dates` of all dates for the places it rebuilt; `_alt_dates` groups the pool once (it scans the whole pool per row now) | Integrity query in C2 → 0 |
| A12 | `stale` is set only by the 05:00 run | A feed that dies at 08:00 stays "fresh" all day; a 05:00 run after a sleep marks everything stale until tomorrow | `apply_overlay` sets `stale` for all of a place's rows from the age of its newest `live_obs` (> 90 minutes) | Test both directions |
| A13 | The model's holiday list is frozen in `meta.json` (`ratio_model.py:26`) | A holiday added to the table later gets no holiday correction, silently | `ratio()` takes the holiday set and block starts from the caller, which reads the `holidays` table | Test: a date added to the table changes `hol` for that date |
| A14 | `forecast` and `collect` both start at 05:00 and lock `forecast_hourly` rows in different orders (unconfirmed deadlock); the overlay issues one `UPDATE` per row | One job aborts | Forecast task at 05:10; both lock in `place_id, target_ts` order; overlay as one statement per place, limited to the places just stored | Forecast task trigger 05:10 |
| A15 | Small: tier B rows store no `rel`; `open_hours` with a bad shape either aborts everything or silently closes the place; `sync_holidays` writes no `job_runs` row; `evaluate`'s `unscored` count omits two branches | — | Store `rel`; validate `HH:MM-HH:MM` in `load_places` and raise a named error in `open_hours_for`; wrap `sync_holidays` in the job ledger; count every unscored logged row | Tests for each |

---

# Part B — Web

| # | Defect (where) | What the visitor sees | Fix | Check |
|---|---|---|---|---|
| B1 | `strip.ts`: the `fit` reason has no entry, so `?? "ok"` prints `reason.ok` | A recommended hour reads "12시는 추천 시간이에요. 가도 괜찮아요": the unverified verdict SOW-M8 removed. `two_step` would read "가도 괜찮아요. 가도 괜찮아요" | For a window cell (and a `fit` cell in `two_step`) the reason is the §9.3 sentence built from the cell's `crowd` and `act` and the row's purpose (same function as the answer card). An unknown reason code throws; no default. English uses the 12-hour form everywhere ("12 PM is a recommended time.") | e2e taps a **window** cell on ⑤ and reads the map card for a window hour: no `reason.ok` text; unit test: unknown code throws |
| B2 | `reason.ts`: A2 windows have no activity clause | Park and palace cards end mid-sentence: "사람은 적당하고" | New keys `reason.crowdOnly0…3`: ko `사람이 적어요` / `사람이 적당해요` / `조금 붐벼요` / `꽤 붐벼요`; en `It is quiet` / `It is moderately busy` / `It is a bit busy` / `It is quite busy`. Used when the window has no activity | e2e on an A2 place: the sentence ends with "요" / has no trailing "and" |
| B3 | `/api/flags` reads with `.limit(2000)`; PostgREST caps at 1,000 | `/about` counts 1,000 of 1,596 rows, differently each run | Page with `.range()` until a short page; add a helper `selectAll` and use it for every read that can exceed 1,000 rows (check `map` with stations, `forecast_hourly` reads); a read that hits a cap without paging is a defect | Live check: sum of `/api/flags` counts = `select count(*) from recommendations where date = today` |
| B4 | `week.tsx:60`: only `off_reason = 'preparing'` counts as preparing | With a stored condition that is off for this place, the card says "이번 주에는 추천할 시간이 없어요" while every row says "준비 중"; on tier B the condition field is hidden, so there is no way out | Every day off → the `state.comboOff` box plus the condition field (all tiers); a `serve_state = 'preparing'` place shows the preparing box only (no week list, no condition field) | e2e: stored `calm` + an A1 place → comboOff text and a working field |
| B5 | `ui.tsx:481`: the sheet's "not ready" line is rendered with unfilled parameters | "맛집는 {tolerance}를 아직 준비하고 있어요." | Pass both parameters. ko message: `{purpose}은 '{tolerance}'를 아직 준비하고 있어요.` (all three purpose names end in a consonant) | e2e: choosing 맛집 shows "맛집은 '한적하게'를 아직 준비하고 있어요." |
| B6 | Sheet accessibility (`ui.tsx:457`): focus is not moved in or returned; the close button is labelled "바꾸기"; disabled options are not described; the screen-reader table prints raw codes | Keyboard and screen-reader users are left behind the dialog | Focus the title on open, trap Tab inside, return focus to the field on close; close button labelled with a new key `sheet.close` (닫기 / Close); `aria-describedby` on disabled options; arrow keys move within a radiogroup; the sr-only table is built from the same sentences as the strip | e2e: after open `document.activeElement` is inside the dialog; after Esc it is the condition field |
| B7 | `week.tsx:46`, `day.tsx:35`: the star starts empty and never reads storage | A saved place shows an empty star; tapping it removes the favourite | Initialise from `readFavorites()` once the place is known | e2e: save, reload → `aria-pressed="true"` |
| B8 | Search (`queries.ts:44`): `)` breaks the PostgREST filter → 500; a backslash silently matches nothing; a 5,000-character `q` → 500 | The error box on a legitimate search such as "서울역(1호선)" | Three separate `ilike` filters with the value passed as a parameter (or quoted and escaped); `q` longer than 50 characters → 400 | Live: `q` = `)`, `(1호선)`, `\`, `%`, 51 characters → 200, 200, 200, 200, 400 |
| B9 | Unknown place, malformed date, date beyond today + 7 | "불러오지 못했어요. 다시 시도" for a place that does not exist; a blank screen for a far date; Next's default English 404 for an unknown path | 404 from the API → a not-found state with a link home (`state.notFoundPlace`: `이 장소는 찾을 수 없어요.` / `We can't find this place.`); malformed or out-of-range date → redirect to ③ with a notice (`state.outOfRange`: `오늘부터 7일 뒤까지만 볼 수 있어요.` / `You can look up to 7 days ahead.`); `not-found.tsx` under `[locale]` and at the root with `state.notFoundPage` (`이 페이지는 찾을 수 없어요.` / `We can't find this page.`) and `nav.home` (`홈으로` / `Home`) | e2e for the four cases; none shows the retry box |
| B10 | Home when data is late (`home.tsx:49,59`) | An outage reads as a calm city: "지금은 붐비는 곳이 없어요" and a caption " 기준" with no time | `stale` → one line "데이터가 늦어지고 있어요 (마지막 14:30)" in place of both lists; the empty sentences only when data is fresh | e2e with a mocked stale payload |
| B11 | Week "now" (`shape.ts:16`): `stale` is hard-coded false, so the stale branch cannot be reached | Late data silently drops the now line | `now` = the latest live observation with `stale` from its age; the screen shows the §5.10 stale line and the 50 % strip | Unit test on the shaping function; e2e with a mocked stale payload produced by the real shaper |
| B12 | Map (`map.tsx`): `state` is ignored (off rows drawn as grey pins with an invented cell); the initial hour is unclamped (02:00 → "2시", `?hour=abc` → "NaN시"); `?date=` outside the 8 days shows an empty map; the URL never carries date and hour; `onLoad` refits after the user zoomed; every slider step rebuilds all markers | Off places look like "avoid"; nonsense hours; a silent empty map | Off rows are not drawn; hour clamped to 9–23 and date to today…today+7 at initialisation (invalid → replaced in the URL); date and hour kept in the URL with `replaceState`; fit once; recolour markers in place | e2e: `?hour=abc&date=2020-01-01` → a valid map with the URL corrected; stored `calm` → no A1 pin; zoom then slide → zoom unchanged |
| B13 | Map on width ≥ 1024: the list is unordered, a row click does not move the map, ⑤ cannot be reached; names are Korean on `/en`; no condition button; no "· 추정" on stations | — | Order recommended → rest; click flies to the pin; each row links to ⑤; `PlaceName` for names; condition button in the bar; station mark | e2e at 1280 wide |
| B14 | `/admin/eval`: a failed query renders an empty table; a repeated `token` parameter throws | An outage looks like "no data" | Throw on any query error (the page then shows an error); take the first `token` value as a string | e2e: `?token=a&token=b` → 404 |
| B15 | Small: the tapped cell stays selected after a condition change (`day.tsx:37`); the open-quiet 2-hour limit is measured from the measured hour, not the clock (`queries.ts:328`); any tile error during load switches the map to the error box (`map.tsx:85`) | — | Clear the selection on condition change; measure from the clock hour; only a style or worker failure is fatal | Tests for the first two |

---

# Part C — Tests that execute the real code, and a permanent end-to-end suite

### C1 Replace the tests that assert nothing
These exist today and must go: `test_evaluate.py` (`assert 6.31 > baseline + 0.3`), `test_judge.py` (`assert 27 < 28`), `test_archive.py` (`assert target.exists()` after writing it; `assert run is not None`), `test_ingest_raw.py` (`read_all() == read_all()`), `test_forecast_sources.py` and `test_forecast_baseline.py` (they test helpers the job does not call), `test_reco_log.py` (hand-written SQL run twice). Replace them with tests that call the job functions on a **temporary schema** with hand-built rows:
- `evaluate_date`: the WAPE values; re-run replaces; null columns for `busy_ok` and A2; `outside_hours` excluded; warning at +0.31 %p and not at +0.29 %p; fewer than 14 days skipped.
- `rejudge`: A4's checks plus the insufficient rule at 27 dates and at 9 places.
- `archive`: A9's checks.
- `ingest_raw`: a folder ingested twice changes 0 rows the second time; A5's bad file.
- `_write_forecasts` with a fake model and a registry passing horizons {0…6}: horizon 3 `model`, horizon 7 `profile` equal to the baseline, a place outside the index `profile`; the baseline for issue date D reads no `live_obs` row with `ts >= D 00:00` (assert on the query's input rows, by inserting a poison row at D that would change the result).
- `refresh_recommendations` run twice the same day: `recommendation_log` unchanged; overlay turns a measured hour `live` and a `city_fcst` hour `seoul`; measured activity sets `a_actual`.
- Delete helpers that only tests call (`served_source`, `served_pop`).
- No test may touch the public schema's data: the two that run `drop_past_forecasts` and `apply_overlay` against live tables inside a rolled-back transaction move to the temporary schema.

### C2 `python -m engine integrity` — a read-only sweep of the live database
Exit 0 when every count is 0, else exit 1 listing the non-zero ones. One `job_runs` row. Checks: every `on` place has 8 × 24 `forecast_hourly` rows and 8 × 3 × (purposes of its tier) `recommendations` rows; no `ready` row with null level; no future hour marked `live`; no `seoul` row more than 13 hours ahead; `a_actual` only on today's A1 rows; no A2/B cell with `act`; every cell's `crowd` equals the `forecast_hourly` level of that hour; no window of today starting before the current hour; no row for a past date; no `alt_dates` / `alt_places` entry pointing to a row that is off or has no window; no `alt_dates` in the past; no `running` row older than 2 hours; `cat_counts` with 8 or 9 keys; thresholds monotone; the five invariants of SOW-M3 row A4. Run it at the end of `forecast` and of `collect` (a non-zero result makes the job `warn` with the list in `detail.integrity`).

### C3 Web unit tests run in the gate
`npm test` runs the `*.test.ts` files (they pass today but nothing runs them); `prebuild` runs it. Extract the open-quiet selection (measured activity, the 2-hour rule, A2 opening hours) into a pure function with tests; fix the D12 fixture that lists levels 1 and 0 under "busy".

### C4 Permanent end-to-end specs (live local stack, no mocks unless stated)
- `e2e/journey.spec.ts`, with the browser clock in `America/Los_Angeles`: ① → search (focus on the input; a hit; the no-result sentence) → ③ → answer card → ⑤ → tap a window cell, a non-window cell, the same cell again, a cell by keyboard → open the sheet, choose 맛집, Esc: nothing changed and no request sent → reopen, apply: the field, the request and stored conditions change → back, back, back lands on ③, ②, ① → star a place and see it on ① → a share link overrides conditions without storing them, and the app back button goes to ③.
- `e2e/map.spec.ts`: slider moves send no request; date and hour survive ⑦ → ⑤ → back; the stations toggle adds pins and is remembered; B12's cases.
- `e2e/api.spec.ts`: every route's 200 shape; the 400 / 404 / 410 cases; B8's inputs; no error response carries `s-maxage`; `/api/places/{id}/week` equals the database rows for 25 places (query through the route and through `pg`, compare `date, state, windows, hours`).
- `e2e/states.spec.ts`: B4, B9, B10, B11 and the preparing place.
- The skeleton screenshot test (`screens.spec.ts:108`) fails intermittently because the skeleton is gone before the screenshot: hold the mocked response until the screenshot is taken.
- The live smoke must fail, not skip, when it cannot walk; `statuses.every` on an empty list is not a pass.
- English pages contain no Hangul outside `lang="ko"` on `/en`, `/en/p/{id}`, `/en/search`, `/en/map`, `/en/about`.

---

## Acceptance (`docs/tracking/criteria-h1.md`, rows created before the first edit; one row per item A1–A15, B1–B15, C1–C4 with the check from its table, plus these)

| # | Criterion | Command |
|---|---|---|
| G1 | Engine suite | `python -m pytest app/engine/tests -q` → exit 0, 0 skipped; `ruff check app/engine` → exit 0; `git grep -n -E "assert (True|[0-9.]+ [<>] )" -- app/engine/tests` → no match |
| G2 | Web suite | `cd app/web; npm run lint; npm test; npm run build; npx playwright test` → exit 0, run twice in a row with the same result |
| G3 | Live system still works | `python -m engine collect` → `ok ≥ 100`; `python -m engine forecast` → exit 0 under 300 s; `python -m engine integrity` → exit 0 |
| G4 | Values unchanged | for a fixed `today`, a dump of `forecast_hourly` and `recommendations` (excluding `issued_ts`, `generated_at`, `stale`, `rel`, `alt_dates`) before Part A equals the dump after it, floats within 1e-6. List any other column that differs and why |
| G5 | Image | `docker build -f app/engine/Dockerfile -t urbanpulse-engine .` → exit 0; A1's container command prints 111 |
| G6 | Clean tree, no key | `git status --short` → empty; `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match |

## Not in this SOW (append each to `docs/tracking/findings.md` with why-not-now)

- The admin token travels in the query string (access logs, browser history). Needs a cookie or header flow; the page is local-only until SOW-MC.
- Screens navigate with `<a href>` (full page load) instead of client-side links.
- `middleware.ts` is deprecated in Next 16 in favour of `proxy.ts`.
- Places have no English name (`name_en` null for all), so English search by name finds nothing.
- Today's past hours that were never collected (2026-10-02 03:00–09:30) stay `model` rows; nothing marks a collection gap on the screens.

## Open facts to report

- Every item whose fix changed a stored value, with before and after.
- Items you could not reproduce (A14 is marked unconfirmed).
- New message keys with both texts.
- Test counts before and after, per suite.
