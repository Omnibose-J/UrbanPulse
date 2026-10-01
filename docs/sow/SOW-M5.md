# SOW-M5 — Evaluate, re-judge, archive, admin page (local)

Work unit W12 (`UrbanPulse_구현설계서.md` §4.6, §4.7, §7.0, §7.2). The engine scores yesterday's forecasts and recommendations against what happened, proposes flag changes weekly, and can move old rows to parquet. A token-protected page shows the tables. Runs locally; SOW-MC later moves the archive target to GCS.

## Depends on

SOW-M3 (`recommendation_log`, `forecast_log`), SOW-M4 (web foundation).

## Files you may touch

Create: `app/engine/jobs/{evaluate,rejudge,archive}.py`, `app/engine/judge.py`, `scripts/register_evaluate_task.ps1` (ASCII), `app/engine/tests/**`, `app/web/src/app/admin/eval/**`, `docs/tracking/criteria-m5.md`.
Edit: `app/engine/__main__.py` (wire `evaluate [--date]`, `rejudge [--apply]`, `archive [--dry-run]`; `tier_b` stays exit 2), `app/engine/requirements.txt` (`pyarrow`, `pandas`, `numpy` pinned to the installed versions if not already listed), `docs/LLM_PROJECT_MAP.md`.
Read-only: migrations, `analysis/` (reference: `boot()` and `verdict()` in `analysis/scripts/rejudge.py`), specs, `docs/sow/`, `AGENTS.md`.

## Definitions

- **Actual level** of an hour: the hourly level of `app/engine/hourly.py`. **Actual value**: the hourly live value.
- **Actual activity** of an hour for a logged row: hourly commerce value of the row's purpose ÷ the row's `p90`. Lively when `>= 0.5` for every purpose: the truth threshold is the pre-registered 0.5; the row's `lively_min` (0.6 for `shop`) is only the prediction gate and is not used here.
- **Scorable hour**: actual level exists, and for A1 the actual activity exists.
- **Crowd kept**: actual level `<=` allowed level (`calm` 1, `moderate` 2). Not scored for `busy_ok`.

## Steps

### 1 `evaluate` — `python -m engine evaluate [--date YYYY-MM-DD]` (default yesterday KST), daily 06:00
One `job_runs` row. Re-running a date replaces that date's rows in the three tables (delete then insert in one transaction).
1. **`eval_daily`**: `forecast_log` rows whose `target_ts` falls on the date, joined to the actual value. Per `horizon_d`: `wape_model = Σ|pred − actual| / Σ actual`, `wape_baseline` likewise with `baseline`, `n` = joined rows. `segment = 'holiday'` when the date is in `holidays`, else `'normal'`. No joined rows for a horizon → no row.
2. **Warning** (same bar as the registration gate): over the last 28 days of normal dates, recomputed from `forecast_log` (not averaged from `eval_daily`), per horizon: model WAPE more than 0.3 %p above baseline WAPE → `status = 'warn'`, `detail.warn = [{"horizon_d", "model", "baseline"}]`. Fewer than 14 dates → no warning, `detail.warn_skipped = "fewer than 14 days"`.
3. **`reco_eval_daily`** (A1 rows of `recommendation_log` with that `date`, windows not empty): over scorable window hours, `n_hours`, `n_lively`, `n_crowd_ok` (null for `busy_ok`); over scorable hours 9…23 of the same place and purpose, `chance_hours`, `chance_lively`. A row with `n_hours = 0` is not written.
4. **`strip_eval_daily`** (A1 and A2 rows of `recommendation_log` with that `date`): cells with `reason = 'outside_hours'` are left out. `n_ok` = scorable `rating = 1` cells; `n_ok_lively` (A1; null for A2); `n_ok_crowd_ok` (null for `busy_ok`); `n_avoid` = scorable `rating = 0` cells; `n_avoid_unfit` = those where the hour really did not fit (A1: not lively, or crowd not kept; A2: crowd not kept; `busy_ok`: not lively only).
5. `detail` = row counts written per table and the counts of logged rows that had no scorable hour.
`scripts/register_evaluate_task.ps1`: task `UrbanPulse evaluate`, daily 06:00, same settings as the forecast task, log `data/logs/evaluate.log`.

### 2 `rejudge` — `python -m engine rejudge [--apply]` (run by hand; weekly)
Port `boot()` (place bootstrap, `B = 1000`, `numpy.random.default_rng(0)`, percentiles 2.5 / 97.5) and `verdict()` from `rejudge.py` into `app/engine/judge.py`.
- Input: all of `reco_eval_daily`, places grouped as in SOW-M3 (`a1`, `a1_foreign`); myeongjeol dates excluded.
- Per group × purpose × tolerance: lively rate (bar 85 %), crowd rate (bar 80 %, not for `busy_ok`); verdict PASS / BORDERLINE / FAIL each; the combination's verdict is the worse of the two; PASS → `on`, BORDERLINE → `reference`, FAIL → `off`.
- **Too little data → no verdict**: fewer than 28 distinct dates or fewer than 10 places in the combination → `insufficient`, state unchanged.
- Strip table from `strip_eval_daily` with the E6 bars (OK cells lively ≥ 85 %, crowd ≥ 80 %, avoid cells unfit ≥ 60 %), same rule. It is printed and stored in `detail`; **`strip` values are never changed by this job** (E6 is judged once by the designer on October data).
- Output: the table on stdout and in `job_runs.detail`, plus `data/rejudge/<date>.yaml` holding the flag file as it would be. Without `--apply` the tracked flag file is not touched. With `--apply` and at least one changed state, rewrite `app/engine/config/feature_flags.yaml` (`judged_at` = today, same line order) and print the diff. Do not run `--apply` in this SOW.
- `a2` is not re-judged here (no activity promise; its crowd check stays the research verdict).

