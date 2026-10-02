# criteria-m7 — Collection works with station places present

Written 2026-10-02 before step 1. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Collect works with stations present | `python -m engine collect` → exit 0 or warn, `ok ≥ 100`; `select max(ts) from live_obs` within the last 40 minutes | 0 | ok 121; job_runs status ok at 2026-10-02 10:03; max(ts) 2026-10-02 09:30 |
| A2 | Missed snapshots stored | after the two `ingest_raw` runs: `select count(distinct ts) from live_obs where ts >= '2026-10-01 23:00+09' and ts < '2026-10-02 03:00+09'` pasted with the list of raw folders of that span | 0 | distinct ts 7 (23:00, 23:30, 00:00, 00:30, 01:00, 01:30, 02:00). folders 2300, 2330, 0000, 0030, 0100, 0130, 0200, 0230. 0230 carries PPLTN_TIME 02:00 |
| A3 | Nothing uncommitted | `git status --short` → empty | 0 | empty after the last M7 commit |
| A4 | Tasks | for the three tasks paste `Settings.WakeToRun`, `ExecutionTimeLimit`; forecast `PT1H`; `powercfg /waketimers` output | 1 | collect WakeToRun=True PT10M; forecast WakeToRun=True PT1H; evaluate WakeToRun=True PT20M. powercfg /waketimers exit 1: administrator rights required |
| A5 | Forecast time and equality | `detail.timing` before and after; total seconds; the equality check result | 0 | before 1047.7s (forecast_hourly 993.2). after 91.3s (forecast_hourly 51.4). 83424 rows identical within 1e-6 |
| A6 | Station places | `select count(*) from places where tier = 'B'` = `select count(distinct place_id) from tier_b_profile`; a second `tier_b` run changes 0 rows | 0 | 247 = 247. second run changed 0, removed 0 |
| A7 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0 with **0 skipped**; `ruff check app/engine` → exit 0; `cd app/web; npm run build; npx playwright test` → exit 0 | 0 | pytest 97 passed, 0 skipped; ruff clean; build compiled; playwright 20 passed |
| A8 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match | 1 | no match |

## Report

1. **Intent** — SOW-M7 makes collect ignore station rows that have no POI code, stores the snapshots that failed overnight, asks the three tasks to wake the machine, brings a full forecast under 5 minutes without changing stored values, and keeps a station as a place only when it has a profile.

2. **Files** — edited `collect.py`, `forecast.py`, `hourly.py`, `levels.py`, `tier_b.py`, `tierb/profile.py`, `tierb/stations.py`, the three `scripts/register_*_task.ps1`, `test_cli.py`, `test_collect_run.py`, `test_forecast_window.py`, `test_levels.py`, `test_ratio_model.py`, `api-log.ts`, `docs/LLM_PROJECT_MAP.md`, `docs/tracking/findings.md`.

3. **Commands and exit codes** — table above.

4. **Tests** — `python -m pytest app/engine/tests -q` → 97 passed, 0 skipped, exit 0. `ruff check app/engine` → exit 0. `npm run build` → exit 0. `npx playwright test` → 20 passed, exit 0.

5. **Open facts** —
   - Half-hour slots from 2026-10-01 23:00 through 2026-10-02 11:00 with no raw folder: 03:00, 03:30, 04:00, 04:30, 05:00, 05:30, 06:00, 06:30, 07:00, 07:30, 08:00, 08:30, 09:00, 09:30. Those are lost. 02:30 has a folder whose `PPLTN_TIME` is 02:00, so distinct live timestamps in the A2 window are 7, not 8.
   - Timing before (per-row model calls), seconds: refresh 0.9, thresholds 5.7, profile 25.2, forecast_hourly 993.2, recommendations 17.9, tier B 4.4, log 0.4. Total 1047.7. After (one predict per place per day): refresh 0.6, thresholds 3.2, profile 16.7, forecast_hourly 51.4, recommendations 15.2, tier B 3.9, log 0.3. Total 91.3. Equality on `data/tmp/before.parquet` and `after.parquet` for 2026-10-02 through 2026-10-09: 70656 forecast rows and 12768 recommendation rows, no column differed, floats within 1e-6.
   - The three tasks have `WakeToRun` true. `powercfg /waketimers` exited 1 because this shell is not an administrator, so it is not confirmed that the machine will actually wake from sleep.

6. **Not done** — empty. Wake-from-sleep was requested on the tasks and could not be observed.