### 3 `archive` — `python -m engine archive [--dry-run]`
- Candidates: `live_obs` and `commerce_obs` rows older than 90 days, `forecast_log` rows older than 180 days (by `ts` / `target_ts`, KST midnight cut).
- Write each table's candidates to `data/archive/<table>/<run date>.parquet`; read the file back; delete from the database only when the file's row count equals the candidate count, in one transaction per table. Mismatch → exit 1, nothing deleted. An existing file for that run date is never overwritten (exit 1).
- `--dry-run`: print and record the candidate counts; write nothing, delete nothing.
- **Do not register a scheduled task and do not run it without `--dry-run` on the real database.** `lively_profile` averages "all history before today" per day type; deleting commerce rows older than 90 days would starve the `holiday` and `myeongjeol` profiles. Append this to `docs/tracking/findings.md` (why not now: the retention design needs a decision; touches `lively.py`, build contract §4.7). Local Postgres has no size limit, so nothing is lost by waiting.

### 4 Admin page — `/admin/eval` (English only, server component, no locale prefix)
- Requires `?token=` equal to `ADMIN_TOKEN` (server-side comparison); otherwise 404. `ADMIN_TOKEN` unset → 404 always. The token is never logged or rendered.
- Plain tables: `model_registry`; `eval_daily` for the last 28 days plus pooled WAPE per horizon and segment; `reco_eval_daily` pooled by group × purpose × tolerance (rates and chance rate); `strip_eval_daily` pooled likewise; place counts by `tier` × `serve_state`; last 50 `job_runs` (job, status, started, duration, a 200-character cut of `detail`); the collect success rate per day for the last 7 days.
- Pooling here is display arithmetic over stored counts; no verdicts are computed in the web app.

### 5 Tests
- `test_evaluate.py` (temporary schema, hand-built rows): WAPE values; holiday vs normal segment; re-run replaces, does not duplicate; `busy_ok` null columns; A2 `n_ok_lively` null; `outside_hours` cells excluded; a logged row with no actuals writes nothing; warning fires at +0.31 %p and not at +0.29 %p; fewer than 14 days → skipped.
- `test_judge.py`: `verdict()` PASS / BORDERLINE / FAIL on constructed inputs; bootstrap is deterministic for seed 0; `insufficient` under either minimum; worse-of-two rule; `--apply` absent → file bytes unchanged (on a temp copy); with `--apply` on a temp copy only changed states differ.
- `test_archive.py` (temporary schema): cut dates; row-count check blocks deletion when the file is short (simulate by patching the reader); `--dry-run` changes nothing; existing file → exit 1.
- Web: Playwright `admin.spec.ts`: no token → 404; wrong token → 404; right token → the six table headings.

## Acceptance (`docs/tracking/criteria-m5.md`, rows created before step 1)

| # | Criterion | Command |
|---|---|---|
| A1 | Evaluate runs | `python -m engine evaluate` → exit 0 or warn; paste `job_runs.detail`. Row counts may be 0 when no log row targets yesterday yet; report the counts, do not backfill them |
| A2 | Evaluate is idempotent | run again → the three tables' counts for that date are unchanged |
| A3 | Re-judge prints without changing flags | `python -m engine rejudge` → exit 0; table pasted (every combination `insufficient` is the expected outcome this early); `git diff --stat app/engine/config/feature_flags.yaml` → empty |
| A4 | Archive dry run | `python -m engine archive --dry-run` → exit 0; candidate counts pasted; `select count(*) from live_obs` and `commerce_obs` unchanged; no file under `data/archive/` |
| A5 | No archive task | `Get-ScheduledTask 'UrbanPulse archive' -ErrorAction SilentlyContinue` → nothing |
| A6 | Evaluate scheduled | `Get-ScheduledTask 'UrbanPulse evaluate'` → daily 06:00, battery settings as collect |
| A7 | Admin page guarded | `curl -s -o NUL -w "%{http_code}" http://localhost:3000/admin/eval` → 404; with the token (read from `.env` by the script, never echoed) → 200 |
| A8 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0; `cd app/web; npm run lint; npm run build; npx playwright test` → exit 0 |
| A9 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match; the admin token value does not occur in `app/web/.next/static` (script prints `no match`) |

## Open facts to report

- The first dates for which `eval_daily`, `reco_eval_daily` and `strip_eval_daily` will have rows, given when `forecast_log` and `recommendation_log` started.
- The archive candidate counts and the oldest row per table.
- The finding on commerce retention versus the activity profile, as written to `findings.md`.
